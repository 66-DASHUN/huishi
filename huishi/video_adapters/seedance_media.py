import base64
import binascii
import ipaddress
import posixpath
import socket
import time
from urllib.parse import unquote, urlsplit, urlunsplit

from huishi.media_capabilities import video_capabilities, validate_video_request
from huishi.video_api import VideoTask, VideoTaskState, VideoApiError, _normalize_status
from .common import (
    RetryableVideoError,
    VideoNotReadyError,
    error_text,
    is_response_format_error,
    request_json,
    require_idempotency,
    task_segment,
    unsupported_model_error,
)


_CATALOG_PATH = '/v1/catalog'
_BALANCE_PATH = '/v1/balance'
_FILES_PATH = '/v1/files'
_VIDEOS_PATH = '/v1/videos'


def _root_endpoint(provider, path):
    """Build an endpoint at the upstream site root.

    The Laogou Seedance gateway is configured with ``/seedance`` as its API
    prefix, but its signed download URL deliberately points at ``/v1`` on the
    site root.  Keeping this distinction here prevents the prefix from being
    accidentally added to download URLs.
    """
    parsed = urlsplit(str(provider.get('base_url') or '').strip().rstrip('/'))
    base_path = parsed.path.rstrip('/')
    if base_path.lower().endswith('/seedance'):
        base_path = base_path[:-len('/seedance')]
    origin = urlunsplit((parsed.scheme, parsed.netloc, base_path, '', '')).rstrip('/')
    return origin + '/' + str(path or '').lstrip('/')


def _origin_tuple(parsed):
    try:
        port = parsed.port
    except ValueError as exc:
        raise VideoApiError('Seedance 签名下载地址端口无效') from exc
    if not parsed.scheme or not parsed.hostname:
        raise VideoApiError('Seedance 签名下载地址来源无效')
    return (parsed.scheme.lower(), parsed.hostname.lower(), port or (443 if parsed.scheme.lower() == 'https' else 80))


def _validated_signed_url(provider, value, task_id=''):
    """Validate and resolve the URL returned by ``signed_url``.

    Laogou returns a root-relative path (for example
    ``/v1/videos/<id>/file``), while some compatible gateways return an
    absolute URL.  The URL must remain on the configured channel origin and
    inside the documented video file namespace; otherwise a compromised or
    malformed upstream response could turn the worker into an open fetcher.
    """
    raw = str(value or '').strip()
    parsed = urlsplit(raw)
    if not raw or parsed.fragment:
        raise VideoApiError('Seedance 签名下载地址无效')
    if parsed.netloc:
        if parsed.scheme.lower() not in {'http', 'https'} or parsed.username or parsed.password:
            raise VideoApiError('Seedance 签名下载地址来源无效')
        provider_origin = _origin_tuple(urlsplit(str(provider.get('base_url') or '').strip()))
        if _origin_tuple(parsed) != provider_origin:
            raise VideoApiError('Seedance 签名下载地址来源不匹配')
        scheme, netloc = parsed.scheme, parsed.netloc
    else:
        # Protocol-relative URLs (//host/path) are deliberately rejected.
        if parsed.scheme or not raw.startswith('/') or raw.startswith('//'):
            raise VideoApiError('Seedance 签名下载地址必须是同源地址')
        base = urlsplit(str(provider.get('base_url') or '').strip())
        scheme, netloc = base.scheme, base.netloc
        _origin_tuple(base)

    raw_path = parsed.path or ''
    decoded_path = unquote(raw_path)
    if '\\' in decoded_path or any(segment == '..' for segment in decoded_path.split('/')):
        raise VideoApiError('Seedance 签名下载地址包含非法路径')
    # Normalize the raw path for the outgoing URL so encoded delimiters such
    # as ``%3F`` remain encoded and the signed query string is preserved.
    normalized_path = posixpath.normpath(raw_path)
    normalized_decoded_path = unquote(normalized_path)
    path_parts = normalized_decoded_path.split('/')
    expected_task = str(task_id or '').strip()
    if (not normalized_path.startswith('/v1/videos/') or
            not normalized_decoded_path.startswith('/v1/videos/') or
            len(path_parts) != 5 or path_parts[1] != 'v1' or
            path_parts[2] != 'videos' or path_parts[4] != 'file' or
            (expected_task and path_parts[3] != expected_task)):
        raise VideoApiError('Seedance 签名下载地址路径不受支持')
    return urlunsplit((scheme, netloc, normalized_path, parsed.query, ''))


