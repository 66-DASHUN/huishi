from __future__ import annotations

import logging
import json
import math
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
from typing import Any

from flask import Flask

from huishi.db import close_db, get_db, transaction, immediate_transaction, utc_now
from huishi.generation_limits import InMemoryGenerationLimiter, RedisGenerationLimiter
from huishi.image_api import ConfigurationError, generate_image
from huishi.secrets import sanitize_generation_error_message
from huishi.audio_api import AudioApiError, generate_music, generate_speech
from huishi.providers import generate_image_with_failover
from huishi.providers import audio_provider_candidates, video_provider_candidates, get_provider
from huishi.route_runtime import channel_capacity, begin_task_route, finish_task_route
from huishi.records import (
    get_generation_task,
    mark_generation_task_failed,
    mark_generation_task_running,
    mark_generation_task_succeeded,
)
from huishi.user_key import get_user_provider
from huishi.upload_storage import get_upload_storage
from huishi.video_api import VideoApiError, create_video_task, download_video_result, poll_video_task


logger = logging.getLogger(__name__)
_executor: ThreadPoolExecutor | None = None
_memory_limiter: InMemoryGenerationLimiter | None = None


def get_generation_executor(app: Flask) -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        workers = int(app.config.get("GENERATION_WORKERS", 3))
        _executor = ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="huishi-generation")
    return _executor


def enqueue_generation_task(app: Flask, task_id: int, cleanup_paths: list[str] | None = None) -> None:
    if app.config.get("GENERATION_INLINE"):
        run_generation_task(app, task_id, cleanup_paths or [])
        return
    backend = str(app.config.get("GENERATION_QUEUE_BACKEND", "thread")).strip().lower()
    if backend == "rq":
        queue = get_rq_queue(app)
        queue.enqueue(
            run_generation_task_from_import_path,
            str(app.config.get("APP_IMPORT_PATH", "app:create_app")),
            task_id,
            cleanup_paths or [],
            job_timeout=effective_rq_job_timeout_seconds(app),
            result_ttl=int(app.config.get("RQ_RESULT_TTL_SECONDS", 60)),
            failure_ttl=int(app.config.get("RQ_FAILURE_TTL_SECONDS", 86400)),
        )
        return
    if backend not in {"thread", "threads"}:
        raise RuntimeError(f"Unsupported generation queue backend: {backend}")
    get_generation_executor(app).submit(run_generation_task, app, task_id, cleanup_paths or [])


def effective_rq_job_timeout_seconds(app: Flask) -> int:
    configured = int(app.config.get("RQ_JOB_TIMEOUT_SECONDS", 1200))
    wait_timeout = float(app.config.get("GENERATION_LIMIT_WAIT_TIMEOUT_SECONDS", 840))
    provider_timeout = float(app.config.get("IMAGE_API_TIMEOUT", 180))
    safe_floor = math.ceil(wait_timeout + provider_timeout + 60)
    return max(configured, safe_floor)


def get_rq_queue(app: Flask):
    redis_url = str(app.config.get("REDIS_URL") or "").strip()
    if not redis_url:
        raise RuntimeError("HUISHI_REDIS_URL must be set when HUISHI_GENERATION_QUEUE_BACKEND=rq")
    try:
        from redis import Redis
        from rq import Queue
    except ImportError as exc:
        raise RuntimeError("Install redis and rq to use HUISHI_GENERATION_QUEUE_BACKEND=rq") from exc
    connection = Redis.from_url(redis_url)
    return Queue(str(app.config.get("RQ_QUEUE_NAME", "huishi-generation")), connection=connection)


def get_generation_limiter(app: Flask):
    redis_url = str(app.config.get("REDIS_URL") or "").strip()
    max_concurrency = int(app.config.get("UPSTREAM_MAX_CONCURRENCY", 240))
    rpm = int(app.config.get("UPSTREAM_RPM_LIMIT", 300))
    if redis_url:
        try:
            from redis import Redis
        except ImportError as exc:
            raise RuntimeError("Install redis to use shared generation limits") from exc
        return RedisGenerationLimiter(
            Redis.from_url(redis_url),
            namespace=str(app.config.get("RATE_LIMIT_NAMESPACE", "huishi")),
            max_concurrency=max_concurrency,
            rpm=rpm,
            active_ttl_seconds=effective_rq_job_timeout_seconds(app),
        )
    if not app.testing:
        raise RuntimeError('Redis must be configured for shared generation limits')
    global _memory_limiter
    if _memory_limiter is None or _memory_limiter.max_concurrency != max_concurrency or _memory_limiter.rpm != rpm:
        _memory_limiter = InMemoryGenerationLimiter(max_concurrency=max_concurrency, rpm=rpm)
    return _memory_limiter


