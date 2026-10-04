"""Channel-specific video contracts shared by API validation and both clients."""
from copy import deepcopy
from urllib.parse import urlsplit

RATIOS = ['1:1', '3:4', '4:3', '9:16', '16:9', '21:9']
CHANNEL_PROTOCOLS = {'dmc_h3', 'seedance_media', 'jiasuapi'}
SEEDANCE_DURATIONS = {'seedance2.5': [30], 'seedance2.0': [5, 10, 15],
                      'seedance2.0fast': [5, 10, 15], 'seedance2.0mini': [5, 10]}
GROK_VIDEO_MODELS = {'grok-imagine-video', 'grok-imagine-video-1.5'}
GROK_VIDEO_DURATIONS = list(range(1, 16))
GROK_VIDEO_RESOLUTIONS = ['480p', '720p', '1080p']
GROK_VIDEO_RATIOS = ['16:9', '9:16', '1:1']


def video_capabilities(protocol, model, configured=None):
    normalized_model = str(model or '').strip().lower()
    if protocol == 'jiasuapi' and normalized_model == 'minimax-h3':
        caps = dict(duration_range={'min': 4, 'max': 15, 'step': 1}, resolutions=['2k'],
                    ratios=['9:16', '1:1', '3:4', '4:3', '16:9'],
                    modes=['text', 'keyframes', 'omni_reference'], max_reference_images=9,
                    max_reference_videos=3, max_reference_audios=3, max_references=15,
                    max_prompt_chars=7000, supports_cancel=False)
    elif protocol == 'jiasuapi' and ('seedance' in normalized_model or normalized_model.startswith(('sd-', 'sd2.'))) and '2.5' in normalized_model:
        caps = dict(duration_range={'min': 4, 'max': 30, 'step': 1},
                    resolutions=['480p', '720p', '1080p'], ratios=['16:9', '9:16', '1:1'],
                    modes=['text', 'keyframes', 'omni_reference'], max_prompt_chars=7000,
                    supports_cancel=False)
    elif protocol == 'jiasuapi' and ('seedance' in normalized_model or normalized_model.startswith(('sd-', 'sd2.'))) and '2.0' in normalized_model:
        caps = dict(duration_range={'min': 4, 'max': 15, 'step': 1},
                    resolutions=['480p', '720p', '1080p'], ratios=['16:9', '9:16', '1:1'],
                    modes=['text', 'keyframes', 'omni_reference'], max_prompt_chars=7000,
                    supports_cancel=False)
    elif protocol == 'dmc_h3' and model == 'MiniMax-H3':
        caps = dict(durations=list(range(1, 16)), resolutions=['768P'], ratios=RATIOS + ['adaptive'],
                    modes=['text', 'keyframes', 'omni_reference'], max_reference_images=9,
                    max_reference_videos=3, max_reference_audios=3, max_references=12,
                    max_image_bytes=30000000, max_video_bytes=50000000, max_audio_bytes=15000000,
                    max_prompt_chars=7000, supports_cancel=False)
    elif protocol == 'seedance_media' and model in SEEDANCE_DURATIONS:
        caps = dict(durations=SEEDANCE_DURATIONS[model], resolutions=['720p'], ratios=RATIOS,
                    modes=['text', 'reference_images'], max_reference_images=30 if model == 'seedance2.5' else 9,
                    max_reference_videos=0, max_reference_audios=0, max_image_bytes=12*1024*1024,
                    max_images_total_bytes=70*1024*1024, camera_movement=['auto', 'fixed'],
                    max_prompt_chars=6000, supports_cancel=False)
    elif protocol == 'grok' and model in GROK_VIDEO_MODELS:
        caps = dict(durations=GROK_VIDEO_DURATIONS, resolutions=GROK_VIDEO_RESOLUTIONS,
                    ratios=GROK_VIDEO_RATIOS, modes=['text', 'reference_images'],
                    max_reference_images=1, max_reference_videos=0, max_reference_audios=0,
                    max_references=1, max_prompt_chars=6000, supports_cancel=False)
    elif protocol in CHANNEL_PROTOCOLS:
        return {}
    else:
        return deepcopy(configured) if isinstance(configured, dict) else {}
    # Saved capabilities can restrict a documented channel, never expand it.
    if isinstance(configured, dict):
        for key, value in configured.items():
            if key not in caps:
                continue
            if isinstance(caps[key], list) and isinstance(value, list):
                caps[key] = [item for item in caps[key] if item in value]
            elif type(caps[key]) is int and type(value) is int:
                caps[key] = min(caps[key], value)
    return deepcopy(caps)


