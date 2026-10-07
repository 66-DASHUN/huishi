from huishi.media_capabilities import video_capabilities, validate_video_request
from huishi.video_api import VideoTask, VideoTaskState, VideoApiError, _normalize_status
from .common import RetryableVideoError, error_text, request_json, require_idempotency, task_segment, unsupported_model_error


def create(provider, request):
    key = require_idempotency(request)
    model = str(request.get('model') or provider.get('model') or '')
    caps = video_capabilities('dmc_h3', model)
    if not caps:
        raise unsupported_model_error('DMC H3', model)
    try:
        normalized = validate_video_request(model, caps, request)
    except ValueError as exc:
        raise VideoApiError(str(exc)) from exc
    payload = {k: normalized[k] for k in ('model', 'content', 'resolution', 'ratio')}
    payload['duration'] = normalized['duration_seconds']
    result = request_json(provider, 'POST', '/v2/video_generation', payload=payload, idempotency_key=key)
    if not result.get('task_id'):
        raise RetryableVideoError('H3 已返回响应但缺少任务 ID，等待原幂等键恢复')
    return VideoTask(str(result['task_id']))


def poll(provider, task_id):
    result = request_json(provider, 'GET', '/v2/query/video_generation/' + task_segment(task_id))
    task = result.get('task')
    if not isinstance(task, dict):
        raise RetryableVideoError('H3 查询响应缺少 task')
    status = _normalize_status(task.get('status'))
    if status == 'failed':
        return VideoTaskState('failed', error=error_text(task.get('error'), provider))
    content = task.get('content') or {}
    url = str(content.get('url') or '') if isinstance(content, dict) else ''
    if status == 'completed' and not url.startswith('https://'):
        raise RetryableVideoError('H3 已生成，等待有效 HTTPS 下载地址')
    return VideoTaskState(status, url=url)