def run_generation_task_from_import_path(app_import_path: str, task_id: int, cleanup_paths: list[str] | None = None) -> None:
    module_name, factory_name = app_import_path.split(":", 1)
    factory = getattr(import_module(module_name), factory_name)
    app = factory()
    run_generation_task(app, task_id, cleanup_paths or [])


def run_generation_task(app: Flask, task_id: int, cleanup_paths: list[str] | None = None) -> None:
    with app.app_context():
        generated_output_paths: list[str] = []
        try:
            task = get_generation_task(task_id)
            if task is None:
                return
            if str(task.get("media_type") or "image") == "video":
                run_video_generation_task(app, task_id, cleanup_paths or [])
                return
            if str(task.get("media_type") or "image") in {"speech", "music"}:
                run_audio_generation_task(app, task_id, cleanup_paths or [])
                return
            from huishi import routes_workspace

            reference_images = routes_workspace.load_reference_images(task.get("reference_paths") or [])

            bypass_billing = bool(task.get("bypass_billing"))
            user_provider = None
            if bypass_billing:
                user_provider = get_user_provider(
                    int(task["user_id"]),
                    model=str(task.get("model") or ""),
                    resolution=str(task["resolution"]),
                )
                if user_provider is None:
                    bypass_billing = False

            limiter = get_generation_limiter(app)
            wait_timeout = float(app.config.get("GENERATION_LIMIT_WAIT_TIMEOUT_SECONDS", 840))
            # PostgreSQL SELECTs open a transaction too; release it before capacity waits.
            get_db().commit()
            try:
                lease = limiter.acquire(
                    block=True,
                    timeout_seconds=wait_timeout,
                    sleep_seconds=float(app.config.get("GENERATION_LIMIT_WAIT_SLEEP_SECONDS", 1.0)),
                )
            except TypeError:
                lease = limiter.acquire()
            with lease:
                current_task = get_generation_task(task_id)
                if current_task is None or current_task["status"] != "queued":
                    return
                task = current_task
                mark_generation_task_running(task_id)
                get_db().commit()
                if bypass_billing and user_provider:
                    # Personal credentials are never copied into the task snapshot.
                    personal_route={**user_provider,'id':None,'name':'Personal API key'}
                    begin_task_route(task_id,personal_route,str(task.get('model') or user_provider['model']))
                    started=time.monotonic()
                    try:
                        result = generate_image(
                            prompt=str(task["prompt"]),
                            mode=str(task["mode"]),
                            ratio=str(task["ratio"]),
                            resolution=str(task["resolution"]),
                            count=int(task["count"]),
                            quality=str(task["quality"]),
                            output_format=str(task["output_format"]),
                            reference_images=reference_images,
                            api_key=user_provider["api_key"],
                            base_url=user_provider["base_url"],
                            model=str(task.get("model") or user_provider["model"]),
                            api_format=user_provider["api_format"],
                            proxy_url=str(user_provider.get("proxy_url") or ""),
                        )
                    finally:
                        finish_task_route(task_id,upstream_ms=(time.monotonic()-started)*1000)
                        get_db().commit()
                else:
                    bypass_billing = False
                    result = generate_image_with_failover(
                        task_id=task_id,
                        prompt=str(task["prompt"]),
                        mode=str(task["mode"]),
                        ratio=str(task["ratio"]),
                        resolution=str(task["resolution"]),
                        count=int(task["count"]),
                        quality=str(task["quality"]),
                        output_format=str(task["output_format"]),
                        reference_images=reference_images,
                        model=str(task.get("model") or ""),
                    )
            generated_output_paths = list(result.get("image_paths") or ([result["image_path"]] if result.get("image_path") else []))
            with transaction():
                record_id = finalize_generation_task(task, result, bypass_billing=bypass_billing, commit=False)
                mark_generation_task_succeeded(task_id, record_id)
                finish_task_route(task_id,phase='completed',storage_status='saved')
        except (ConfigurationError, ValueError) as exc:
            mark_generation_task_failed(task_id, str(exc))
            finish_task_route(task_id,phase='failed',storage_status='failed')
            get_db().commit()
            cleanup_generation_outputs(generated_output_paths)
            cleanup_generation_inputs(cleanup_paths)
        except RuntimeError as exc:
            mark_generation_task_failed(task_id, f"生成失败：{exc}")
            finish_task_route(task_id,phase='failed',storage_status='failed')
            get_db().commit()
            cleanup_generation_outputs(generated_output_paths)
            cleanup_generation_inputs(cleanup_paths)
        except Exception as exc:
            logger.exception("generation worker failed task_id=%s", task_id)
            # 把真实原因也写进任务记录，而不是只留一句"生成结果保存失败"。
            #
            # 这句话原先是不带任何细节的兜底文案，真实堆栈只进容器日志——
            # 而这个分支恰恰覆盖"没人预料到的异常"，最需要能直接看到原因。
            # 2026-10-06 排查那批失败时，只能靠翻 worker 的按天日志才定位到
            # 是 task_id 被透传进 generate_image() 引发 TypeError；日志一旦
            # 轮转或容器重建，现场就没了。
            #
            # 入库前必须脱敏：错误消息可能回显上游凭据或内部地址，而
            # _finalize / 前端展示都会把它带给用户。
            detail = sanitize_generation_error_message(f"{type(exc).__name__}: {exc}")
            mark_generation_task_failed(
                task_id,
                f"生成结果保存失败（{detail}）" if detail else "生成结果保存失败",
            )
            finish_task_route(task_id,phase='failed',storage_status='failed')
            get_db().commit()
            cleanup_generation_outputs(generated_output_paths)
            cleanup_generation_inputs(cleanup_paths)
        finally:
            close_db()


