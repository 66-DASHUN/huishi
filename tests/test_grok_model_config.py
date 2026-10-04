from io import BytesIO
from pathlib import Path
import pytest
from app import create_app
from huishi import providers, image_api
from huishi.db import init_db

@pytest.fixture()
def app(tmp_path: Path):
    app=create_app(testing=True); app.config['DATABASE']=tmp_path/'test.sqlite3'; app.config['OUTPUT_DIR']=tmp_path/'uploads'
    with app.app_context(): init_db()
    return app

def test_grok_catalog_has_only_current_model():
    assert providers.image_model_options('grok') == [{'id':'grok-imagine-image-2.0','label':'grok-imagine 2.0'}]

def test_protocol_model_metadata_and_defaults():
    assert providers.image_model_metadata('grok-imagine-image-2.0')['default_base_url'] == 'https://api.x.ai/v1'
    assert providers.image_model_metadata('gemini-3.1-flash-image')['default_base_url'] == 'https://generativelanguage.googleapis.com'
    assert providers.provider_default_base_url('grok') == 'https://api.x.ai/v1'
    assert providers.provider_supported_resolutions('grok') == ('1K','2K')
    assert providers.provider_supported_resolutions('banana') == ('1K','2K','4K')
    assert providers.provider_endpoint_path('grok', 'text') == '/v1/images/generations'
    assert providers.provider_endpoint_path('grok', 'reference') == '/v1/images/edits'
    assert providers.provider_endpoint_path('banana', 'text') == '/v1beta/interactions'

def test_parse_rejects_known_model_protocol_mismatch(app):
    from huishi.routes_workspace import parse_provider_form
    with app.app_context(), app.test_request_context('/settings/providers', method='POST', data={
      'provider_type':'image','name':'x','base_url':'https://api.example.com','api_key':'key',
      'model':'grok-imagine-image-2.0','api_format':'banana','priority':'1','enabled':'1','resolutions':['1K']}):
        with pytest.raises(ValueError, match='模型.*协议'):
            parse_provider_form()

def test_parse_rejects_banana_unsupported_resolution(app):
    from huishi.routes_workspace import parse_provider_form
    with app.app_context(), app.test_request_context('/settings/providers', method='POST', data={
      'provider_type':'image','name':'x','base_url':'https://api.example.com','api_key':'key',
      'model':'gemini-3.1-flash-image','api_format':'banana','priority':'1','enabled':'1','resolutions':['4K']}):
        parse_provider_form()

def test_grok_4k_rejected_before_http(monkeypatch):
    called=[]
    monkeypatch.setattr(image_api, 'OpenAI', lambda **_: called.append(1))
    monkeypatch.setattr(image_api, 'current_app', type('App',(),{'config':{'IMAGE_API_TIMEOUT':10,'IMAGE_API_MAX_RETRIES':0}})())
    with pytest.raises(image_api.ConfigurationError, match='1K 或 2K'):
        image_api.generate_image(prompt='x', mode='text', ratio='1:1', resolution='4K', count=1, api_key='k', base_url='https://api.x.ai/v1', model='grok-imagine-image-2.0', api_format='grok')
    assert not called

def test_provider_json_error_redacts_key_and_sensitive_url(monkeypatch):
    class Response:
        status_code = 401
        text = 'invalid key sk-live-abcdef123456 at https://up.example/v1?api_key=query-secret&token=t-secret'
        def json(self):
            return {'error': {'message': self.text}}
    monkeypatch.setattr(image_api.requests, 'post', lambda *a, **k: Response())
    with pytest.raises(RuntimeError) as exc:
        image_api.post_provider_json('https://up.example/v1', headers={'Authorization': 'Bearer sk-live-abcdef123456'}, payload={}, timeout=1)
    message = str(exc.value)
    assert 'sk-live-abcdef123456' not in message
    assert 'query-secret' not in message and 't-secret' not in message

@pytest.mark.parametrize('detail', [
    'Authorization: Bearer opaque-credential-987654',
    'token: another-credential-987654',
])
def test_provider_json_error_redacts_unknown_credentials(monkeypatch, detail):
    class Response:
        status_code = 401
        text = detail
        def json(self):
            return {'error': {'message': self.text}}
    monkeypatch.setattr(image_api.requests, 'post', lambda *a, **k: Response())
    with pytest.raises(RuntimeError) as exc:
        image_api.post_provider_json('https://up.example/v1', headers={}, payload={}, timeout=1)
    assert detail.split()[-1] not in str(exc.value)