def _duration_in_range(duration, value):
    if not isinstance(value, dict):
        raise ValueError('视频时长范围配置无效')
    minimum, maximum, step = value.get('min'), value.get('max'), value.get('step', 1)
    if any(isinstance(part, bool) or not isinstance(part, int) for part in (minimum, maximum, step)):
        raise ValueError('视频时长范围配置无效')
    if minimum < 1 or maximum < minimum or maximum > 3600 or step < 1 or step > 3600:
        raise ValueError('视频时长范围配置无效')
    return minimum <= duration <= maximum and (duration - minimum) % step == 0


def validate_video_request(model, capabilities, request):
    result = deepcopy(request)
    prompt = str(result.get('prompt') or '').strip()
    if not prompt or len(prompt) > capabilities.get('max_prompt_chars', 7000):
        raise ValueError('提示词为空或超过模型字数限制')
    result['prompt'] = prompt
    # Defaults must come from the selected model contract.  A fixed six-second
    # fallback used to leak into Grok/Seedance requests and could produce a
    # value that the model did not support.
    supported_durations = capabilities.get('durations') or []
    duration_range = capabilities.get('duration_range')
    range_default = duration_range.get('min') if isinstance(duration_range, dict) else None
    raw_duration = result.get('duration_seconds', result.get('seconds',
        supported_durations[0] if supported_durations else range_default or 1))
    if isinstance(raw_duration, bool) or not str(raw_duration).isdigit():
        raise ValueError('视频时长必须是整数秒')
    duration = int(raw_duration)
    if duration < 1 or (duration_range is not None and not _duration_in_range(duration, duration_range)) or (duration_range is None and capabilities.get('durations') is not None and duration not in capabilities['durations']):
        raise ValueError('视频时长不在当前模型支持范围内')
    result['duration_seconds'] = duration
    supported_resolutions = capabilities.get('resolutions') or []
    resolution = str(result.get('resolution') or (
        supported_resolutions[0] if supported_resolutions else '720p'
    ))
    if 'resolutions' in capabilities:
        match = next((v for v in capabilities['resolutions'] if v.lower() == resolution.lower()), None)
        if not match:
            raise ValueError('当前模型不支持所选分辨率')
        resolution = match
    result['resolution'] = resolution
    supported_ratios = capabilities.get('ratios') or []
    ratio = str(result.get('ratio') or (
        supported_ratios[0] if supported_ratios else '16:9'
    ))
    if 'ratios' in capabilities and ratio not in capabilities['ratios']:
        raise ValueError('当前模型不支持所选画幅比例')
    result['ratio'] = ratio
    content = result.get('content') or [{'type': 'text', 'text': prompt}]
    if not isinstance(content, list) or any(not isinstance(item, dict) for item in content):
        raise ValueError('参考素材格式错误')
    texts = [item for item in content if item.get('type') == 'text']
    if len(texts) != 1 or str(texts[0].get('text') or '').strip() != prompt:
        raise ValueError('content 必须包含且只包含一个与提示词一致的文本项')
    refs = [item for item in content if item.get('type') != 'text']
    counts = {'image_url': 0, 'video_url': 0, 'audio_url': 0}
    roles = []
    for item in refs:
        kind = item.get('type')
        if kind not in counts:
            raise ValueError('不支持的参考素材类型')
        role = item.get('role') or ('first_frame' if len(refs) == 1 and kind == 'image_url' else '')
        allowed = {'image_url': ['first_frame', 'last_frame', 'reference_image'],
                   'video_url': ['reference_video'], 'audio_url': ['reference_audio']}
        if role not in allowed[kind]:
            raise ValueError('参考素材角色错误')
        if 'omni_reference' not in capabilities.get('modes', []) and capabilities and role != 'reference_image':
            raise ValueError('当前渠道不支持首尾帧或视频音频参考')
        nested = item.get(kind)
        url = str(nested.get('url') or '') if isinstance(nested, dict) else ''
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('参考素材必须使用可访问的 HTTPS 地址')
        item['role'] = role
        counts[kind] += 1
        roles.append(role)
    if any(role in ('first_frame', 'last_frame') for role in roles):
        if any(role.startswith('reference_') for role in roles) or len(roles) != len(set(roles)):
            raise ValueError('首尾帧不能重复或与全能参考混用')
    for kind, limit_key in [('image_url', 'max_reference_images'), ('video_url', 'max_reference_videos'), ('audio_url', 'max_reference_audios')]:
        if counts[kind] > capabilities.get(limit_key, 99):
            raise ValueError('参考素材数量超过当前模型限制')
    if len(refs) > capabilities.get('max_references', 99):
        raise ValueError('参考素材总数超过当前模型限制')
    if capabilities and ratio == 'adaptive' and not (counts['image_url'] or counts['video_url']):
        raise ValueError('adaptive 需要图片或视频参考')
    camera = result.get('camera_movement') or 'auto'
    if capabilities.get('camera_movement') and camera not in capabilities['camera_movement']:
        raise ValueError('当前模型不支持所选镜头模式')
    result['camera_movement'] = camera
    result['content'] = content
    result['model'] = model
    return result