def _validate_public_image_url(value):
    raw = str(value or '').strip()
    parsed = urlsplit(raw)
    if (not raw or len(raw) > 2048 or parsed.scheme.lower() != 'https' or
            not parsed.hostname or parsed.username or parsed.password or parsed.fragment):
        raise VideoApiError('参考图地址必须是公网 HTTPS 地址')
    try:
        port = parsed.port or 443
    except ValueError as exc:
        raise VideoApiError('参考图地址必须是公网 HTTPS 地址') from exc
    hostname = parsed.hostname.rstrip('.').lower()
    if not hostname:
        raise VideoApiError('参考图地址必须是公网 HTTPS 地址')
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise VideoApiError('参考图地址必须是公网 HTTPS 地址')
    if address is None:
        try:
            resolved = socket.getaddrinfo(
                hostname,
                port,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
            )
        except (OSError, TypeError, UnicodeError, ValueError) as exc:
            raise VideoApiError('参考图地址必须是公网 HTTPS 地址') from exc
        if not resolved:
            raise VideoApiError('参考图地址必须是公网 HTTPS 地址')
        for result in resolved:
            try:
                resolved_address = ipaddress.ip_address(result[4][0])
            except (IndexError, KeyError, TypeError, ValueError) as exc:
                raise VideoApiError('参考图地址必须是公网 HTTPS 地址') from exc
            if not resolved_address.is_global:
                raise VideoApiError('参考图地址必须是公网 HTTPS 地址')
    if hostname in {'localhost', 'localhost.localdomain'}:
        raise VideoApiError('参考图地址必须是公网 HTTPS 地址')
    return raw


def _image_urls(request, normalized):
    urls = []
    configured = request.get('image_urls') or []
    if isinstance(configured, (str, bytes)) or not isinstance(configured, list):
        raise VideoApiError('参考图地址格式错误')
    for value in configured:
        value = _validate_public_image_url(value)
        if value not in urls:
            urls.append(value)
    for item in normalized.get('content') or []:
        if not isinstance(item, dict) or item.get('type') != 'image_url':
            continue
        nested = item.get('image_url')
        value = str(nested.get('url') or '').strip() if isinstance(nested, dict) else ''
        if value:
            value = _validate_public_image_url(value)
            if value not in urls:
                urls.append(value)
    return urls


def _catalog_entries(result):
    entries = result.get('models') if isinstance(result, dict) else result
    if isinstance(entries, dict):
        # Some catalog implementations use a model-id keyed object rather
        # than an array.  Preserve the key as the model id.
        entries = [dict(value, id=key) if isinstance(value, dict) else {'id': key}
                   for key, value in entries.items()]
    if not isinstance(entries, list) and isinstance(result, dict):
        data = result.get('data')
        entries = data.get('models') if isinstance(data, dict) else data
    return entries if isinstance(entries, list) else []


def _catalog_config(result, item):
    configured = {}
    source = result if isinstance(result, dict) else {}
    # The gateway may advertise a field globally or on an individual model.
    aliases = {
        'max_ref_images': 'max_reference_images',
        'max_reference_images': 'max_reference_images',
        'max_images': 'max_reference_images',
        'max_image_bytes': 'max_image_bytes',
        'max_images_total_bytes': 'max_images_total_bytes',
        'durations': 'durations',
        'duration': 'durations',
        'duration_seconds': 'durations',
        'ratios': 'ratios',
        'resolutions': 'resolutions',
        'camera_movement': 'camera_movement',
    }
    for source_item in (source, item if isinstance(item, dict) else {}):
        for key, target in aliases.items():
            if key not in source_item:
                continue
            value = source_item[key]
            if target == 'durations' and not isinstance(value, list):
                value = [value]
            configured[target] = value
    return configured


def create(provider, request):
    key = require_idempotency(request)
    model = str(request.get('model') or provider.get('model') or '')
    caps = video_capabilities('seedance_media', model)
    if not caps:
        raise unsupported_model_error('Seedance Media', model)
    try:
        normalized = validate_video_request(model, caps, request)
    except ValueError as exc:
        raise VideoApiError(str(exc)) from exc
    images = _image_urls(request, normalized)
    # ``image_ids`` are IDs returned by the documented /v1/files endpoint.
    # Accept the old internal name as input for queued tasks, but never send
    # the non-documented ``file_ids`` field upstream.
    image_ids = list(request.get('image_ids') or request.get('file_ids') or [])
    image_ids = [str(value).strip() for value in image_ids if str(value).strip()]
    if len(images) + len(image_ids) > caps['max_reference_images']:
        raise VideoApiError('参考图片数量超过模型限制')
    payload = {k: normalized[k] for k in ('model', 'prompt', 'resolution', 'ratio', 'camera_movement')}
    payload.update(duration=normalized['duration_seconds'], image_ids=image_ids, image_urls=images)
    result = request_json(provider, 'POST', _VIDEOS_PATH, payload=payload, idempotency_key=key,
                          expected_statuses={202})
    task_id = str(result.get('id') or result.get('task_id') or '')
    data = result.get('data') if isinstance(result.get('data'), dict) else {}
    task_id = task_id or str(data.get('id') or data.get('task_id') or '')
    if not task_id:
        raise RetryableVideoError('Seedance 已返回响应但缺少任务 ID，等待原幂等键恢复')
    return VideoTask(task_id, status=str(result.get('status') or data.get('status') or 'pending'))