@pytest.mark.parametrize('api_key', ['gemini-unknown-key-987654', 'banana-unknown-key-987654'])
def test_provider_json_error_redacts_google_key(monkeypatch, api_key):
    class Response:
        status_code = 403
        text = f'bad key {api_key}'
        def json(self):
            return {'message': self.text}
    monkeypatch.setattr(image_api.requests, 'post', lambda *a, **k: Response())
    with pytest.raises(RuntimeError) as exc:
        image_api.post_provider_json('https://generativelanguage.googleapis.com/v1beta/interactions', headers={'x-goog-api-key': api_key}, payload={}, timeout=1)
    assert api_key not in str(exc.value)

def test_generation_error_sanitizer_redacts_credentials():
    from huishi.routes_workspace import _sanitize_generation_error_message
    message = 'upstream failed api_key=sk-live-abcdef123456 Authorization: Bearer tok-secret https://up.example/x?secret=url-secret'
    safe = _sanitize_generation_error_message(message)
    assert 'sk-live-abcdef123456' not in safe
    assert 'tok-secret' not in safe and 'url-secret' not in safe
    assert '模型与调用协议不匹配' in _sanitize_generation_error_message('模型与调用协议不匹配')
    assert 'Grok 官方生图仅支持 1K 或 2K' in _sanitize_generation_error_message('Grok 官方生图仅支持 1K 或 2K')
    assert 'tokenization_failed' in _sanitize_generation_error_message('tokenization_failed while processing prompt')
    assert 'OpenAI Base URL is unreachable' in _sanitize_generation_error_message('OpenAI Base URL is unreachable')
    assert '[redacted]' in _sanitize_generation_error_message('Authorization: ApiKey abc.def/ghi')

def test_metadata_drives_banana_request_path(app, monkeypatch):
    captured = {}
    class Response:
        status_code = 200
        text = ''
        def json(self): return {'output_image': {'data': 'aGk=', 'mime_type': 'image/png'}}
    monkeypatch.setattr(image_api.requests, 'post', lambda url, **kwargs: (captured.update(url=url), Response())[1])
    monkeypatch.setattr(image_api, 'current_app', type('App', (), {'config': {'IMAGE_API_TIMEOUT': 10, 'IMAGE_API_MAX_RETRIES': 0}})())
    monkeypatch.setitem(providers.IMAGE_PROVIDER_METADATA['banana'], 'interactions_path', '/custom/banana')
    with app.app_context():
        image_api.generate_image(prompt='x', mode='text', ratio='1:1', resolution='1K', count=1, api_key='k', base_url='https://g.example', model='gemini-3.1-flash-image', api_format='banana')
    assert captured['url'] == 'https://g.example/custom/banana'

@pytest.mark.parametrize('api_format, path', [('gemini', '/custom/gemini'), ('banana', '/custom/banana')])
def test_metadata_drives_actual_gemini_protocol_path(app, monkeypatch, api_format, path):
    captured = {}
    class Response:
        status_code = 200
        text = ''
        def json(self): return {'output_image': {'data': 'aGk=', 'mime_type': 'image/png'}}
    monkeypatch.setattr(image_api.requests, 'post', lambda url, **kwargs: (captured.update(url=url), Response())[1])
    monkeypatch.setattr(image_api, 'current_app', type('App', (), {'config': {'IMAGE_API_TIMEOUT': 10, 'IMAGE_API_MAX_RETRIES': 0}})())
    monkeypatch.setitem(providers.IMAGE_PROVIDER_METADATA[api_format], 'interactions_path', path)
    with app.app_context():
        image_api.generate_image(prompt='x', mode='text', ratio='1:1', resolution='1K', count=1, api_key='k', base_url='https://g.example', model='gemini-3.1-flash-image', api_format=api_format)
    assert captured['url'] == 'https://g.example' + path

def test_redact_url_removes_userinfo_and_generation_log(monkeypatch, caplog):
    from huishi.secrets import redact_url
    assert redact_url('https://user:password@example.com/v1?token=secret') == 'https://example.com/v1'
    monkeypatch.setattr(image_api, 'OpenAI', lambda **_: (_ for _ in ()).throw(RuntimeError('stop')))
    monkeypatch.setattr(image_api, 'current_app', type('App', (), {'config': {'IMAGE_API_TIMEOUT': 10, 'IMAGE_API_MAX_RETRIES': 0}})())
    with caplog.at_level('INFO'):
        with pytest.raises(RuntimeError):
            image_api.generate_image(prompt='x', mode='text', ratio='1:1', resolution='1K', count=1, api_key='password', base_url='https://user:password@example.com/v1?token=secret', model='gpt-image-2')
    assert 'password' not in caplog.text and 'user:' not in caplog.text and 'token=secret' not in caplog.text
