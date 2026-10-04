"""Shared connection admission and deliberately small, safe task route snapshots."""
import json
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone

from flask import current_app
from huishi.db import get_db
from huishi.generation_limits import InMemoryGenerationLimiter, RedisGenerationLimiter

_memory_lock = threading.Lock()


@contextmanager
def channel_capacity(provider):
    """Limit API calls on one connection across models/media, not remote video jobs.

    Admission is nonblocking, so callers never hold a DB transaction while waiting.
    Redis failures propagate; only isolated testing explicitly permits local state.
    """
    settings = provider.get('settings') or {}
    concurrency = max(0, int(settings.get('max_concurrency') or 0))
    rpm = max(0, int(settings.get('requests_per_minute') or 0))
    if not concurrency and not rpm:
        yield
        return
    app = current_app._get_current_object()
    channel_id = provider.get('id')
    if channel_id is None:
        raise RuntimeError('Shared channel limits require a saved channel')
    namespace = f"{app.config.get('RATE_LIMIT_NAMESPACE','huishi')}:channel:{channel_id}"
    redis_url = str(app.config.get('REDIS_URL') or '').strip()
    options = dict(max_concurrency=concurrency or 2147483647, rpm=rpm or 2147483647)
    if redis_url:
        from redis import Redis
        limiter = RedisGenerationLimiter(Redis.from_url(redis_url), namespace=namespace,
            active_ttl_seconds=max(900, int(app.config.get('RQ_JOB_TIMEOUT_SECONDS',1200))), **options)
    elif app.testing:
        with _memory_lock:
            cache = app.extensions.setdefault('channel_generation_limiters', {})
            key = (channel_id, concurrency, rpm)
            limiter = cache.setdefault(key, InMemoryGenerationLimiter(**options))
    else:
        raise RuntimeError('Redis must be configured for shared channel generation limits')
    with limiter.acquire():
        yield


def safe_route(provider, model=None):
    from huishi.model_lifecycle import upstream_model
    model = model or provider.get('model') or ''
    entry = next((e for e in provider.get('models', []) if e['id']==model), {})
    return dict(provider_id=provider.get('id'), provider_name=str(provider.get('name') or ''),
        model=model, upstream_id=upstream_model(provider,model),
        api_format=entry.get('api_format') or provider.get('api_format') or '')


def begin_task_route(task_id, provider, model=None):
    from huishi.records import get_generation_task
    task = get_generation_task(task_id)
    if task is None:
        raise RuntimeError('Generation task no longer exists')
    metadata = dict(task.get('metadata') or {})
    metadata['route'] = safe_route(provider,model)
    metadata.setdefault('quote', {key:task.get(key) for key in
        ('cost','count','model','media_type','mode','resolution','ratio','quality','duration_seconds','output_format')})
    timing = metadata.setdefault('timing', {})
    if 'queue_ms' not in timing:
        try:
            created=datetime.fromisoformat(str(task['created_at']).replace('Z','+00:00'))
            if created.tzinfo is None:
                created=created.replace(tzinfo=timezone.utc)
            timing['queue_ms']=max(0,round((time.time()-created.timestamp())*1000))
        except (ValueError,TypeError):
            timing['queue_ms']=0
    metadata.update(phase='submitting',storage_status='pending')
    get_db().execute('UPDATE generation_tasks SET provider_id=?, metadata_json=? WHERE id=?',
        (provider.get('id'),json.dumps(metadata,ensure_ascii=False),task_id))
    get_db().commit()
    return metadata


def finish_task_route(task_id, *, upstream_ms=None, phase=None, storage_status=None):
    from huishi.records import get_generation_task
    task=get_generation_task(task_id)
    if task is None:
        return
    metadata=dict(task.get('metadata') or {})
    if upstream_ms is not None:
        metadata.setdefault('timing',{})['upstream_ms']=max(0,round(upstream_ms))
    if phase:
        metadata['phase']=phase
    if storage_status:
        metadata['storage_status']=storage_status
    get_db().execute('UPDATE generation_tasks SET metadata_json=? WHERE id=?',
        (json.dumps(metadata,ensure_ascii=False),task_id))
