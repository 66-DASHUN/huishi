"""One server-owned submission path for canvas, workbench and admin tests."""
import secrets
from huishi.db import get_db, immediate_transaction, lock_user_for_update
from huishi import providers
from huishi.billing import calculate_cost, require_available_generation_points
from huishi.media_capabilities import video_capabilities, validate_video_request, CHANNEL_PROTOCOLS
from huishi.media_tasks import request_replay, remember_request, payload_hash
from huishi.records import create_generation_task, get_generation_task, create_dialogue, get_dialogue_for_user, dialogue_title_from_prompt


def submit_video(app, user_id, payload, *, test_provider=None, identity_payload=None):
    from huishi.generation_queue import enqueue_generation_task
    key = str(payload.get('request_key') or secrets.token_hex(24))
    model = str(payload.get('model') or '').strip()
    incoming = {k: payload[k] for k in ('prompt','model','duration_seconds','seconds','ratio','resolution','content','camera_movement','generate_audio','watermark','references') if k in payload}
    if test_provider:
        incoming['test_provider_id'] = test_provider['id']
    identity = dict(incoming if identity_payload is None else identity_payload)
    dialogue_raw = str(payload.get('dialogue_id') or '').strip()
    try:
        dialogue_id = int(dialogue_raw) if dialogue_raw else None
    except ValueError as exc:
        raise ValueError('对话参数无效') from exc
    create_requested = str(payload.get('create_dialogue') or '') == '1'
    identity.update(dialogue_id=dialogue_id, create_dialogue=create_requested)
    # Check identity before mutable configuration/price validation.
    existing = request_replay(user_id,key,identity)
    if existing:
        return get_generation_task(existing)
    if dialogue_id is not None and not get_dialogue_for_user(dialogue_id, user_id):
        raise ValueError('对话不存在或不属于当前用户')
    if providers.get_app_settings('media_submissions_paused').get('media_submissions_paused') == '1':
        raise ValueError('服务正在更新，暂时停止接收新任务，请稍后重试')
    candidates = [test_provider] if test_provider else providers.video_provider_candidates(model)
    errors=[]
    for candidate in candidates:
        selected_model = model or candidate.get('model') or ''
        entry = next((m for m in candidate.get('models',[]) if m['id']==selected_model),{})
        protocol = entry.get('api_format') or candidate['api_format']
        caps = video_capabilities(protocol, entry.get('upstream_id') or selected_model,entry.get('capabilities'))
        try:
            if protocol in CHANNEL_PROTOCOLS and not caps:
                raise ValueError('当前渠道尚未适配此模型')
            normalized = {**incoming,'model':selected_model,'prompt':str(incoming.get('prompt') or '').strip()}
            # Prepared server-owned references are resolved before any upstream call.
            if incoming.get('references'):
                from huishi.media_references import prepare_references
                normalized = prepare_references(user_id,protocol,caps,normalized,incoming['references'])
            else:
                if protocol in CHANNEL_PROTOCOLS and any(item.get('type')!='text' for item in incoming.get('content',[]) if isinstance(item,dict)):
                    raise ValueError('请先上传参考素材，使用素材ID提交；不接受外部地址或Base64直传')
                normalized = validate_video_request(selected_model,caps,normalized)
            provider = {**candidate,'api_format':protocol}
            break
        except ValueError as exc:
            errors.append(str(exc))
    else:
        raise ValueError(errors[0] if errors else '没有可用的视频模型，请管理员配置并启用渠道')
    from huishi.model_lifecycle import upstream_model, test_fingerprint
    metadata = dict(normalized_request=normalized, api_format=protocol, phase='validated',upstream_model=upstream_model(provider,selected_model),
                    credential_version=payload_hash({k:provider.get(k) for k in ('api_key','base_url','api_format')}),
                    binding_fingerprint=test_fingerprint(provider,selected_model),
                    idempotency_key='huishi-'+secrets.token_hex(24), test_scope=bool(test_provider))
    with immediate_transaction():
        lock_user_for_update(user_id)
        existing = request_replay(user_id,key,identity)
        if existing:
            return get_generation_task(existing)
        cost = 0 if test_provider else calculate_cost('video',normalized['resolution'],1,model=selected_model,
            media_type='video',duration_seconds=normalized['duration_seconds'])
        require_available_generation_points(user_id,cost)
        from huishi.routes_workspace import require_active_generation_task_slot
        require_active_generation_task_slot(user_id)
        if dialogue_id is None and create_requested:
            dialogue_id = create_dialogue(user_id=user_id, title=dialogue_title_from_prompt(normalized['prompt']))
        metadata['billing'] = dict(state='reserved', reserved_points=cost, charged_points=0, released_points=0)
        tid=create_generation_task(user_id=user_id,prompt=normalized['prompt'],mode='video',media_type='video',
            model=selected_model,provider_id=provider['id'],ratio=normalized['ratio'],resolution=normalized['resolution'],
            actual_size='',quality='auto',output_format='mp4',count=1,cost=cost,
            dialogue_id=dialogue_id,duration_seconds=normalized['duration_seconds'],metadata=metadata,bypass_billing=bool(test_provider))
        remember_request(user_id,key,identity,tid)
    try:
        enqueue_generation_task(app,tid)
    except Exception:
        # Durable queued row is recovered by worker maintenance.
        app.logger.exception('video enqueue deferred task_id=%s',tid)
    return get_generation_task(tid)
