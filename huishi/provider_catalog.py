"""Local connection/model routing; no network discovery on generation paths."""
from copy import deepcopy
from flask import g, has_request_context
from huishi.db import get_db

MODEL_TYPES={'image','video','speech','music','prompt'}


# A shared connection may carry stale or hand-entered media_type values.  These
# well-known platform ids are authoritative enough to prevent an image/chat
# model from leaking into the video workbench while keeping custom ids
# explicitly classified by the administrator.
KNOWN_MODEL_TYPES = {
    'grok-4.5': 'prompt',
    'grok-4.6': 'prompt',
    'grok-imagine': 'image',
    'grok-imagine-image': 'image',
    'grok-imagine-image-2.0': 'image',
    'grok-imagine-image-quality': 'image',
    'gpt-image-2-adobe': 'image',
    'grok-imagine-video': 'video',
    'grok-imagine-video-1.5': 'video',
    'minimax-h3': 'video',
    'minimax-hailuo-3.0': 'video',
}


def _known_model_type(entry):
    for field in ('id', 'upstream_id'):
        model_id = str(entry.get(field) or '').strip().lower()
        if model_id in KNOWN_MODEL_TYPES:
            return KNOWN_MODEL_TYPES[model_id]
        if model_id.startswith(('seedance2.', 'seedance-', 'doubao-seedance-', 'sd-', 'sd2.')):
            return 'video'
        if model_id.startswith(('gpt-image-', 'gemini-')) and 'image' in model_id:
            return 'image'
        if model_id.startswith('nano-banana'):
            return 'image'
    return ''


def model_type(entry, provider_type):
    known = _known_model_type(entry)
    if known:
        return known
    kind=entry.get('media_type') or entry.get('capability') or ''
    if kind=='text':
        kind='prompt'
    if kind in MODEL_TYPES:
        return kind
    # A mixed connection is intentionally explicit.  Model IDs are not a
    # reliable capability contract: the same upstream ID can be exposed by
    # different gateways, and guessing here was the cause of image models
    # opening the video test dialog.  Unknown entries remain unclassified
    # until an administrator selects and saves a media type.
    return ''


def suggested_model_type(entry):
    """Return only capability metadata supplied by the upstream catalog."""
    known = _known_model_type(entry)
    if known:
        return known
    kind = str(entry.get('media_type') or entry.get('capability') or '').strip().lower()
    return 'prompt' if kind == 'text' else kind if kind in MODEL_TYPES else ''


def provider_view(provider, kind, *, selected_model=None, include_disabled=True):
    """Project one shared connection for an existing media-specific consumer."""
    wanted={'speech','music'} if kind=='audio' else {kind}
    family='audio' if kind in ('speech','music') else kind
    if provider['provider_type'] not in ('mixed',family):
        return None
    if provider['provider_type']=='audio':
        declared=set(provider.get('capabilities') or []) & {'speech','music'}
        if declared:
            wanted &= declared
    entries=[entry for entry in provider.get('models',[]) if model_type(entry,provider['provider_type']) in wanted
             and (include_disabled or entry.get('enabled',True))]
    if not entries:
        return None
    default=next((entry for entry in entries if entry['id']==selected_model),None) if selected_model else None
    if selected_model and default is None:
        return None
    default=default or next((e for e in entries if e.get('enabled',True) and e['id']==provider.get('model')),None)
    default=default or next((e for e in entries if e.get('enabled',True)),entries[0])
    return {**provider,'connection_type':provider['provider_type'],'connection_api_format':provider['api_format'],
            'provider_type':'audio' if kind in ('speech','music') else kind,
            'model':default['id'],'api_format':default.get('api_format') or provider['api_format'],
            'models':[{**e,'media_type':model_type(e,provider['provider_type'])} for e in entries],
            'capabilities':list(dict.fromkeys(model_type(e,provider['provider_type']) for e in entries))}


def resolve_test_provider(provider, selected_model):
    entry=next((e for e in provider.get('models',[]) if e['id']==selected_model),None)
    if not entry:
        raise ValueError('请先把测试模型添加到该渠道并保存')
    kind=model_type(entry,provider['provider_type'])
    if not kind:
        raise ValueError('请先为模型选择类型并保存')
    return provider_view(provider,kind,selected_model=selected_model)


def invalidate_catalog():
    if has_request_context():
        g.pop('_provider_route_index',None)
        g.pop('_model_prices',None)
        g.pop('_managed_model_ids',None)


def load_enabled_connections():
    from huishi.providers import normalize_provider
    rows=get_db().execute('SELECT * FROM api_providers WHERE enabled=1 ORDER BY priority ASC,id ASC').fetchall()
    return [normalize_provider(row) for row in rows]


def local_candidates(kind, model=None):
    cached=g.get('_provider_route_index') if has_request_context() else None
    if cached is None:
        groups={key:[] for key in ('image','video','audio','speech','music','prompt')}
        by_model={}
        for provider in load_enabled_connections():
            from huishi.model_lifecycle import publication
            provider={**provider,'models':[e for e in provider.get('models',[]) if not e.get('managed') or publication(provider,e)['ready']]}
            for group in groups:
                view=provider_view(provider,group,include_disabled=False)
                if not view:
                    continue
                groups[group].append(view)
                for entry in view['models']:
                    selected={**view,'model':entry['id'],'models':[entry],'api_format':entry.get('api_format') or provider['api_format']}
                    by_model.setdefault((group,entry['id']),[]).append(selected)
        cached=(groups,by_model)
        if has_request_context():
            g._provider_route_index=cached
    groups,by_model=cached
    result=by_model.get((kind,str(model)),[]) if model and model!='*' else groups.get(kind,[])
    return deepcopy(result)