def poll(provider, task_id):
    task = request_json(provider, 'GET', _VIDEOS_PATH + '/' + task_segment(task_id),
                        expected_statuses={200})
    data = task.get('data') if isinstance(task.get('data'), dict) else task
    raw_status = str(data.get('status') or '').strip().lower()
    if raw_status in {'queued', 'running'}:
        status = 'pending'
    elif raw_status == 'succeeded':
        status = 'completed'
    elif raw_status in {'failed', 'cancelled', 'expired'}:
        status = 'failed'
    else:
        raise RetryableVideoError(f'Seedance 返回未知任务状态: {raw_status or "空"}')
    if status == 'failed':
        return VideoTaskState('failed', error=error_text(data.get('error'), provider), file_id=str(task_id))
    return VideoTaskState(status, file_id=str(task_id))


def upload_image(provider, image_b64):
    raw = str(image_b64 or '').strip()
    if raw.lower().startswith('data:'):
        header, separator, raw = raw.partition(',')
        if not separator or ';base64' not in header.lower():
            raise VideoApiError('Seedance 图片 Base64 格式无效')
    raw = ''.join(raw.split())
    if not raw:
        raise VideoApiError('Seedance 图片 Base64 不能为空')
    try:
        decoded = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise VideoApiError('Seedance 图片 Base64 格式无效') from exc
    if not decoded:
        raise VideoApiError('Seedance 图片内容为空')
    if len(decoded) > 12 * 1024 * 1024:
        raise VideoApiError('Seedance 单张参考图片不能超过12MiB')
    result = request_json(provider, 'POST', _FILES_PATH, payload={'image_b64': raw},
                          expected_statuses={201})
    data = result.get('data') if isinstance(result.get('data'), dict) else result
    if not data.get('image_id'):
        raise VideoApiError('Seedance 上传响应缺少 image_id')
    return result


def balance(provider):
    """Return the upstream account balance for an administrator probe."""
    return request_json(provider, 'GET', _BALANCE_PATH, expected_statuses={200})


def download(provider, state, *, timeout=120, destination=None):
    """Resolve Laogou's signed URL and download the root-path media file."""
    from huishi.media_download import download_media

    task_id = str(state.file_id or '').strip()
    if not task_id:
        raise VideoApiError('Seedance 任务缺少下载 ID')
    signed = None
    for attempt in range(3):
        try:
            signed = request_json(
                provider,
                'GET',
                _VIDEOS_PATH + '/' + task_segment(task_id) + '/signed_url',
                expected_statuses={200},
                not_ready_statuses={409},
            )
            break
        except VideoNotReadyError:
            if attempt >= 2:
                # Preserve the more specific transient state so the worker can
                # schedule another poll without moving an accepted task into
                # manual reconciliation.
                raise VideoNotReadyError('HTTP 409: Seedance 视频结果准备中')
            time.sleep(1)
    data = signed.get('data') if isinstance(signed.get('data'), dict) else signed
    value = str(data.get('url') or '').strip()
    if not value:
        raise RetryableVideoError('Seedance 签名下载地址为空')
    value = _validated_signed_url(provider, value, task_id)
    return download_media(provider, value, authenticated=True, timeout=timeout, destination=destination)


def models(provider):
    try:
        result = request_json(provider, 'GET', _CATALOG_PATH, allow_list=True, expected_statuses={200})
    except RetryableVideoError as exc:
        # The current Laogou deployment serves its web shell at /v1/catalog
        # even though the documented endpoint is enabled.  Keep real HTTP,
        # auth, and transport failures visible; only a successful non-JSON
        # response can safely use the documented static capability snapshot.
        #
        # 用标记判断而不是比较错误字符串：文案属于展示层，改一个字就会让这里的
        # 降级静默失效（变成把"上游返回网页"当成硬故障抛出），且没有任何测试
        # 会红。标记由 common.response_format_error 打上、并经 request_json
        # 的重新包装透传过来。
        if not is_response_format_error(exc):
            raise
        return _builtin_catalog()
    entries = _catalog_entries(result)
    if not isinstance(entries, list) or not entries:
        raise VideoApiError('Seedance 模型目录为空或格式错误')
    models = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        model = str(item.get('id') or item.get('model') or item.get('name') or '').strip()
        configured = _catalog_config(result, item)
        caps = video_capabilities('seedance_media', model, configured)
        if not caps:
            continue
        models.append(dict(id=model, label=str(item.get('label') or item.get('display_name') or model), media_type='video',
            api_format='seedance_media', capabilities=caps, capability_source='remote', enabled=False))
    if not models:
        raise VideoApiError('Seedance 目录没有已适配的模型')
    return models


def _builtin_catalog():
    labels = {
        'seedance2.5': 'Seedance 2.5',
        'seedance2.0': 'Seedance 2.0',
        'seedance2.0fast': 'Seedance 2.0 Fast',
        'seedance2.0mini': 'Seedance 2.0 Mini',
    }
    return [
        dict(
            id=model,
            label=labels[model],
            media_type='video',
            api_format='seedance_media',
            capabilities=video_capabilities('seedance_media', model),
            capability_source='builtin-fallback',
            enabled=False,
        )
        for model in ('seedance2.5', 'seedance2.0', 'seedance2.0fast', 'seedance2.0mini')
    ]