def finalize_generation_task(
    task: dict[str, Any],
    result: dict[str, Any],
    *,
    bypass_billing: bool = False,
    commit: bool = True,
) -> int:
    from huishi.routes_workspace import _finalize_generation

    dialogue_id = task.get("dialogue_id")
    return _finalize_generation(
        user_id=int(task["user_id"]),
        prompt=str(task["prompt"]),
        mode=str(task["mode"]),
        ratio=str(task["ratio"]),
        resolution=str(task["resolution"]),
        count=int(task["count"]),
        quality=str(task["quality"]),
        output_format=str(task["output_format"]),
        model=str(task.get("model") or result.get("model_source") or ""),
        result=result,
        reference_paths=list(task.get("reference_paths") or []),
        dialogue_id=int(dialogue_id) if dialogue_id is not None else None,
        bypass_billing=bypass_billing,
        commit=commit,
        media_type=str(task.get("media_type") or "image"),
        duration_seconds=int(task.get("duration_seconds") or 0),
        cost_snapshot=int(task['cost']) // max(1,int(task['count'])),
    )


def run_video_generation_task(app: Flask, task_id: int, cleanup_paths: list[str] | None = None) -> None:
    """Run one server-owned video task and persist the result through UploadStorage."""
    from huishi.media_tasks import claim_task, save_phase, release_task, assert_owner, payload_hash
    from huishi.media_capabilities import CHANNEL_PROTOCOLS
    from huishi.video_adapters.common import RetryableVideoError
    from huishi.provider_tests import record_video_test_result
    from huishi.task_billing import settle_video_failure
    task = get_generation_task(task_id)
    if task is None or task['status'] not in ('queued', 'running'):
        return
    token = claim_task(task_id)
    if not token:
        return
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    try:
        task = get_generation_task(task_id)
        if task['status'] not in ('queued', 'running'):
            return
        metadata = dict(task.get('metadata') or {})
        if metadata.get('phase') == 'needs_reconciliation':
            return
        provider = get_provider(int(task['provider_id'])) if task.get('provider_id') else next(iter(video_provider_candidates(task.get('model'))), None)
        if not provider:
            save_phase(task_id, token, metadata, 'needs_reconciliation', recovery_error='原渠道不存在，请管理员核对')
            return
        entry = next((m for m in provider.get('models', []) if m['id'] == task.get('model')), {})
        provider['api_format'] = metadata.get('api_format') or entry.get('api_format') or provider['api_format']
        version = payload_hash({k: provider.get(k) for k in ('api_key', 'base_url', 'api_format')})
        if metadata.get('credential_version') and version != metadata['credential_version']:
            save_phase(task_id, token, metadata, 'needs_reconciliation', recovery_error='原渠道配置已变更，请核对后恢复')
            return
        metadata.update(credential_version=version, api_format=provider['api_format'])
        mark_generation_task_running(task_id)
        get_db().execute('UPDATE generation_tasks SET provider_id=? WHERE id=?', (provider['id'], task_id))
        get_db().commit()
        request_payload = metadata.get('normalized_request') or {
            'prompt': task['prompt'], 'model': task.get('model') or provider.get('model'),
            'ratio': task.get('ratio') or '16:9', 'resolution': task.get('resolution') or '720p',
            'duration_seconds': int(task.get('duration_seconds') or 6),
            **{key: metadata[key] for key in ('content','generate_audio','watermark','camera_movement','file_ids','image_urls') if key in metadata},
        }
        request_payload=dict(request_payload)
        # Public model remains on the task for billing; upstream identity is immutable.
        request_payload['model']=metadata.get('upstream_model') or request_payload['model']
        request_payload['idempotency_key'] = metadata.get('idempotency_key') or f'huishi-video-{task_id}-{secrets.token_hex(12)}'
        external_id = str(task.get('provider_task_id') or '')
        if not external_id:
            if metadata.get('phase') == 'submitting' and provider['api_format'] not in CHANNEL_PROTOCOLS:
                save_phase(task_id, token, metadata, 'needs_reconciliation', recovery_error='此旧渠道未声明幂等能力，请核对是否已受理')
                return
            try:
                with channel_capacity(provider):
                    route_metadata = begin_task_route(task_id,provider,task.get('model'))
                    route_metadata['route']['upstream_id'] = request_payload['model']
                    metadata.update({key:route_metadata[key] for key in ('route','quote','timing','storage_status')})
                    # Persist original submission data before making any external call.
                    save_phase(task_id, token, metadata, 'submitting', normalized_request=request_payload, idempotency_key=request_payload['idempotency_key'])
                    started=time.monotonic()
                    try:
                        external = create_video_task(provider, request_payload)
                    finally:
                        metadata.setdefault('timing',{})['upstream_ms']=round((time.monotonic()-started)*1000)
            except RetryableVideoError:
                raise
            except VideoApiError as exc:
                if provider['api_format'] in CHANNEL_PROTOCOLS:
                    with immediate_transaction():
                        assert_owner(task_id, token)
                        settle_video_failure(task, metadata, provider, str(exc), accepted=False)
                        mark_generation_task_failed(task_id, str(exc))
                        record_video_test_result(task,generation='failed',storage='not_tested',error=str(exc))
                    return
                raise RetryableVideoError(str(exc)) from exc
            with immediate_transaction():
                assert_owner(task_id, token)
                external_id = external.provider_task_id
                get_db().execute('UPDATE generation_tasks SET provider_task_id=?,updated_at=? WHERE id=?', (external_id,utc_now(),task_id))
        save_phase(task_id, token, metadata, 'polling')
        deadline = time.monotonic() + max(30, min(300, int(app.config.get('VIDEO_GENERATION_TIMEOUT_SECONDS', 1200))))
        state = None
        storage = get_upload_storage()
        filename = f'video_task_{task_id}.mp4'
        if not storage.exists(filename):
            while time.monotonic() < deadline:
                save_phase(task_id, token, metadata, 'polling')
                # Polling is an upstream API request too and shares the channel RPM.
                # Exhaustion defers recovery on the same accepted external task.
                with channel_capacity(provider):
                    state = poll_video_task(provider, external_id)
                if state.status == 'failed':
                    with immediate_transaction():
                        assert_owner(task_id, token)
                        settle_video_failure(task, metadata, provider, state.error or '上游视频生成失败', accepted=True)
                        mark_generation_task_failed(task_id, state.error or '上游视频生成失败')
                        record_video_test_result(task,generation='failed',storage='not_tested',error=state.error or '上游视频生成失败')
                    return
                if state.status == 'completed':
                    break
                time.sleep(min(30, max(1, float((provider.get('settings') or {}).get('poll_interval', 5)))))
            if state is None or state.status != 'completed':
                raise RetryableVideoError('视频仍在上游排队或生成')
            save_phase(task_id, token, metadata, 'persisting')
            if provider['api_format'] in CHANNEL_PROTOCOLS:
                import tempfile
                from pathlib import Path
                from huishi.media_references import inspect_video_file
                with tempfile.TemporaryDirectory(prefix='huishi-video-') as temporary:
                    destination=Path(temporary)/'result.mp4'
                    download_video_result(provider,state,destination=destination)
                    metadata['media_info']=inspect_video_file(destination)
                    storage.save_file(filename,destination,'video/mp4')
            else:
                content = download_video_result(provider, state)
                storage.save_bytes(filename, content, 'video/mp4')
        if provider['api_format'] in CHANNEL_PROTOCOLS and not metadata.get('media_info'):
            from huishi.media_references import inspect_video_file
            metadata['media_info']=inspect_video_file(storage.ensure_local(filename))
        public_path = storage.public_path(filename)
        save_phase(task_id, token, metadata, 'settling')
        from huishi.routes_workspace import _finalize_generation
        result = dict(image_path=public_path,image_paths=[public_path],actual_size=task.get('actual_size') or '1280x720',
                      model_source=task.get('model') or provider.get('model'),elapsed_seconds=0,mime_type='video/mp4')
        if metadata.get('media_info'):
            info=metadata['media_info']
            result.update(actual_size=f"{info['width']}x{info['height']}",duration_ms=info['duration_ms'])
        with immediate_transaction():
            # Lock the lease row through the settlement transaction.
            changed = get_db().execute('UPDATE media_task_leases SET lease_expires_at=? WHERE task_id=? AND owner_token=? AND lease_expires_at>?',
                                      (int(time.time())+180,task_id,token,int(time.time()))).rowcount
            if changed != 1:
                raise RuntimeError('视频任务租约已失效')
            existing = get_db().execute('SELECT record_id FROM media_task_settlements WHERE task_id=?',(task_id,)).fetchone()
            if existing:
                mark_generation_task_succeeded(task_id, existing['record_id'])
                return
            record_id = _finalize_generation(user_id=int(task['user_id']), prompt=task['prompt'], mode='video',
                ratio=task['ratio'],resolution=task['resolution'],count=1,quality=task['quality'],output_format='mp4',
                result=result,reference_paths=task.get('reference_paths') or [],dialogue_id=task.get('dialogue_id'),
                bypass_billing=bool(task.get('bypass_billing')),model=task.get('model') or '',asset_source='video',
                media_type='video',duration_seconds=int(task.get('duration_seconds') or 0),commit=False,cost_snapshot=int(task['cost']))
            get_db().execute('INSERT INTO media_task_settlements(task_id,record_id,points,settled_at) VALUES (?,?,?,?)',
                             (task_id,record_id,task['cost'],utc_now()))
            metadata['phase'] = 'completed'
            metadata['storage_status'] = 'saved'
            metadata['billing'] = dict(state='charged', reserved_points=0, charged_points=0 if task.get('bypass_billing') else int(task['cost']), released_points=0, settled_at=utc_now())
            get_db().execute('UPDATE generation_tasks SET metadata_json=? WHERE id=?',(json.dumps(metadata),task_id))
            mark_generation_task_succeeded(task_id,record_id)
            record_video_test_result(task,generation='passed',storage='passed')
    except Exception as exc:
        get_db().rollback()
        # The terminal transaction may have rolled back after mutating the
        # in-memory billing receipt. Recover only committed state.
        recovered = get_generation_task(task_id)
        metadata = dict((recovered or {}).get('metadata') or {})
        from huishi.secrets import redact_sensitive_text
        attempts = int(metadata.get('recovery_attempts') or 0) + 1
        # Any exception can leave the upstream side uncertain. Pause immediately
        # so maintenance never submits or polls again without an explicit admin
        # reconciliation. The original task, provider ID, reservation and error
        # metadata remain available for the manual recovery path.
        phase = 'needs_reconciliation'
        try:
            save_phase(task_id, token, metadata, phase, recovery_attempts=attempts,
                next_poll_at=0, recovery_error=redact_sensitive_text(str(exc)))
        except RuntimeError:
            get_db().rollback()
        logger.warning('video task awaiting recovery task_id=%s phase=%s',task_id,phase)
    finally:
        release_task(task_id, token)


