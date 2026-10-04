from urllib.parse import quote
import requests
from huishi.network import request_proxy_kwargs
from huishi.secrets import redact_sensitive_text
from huishi.video_api import VideoApiError, _json, _headers, _url


class RetryableVideoError(VideoApiError):
    """The upstream state is uncertain; preserve the task and its reservation."""


class VideoNotReadyError(RetryableVideoError):
    """The accepted upstream task exists, but its result is not downloadable yet."""


def endpoint(provider, path):
    base = str(provider.get('base_url') or '').rstrip('/')
    for prefix in ('/v1/media', '/v2'):
        if base.endswith(prefix) and path.startswith(prefix + '/'):
            return base + path[len(prefix):]
    return _url(base, path)


def task_segment(task_id):
    return quote(str(task_id), safe='')


def request_json(provider, method, path, *, payload=None, idempotency_key='', allow_list=False,
                 expected_statuses=None, not_ready_statuses=()):
    headers = _headers(provider)
    if idempotency_key:
        headers['Idempotency-Key'] = idempotency_key
    kwargs = dict(headers=headers, timeout=(15, 60), allow_redirects=False,
                  **request_proxy_kwargs(provider.get('proxy_url')))
    if payload is not None:
        kwargs['json'] = payload
    try:
        response = (requests.post if method == 'POST' else requests.get)(endpoint(provider, path), **kwargs)
    except requests.RequestException as exc:
        raise RetryableVideoError(redact_sensitive_text(str(exc), provider.get('api_key'))) from exc
    expected = set(expected_statuses or ())
    status_ok = response.status_code in expected if expected else 200 <= response.status_code < 300
    if response.status_code in set(not_ready_statuses or ()):
        raise VideoNotReadyError(f'HTTP {response.status_code}: 视频结果准备中')
    if not status_ok:
        try:
            body = response.json()
            error = body.get('error', body) if isinstance(body, dict) else body
            message = error.get('message') or error.get('msg') if isinstance(error, dict) else error
        except ValueError:
            message = ''
        error_type = RetryableVideoError if response.status_code in (408, 409, 425, 429) or response.status_code >= 500 else VideoApiError
        raise error_type(redact_sensitive_text(f'HTTP {response.status_code}: {message or "渠道请求失败"}', provider.get('api_key')))
    try:
        if allow_list:
            try:
                result = response.json()
            except ValueError as exc:
                raise VideoApiError("视频接口返回的不是 JSON") from exc
            if not isinstance(result, (dict, list)):
                raise VideoApiError("视频接口返回格式不支持")
            return result
        return _json(response)
    except VideoApiError as exc:
        # A malformed create response might still represent an accepted task.
        raise RetryableVideoError(str(exc)) from exc


def error_text(error, provider):
    if isinstance(error, dict):
        error = ': '.join(str(error.get(key) or '') for key in ('code', 'message')).strip(': ')
    return redact_sensitive_text(str(error or '视频生成失败'), provider.get('api_key'))


def require_idempotency(request):
    value = str(request.get('idempotency_key') or '')
    if not value or len(value) > 200 or '\r' in value or '\n' in value:
        raise VideoApiError('视频提交必须使用持久保存的幂等键')
    return value
