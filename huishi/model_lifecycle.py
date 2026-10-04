"""Model binding identity, publication checks and administrator summaries."""
from decimal import Decimal, InvalidOperation
from flask import g, has_request_context
from huishi.db import get_db


def upstream_model(provider, model=None):
    selected=str(model or provider.get('model') or '')
    entry=next((e for e in provider.get('models',[]) if e['id']==selected),{})
    return str(entry.get('upstream_id') or selected)


def test_fingerprint(provider, model):
    """Bind asynchronous test results to the complete call configuration."""
    from huishi.media_tasks import payload_hash
    entry=next((e for e in provider.get('models',[]) if e['id']==model),{})
    return payload_hash({'connection':{k:provider.get(k) for k in ('api_key','base_url','settings','resolutions')},
                         'protocol':entry.get('api_format') or provider['api_format'],
                         'model':{k:entry.get(k) for k in ('id','upstream_id','media_type','capabilities','resolutions','durations','duration_seconds')}})


def validate_binding(entry):
    if 'upstream_id' in entry:
        entry['upstream_id']=str(entry['upstream_id']).strip() or entry['id']
    if len(entry['id'])>200 or len(entry.get('upstream_id',''))>200:
        raise ValueError('模型 ID 长度不能超过200个字符')
    if 'managed' in entry: entry['managed']=entry.get('managed') is True
    raw=entry.get('cost_amount')
    if raw not in (None,''):
        try:
            amount=Decimal(str(raw))
        except InvalidOperation:
            raise ValueError('渠道成本必须是有效金额')
        if not amount.is_finite() or amount<0 or amount>1000000:
            raise ValueError('渠道成本金额超出范围')
        if entry.get('cost_currency') not in ('CNY','USD') or entry.get('cost_unit') not in ('image','second','request','1000_chars','1000_tokens'):
            raise ValueError('请选择渠道成本币种和单位')
        entry['cost_amount']=str(amount)


def pricing_catalog():
    cached=g.get('_model_prices') if has_request_context() else None
    if cached is None:
        cached={}
        for table in ('pricing_rules','video_pricing_rules'):
            for row in get_db().execute(f'SELECT * FROM {table}').fetchall():
                row=dict(row)
                if str(row.get('model') or '').strip() == '*':
                    continue
                kind='video' if table=='video_pricing_rules' else row['media_type']
                if table=='pricing_rules' and kind=='video':
                    continue  # Managed videos use the dedicated pricing contract.
                if row['enabled'] and int(row.get('points',row.get('points_per_image',0)))>0:
                    cached.setdefault((kind,row['model']),[]).append(row)
        if has_request_context(): g._model_prices=cached
    return cached


def exact_prices(kind, model):
    return pricing_catalog().get((kind,model),[])


def compatible_prices(provider, entry, kind):
    prices=exact_prices(kind,entry['id'])
    protocol=entry.get('api_format') or provider.get('connection_api_format') or provider['api_format']
    if kind=='image':
        from huishi.providers import normalize_provider_resolutions, provider_supported_resolutions
        resolutions=set(normalize_provider_resolutions(entry.get('resolutions',provider.get('resolutions')),'image'))
        resolutions &= set(provider_supported_resolutions(protocol))
        return [r for r in prices if r['mode']=='text' and r['resolution'] in resolutions]
    if kind in ('speech','music'):
        return [r for r in prices if r['mode']==kind and r['resolution']=='default']
    if kind=='video':
        from huishi.media_capabilities import video_capabilities
        caps=video_capabilities(protocol,entry.get('upstream_id') or entry['id'],entry.get('capabilities'))
        def duration_supported(duration):
            duration_range=caps.get('duration_range')
            if duration_range:
                minimum,maximum,step=duration_range.get('min',0),duration_range.get('max',-1),duration_range.get('step',1)
                return step > 0 and minimum <= duration <= maximum and (duration-minimum)%step==0
            return 'durations' not in caps or duration in caps['durations']
        has_duration_spec='durations' not in caps and 'duration_range' not in caps or bool(caps.get('durations') or caps.get('duration_range'))
        def price_supports_duration(rule):
            # A per-request rule with duration_seconds=0 means one price for
            # any duration accepted by the channel model. Do not interpret
            # the sentinel as a literal zero-second video.
            if rule['billing_unit'] == 'per_second':
                return True
            if rule['billing_unit'] == 'per_request' and rule['duration_seconds'] in (None, 0, '0'):
                return True
            return duration_supported(rule['duration_seconds'])

        return [r for r in prices if ('resolutions' not in caps or r['resolution'] in caps['resolutions'])
                and has_duration_spec and price_supports_duration(r)]
    return prices


def publication(provider,entry):
    from huishi.provider_catalog import model_type
    from huishi.image_api import is_placeholder_api_key
    kind=model_type(entry,provider['provider_type'])
    reasons=[]
    if not provider.get('enabled'): reasons.append('渠道停用')
    if not entry.get('enabled',True): reasons.append('模型停用')
    if not provider.get('base_url'): reasons.append('缺少接口地址')
    if not provider.get('api_key') or is_placeholder_api_key(provider.get('api_key')): reasons.append('缺少有效 Key')
    if not kind: reasons.append('待分类')
    prices=compatible_prices(provider,entry,kind) if kind and kind!='prompt' else []
    if kind and kind!='prompt' and not prices and entry.get('managed'):
        reasons.append('售价与可用规格不匹配' if exact_prices(kind,entry['id']) else '未设置模型售价')
    check=entry.get('verification') or {}
    checked='待重新测试' if check.get('stale') else '验证失败' if check.get('generation')=='failed' else '已验证' if check.get('generation')=='passed' else '尚未验证'
    return {'ready':not reasons,'reasons':reasons,'verification':checked,
            'pricing':'助手不单独计费' if kind=='prompt' else '已定价' if prices else '未设置模型售价'}


def managed_model(kind,model):
    from huishi.provider_catalog import load_enabled_connections, model_type
    cached=g.get('_managed_model_ids') if has_request_context() else None
    if cached is None:
        cached={(model_type(e,p['provider_type']),e['id']) for p in load_enabled_connections() for e in p.get('models',[]) if e.get('managed')}
        if has_request_context(): g._managed_model_ids=cached
    return (kind,model) in cached


def error_summary(message):
    message=str(message or '')
    if not message: return ''
    if 'has no attribute' in message or 'JSON' in message: return '接口返回格式不符合预期'
    if '404' in message: return '接口路径或模型不存在'
    if '401' in message or '403' in message: return '接口鉴权或访问权限失败'
    if 'Base URL' in message or 'base_url' in message: return '接口地址配置需要检查'
    if 'timeout' in message.lower() or '超时' in message: return '请求超时，需核对上游结果'
    return '最近测试失败，请查看详情'


def admin_connections():
    from huishi.providers import list_providers
    from huishi.secrets import redact_sensitive_text
    connections=list_providers()
    for p in connections:
        for entry in p['models']: entry['publication']=publication(p,entry)
        p['ready_count']=sum(e['publication']['ready'] for e in p['models'])
        p['enabled_count']=sum(e.get('enabled',True) for e in p['models'])
        p['error_summary']=error_summary(p.get('last_error'))
        p['last_error']=redact_sensitive_text(p.get('last_error'),p.get('api_key'),p.get('proxy_url'))
    return connections