def run_audio_generation_task(app: Flask, task_id: int, cleanup_paths: list[str] | None = None) -> None:
    """Run one speech/music task and persist the returned audio in upload storage."""
    task = get_generation_task(task_id)
    if task is None or task['status'] != 'queued':
        return
    media_type = str(task.get("media_type") or "").strip().lower()
    if media_type not in {"speech", "music"}:
        raise AudioApiError("不支持的音频任务类型")
    model = str(task.get("model") or "").strip()
    providers = audio_provider_candidates(media_type, model)
    provider_id = task.get("provider_id")
    if provider_id is not None:
        providers = [item for item in providers if int(item.get("id") or 0) == int(provider_id)]
    if not providers:
        raise AudioApiError("没有可用的音频 Provider，请到设置页添加并启用配置")
    provider = providers[0]
    metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    request_payload = {
        "model": model or str(provider.get("model") or ""),
        "text": str(task.get("prompt") or "") if media_type == "speech" else "",
        "prompt": str(task.get("prompt") or "") if media_type == "music" else "",
        "voice_id": str(metadata.get("voice_id") or "male-qn-qingse"),
        "speed": metadata.get("speed") or 1,
        "volume": metadata.get("volume") or 1,
        "pitch": metadata.get("pitch") or 0,
        "emotion": metadata.get("emotion") or "happy",
        "output_format": metadata.get("audio_format") or task.get("output_format") or "mp3",
        "lyrics": metadata.get("lyrics") or "",
        "lyrics_optimizer": bool(metadata.get("lyrics_optimizer")),
        "is_instrumental": bool(metadata.get("is_instrumental")),
        "audio_url": metadata.get("audio_url") or "",
        "audio_base64": metadata.get("audio_base64") or "",
    }
    # One atomic claimant; running tasks have unknown external acceptance and must not resubmit.
    claimed=get_db().execute("UPDATE generation_tasks SET status='running', provider_id=?, updated_at=? WHERE id=? AND status='queued'",
        (provider.get('id'),utc_now(),task_id)).rowcount
    get_db().commit()
    if claimed != 1:
        return
    limiter = get_generation_limiter(app)
    wait_timeout = float(app.config.get("GENERATION_LIMIT_WAIT_TIMEOUT_SECONDS", 840))
    try:
        try:
            lease = limiter.acquire(block=True, timeout_seconds=wait_timeout, sleep_seconds=float(app.config.get("GENERATION_LIMIT_WAIT_SLEEP_SECONDS", 1.0)))
        except TypeError:
            lease = limiter.acquire()
        with lease:
            current_task = get_generation_task(task_id)
            if current_task is None or current_task["status"] != "running":
                return
            from huishi.model_lifecycle import upstream_model
            request_payload['model']=upstream_model(provider,model)
            with channel_capacity(provider):
                begin_task_route(task_id,provider,model)
                started=time.monotonic()
                try:
                    result = generate_speech(provider, request_payload) if media_type == "speech" else generate_music(provider, request_payload)
                finally:
                    finish_task_route(task_id,upstream_ms=(time.monotonic()-started)*1000)
                    get_db().commit()
    except Exception:
        raise
    extension = str(result.get("extension") or "mp3").strip().lower() or "mp3"
    mime_type = str(result.get("mime_type") or "audio/mpeg")
    filename = f"{media_type}_{secrets.token_urlsafe(10)}.{extension}"
    public_path = get_upload_storage().save_bytes(filename, bytes(result["content"]), mime_type)
    try:
        from huishi.routes_workspace import _finalize_generation

        result_payload = {
            "image_path": public_path,
            "image_paths": [public_path],
            "actual_size": "",
            "model_source": model or str(provider.get("model") or ""),
            "elapsed_seconds": 0,
            "mime_type": mime_type,
            "duration_ms": int(result.get("duration_ms") or 0),
        }
        with transaction():
            record_id = _finalize_generation(
                user_id=int(task["user_id"]),
                prompt=str(task["prompt"]),
                mode=media_type,
                ratio="auto",
                resolution="default",
                count=1,
                quality="auto",
                output_format=extension,
                result=result_payload,
                reference_paths=list(task.get("reference_paths") or []),
                dialogue_id=task.get("dialogue_id"),
                bypass_billing=bool(task.get("bypass_billing")),
                model=model or str(provider.get("model") or ""),
                asset_source="audio",
                media_type=media_type,
                duration_seconds=int(result.get("duration_ms") or 0) // 1000,
                cost_snapshot=int(task['cost']),
                commit=False,
            )
            mark_generation_task_succeeded(task_id, record_id)
            finish_task_route(task_id,phase='completed',storage_status='saved')
    except Exception:
        cleanup_generation_outputs([public_path])
        raise


def cleanup_generation_inputs(paths: list[str] | None) -> None:
    if not paths:
        return
    from huishi.routes_workspace import cleanup_local_uploads

    cleanup_local_uploads(list(paths))


def cleanup_generation_outputs(paths: list[str] | None) -> None:
    if not paths:
        return
    from huishi.routes_workspace import cleanup_local_uploads

    cleanup_local_uploads(list(paths))

