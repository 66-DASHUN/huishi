"""Explicit, transactional model administration over the existing provider schema."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from urllib.parse import urlsplit, urlunsplit
from flask import g, has_request_context

from huishi.db import get_db, immediate_transaction, PostgreSQLConnection, utc_now
from huishi import providers
from huishi.network import normalize_proxy_url
from huishi.provider_catalog import MODEL_TYPES, invalidate_catalog, model_type, suggested_model_type
from huishi.model_lifecycle import publication, validate_binding
from huishi.media_capabilities import video_capabilities


class RevisionConflict(ValueError):
    pass


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _integer(value, name, minimum=0, maximum=1000000):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f'{name}必须是整数')
    if isinstance(value, bool) or not number.is_finite() or number != number.to_integral_value() or not minimum <= number <= maximum:
        raise ValueError(f'{name}必须是 {minimum} 至 {maximum} 的整数')
    return int(number)


def _identity(value, name='模型 ID'):
    value = str(value or '').strip()
    if not value or len(value) > 200 or value == '*' or any(ord(c) < 32 for c in value):
        raise ValueError(f'{name}不能为空、使用通配符或超过200个字符')
    return value


def _json(value, default):
    try:
        result = json.loads(value) if isinstance(value, str) else value
    except (ValueError, TypeError):
        return deepcopy(default)
    return result if isinstance(result, type(default)) else deepcopy(default)


def _lock():
    db = get_db()
    if isinstance(db, PostgreSQLConnection):
        # One transaction lock serializes this management surface, including new rows.
        db.execute('SELECT pg_advisory_xact_lock(718214103)')
        db.execute('SELECT id FROM api_providers ORDER BY id FOR UPDATE').fetchall()


def _raw(pid):
    row = get_db().execute('SELECT * FROM api_providers WHERE id=?', (pid,)).fetchone()
    if row is None:
        raise ValueError('渠道不存在')
    return dict(row)


def _revision(pid):
    return _hash(_raw(pid))


def _check(actual, supplied):
    if not supplied or actual != supplied:
        raise RevisionConflict('配置已变化，请刷新后重新编辑')


def _safe_url(value):
    try:
        p = urlsplit(str(value or ''))
        host = p.hostname or ''
        if ':' in host:
            host = '[' + host + ']'
        if p.port:
            host += ':' + str(p.port)
        return urlunsplit((p.scheme, host, p.path, '', ''))
    except ValueError:
        return ''


def _connection(p):
    result = {k:p.get(k) for k in ('id','name','api_format','provider_type','priority')}
    settings = {k:p.get('settings',{}).get(k,0) for k in ('max_concurrency','requests_per_minute')}
    backup_base_url = _safe_url(p.get('settings', {}).get('backup_base_url'))
    result.update(base_url=_safe_url(p.get('base_url')), enabled=bool(p['enabled']),
                  has_key=bool(p.get('api_key')), proxy_configured=bool(p.get('proxy_url')),
                  backup_base_url=backup_base_url, backup_configured=bool(backup_base_url),
                  proxy_url=_safe_url(p.get('proxy_url')), revision=_revision(p['id']),
                  model_count=len(p['models']), settings=settings, **settings)
    return result


def _prices(kind, mid):
    if kind == 'video':
        rows = get_db().execute('SELECT * FROM video_pricing_rules WHERE model=? ORDER BY resolution,billing_unit,duration_seconds,id',(mid,)).fetchall()
        return [dict(resolution=r['resolution'], mode='video', points=r['points'], enabled=bool(r['enabled']),
                     billing_unit=r['billing_unit'], duration_seconds=r['duration_seconds']) for r in rows]
    rows = get_db().execute('SELECT * FROM pricing_rules WHERE media_type=? AND model=? ORDER BY resolution,mode,id',(kind,mid)).fetchall()
    return [dict(resolution=r['resolution'],mode=r['mode'],points=r['points_per_image'],enabled=bool(r['enabled']),
                 billing_unit='',duration_seconds=0) for r in rows]


def _model_revision(kind, mid, connections):
    relevant = [_raw(p['id']) for p in connections if any(e['id']==mid and model_type(e,p['provider_type'])==kind for e in p['models'])]
    return _hash({'providers':relevant,'prices':_prices(kind,mid)})


def _specs(p, e, kind):
    protocol = e.get('api_format') or p['api_format']
    if kind == 'image':
        resolutions = providers.normalize_provider_resolutions(e.get('resolutions',p.get('resolutions')),'image')
        return dict(resolutions=[r for r in resolutions if r in providers.provider_supported_resolutions(protocol)],durations=[],ratios=[])
    if kind == 'video':
        caps = video_capabilities(protocol,e.get('upstream_id') or e['id'],e.get('capabilities'))
        result = {key:list(caps.get(key) or []) for key in ('resolutions','durations','ratios')}
        if isinstance(caps.get('duration_range'), dict):
            result['duration_range'] = deepcopy(caps['duration_range'])
        return result
    return dict(resolutions=['default'] if kind in ('speech','music') else [],durations=[],ratios=[])


def _safe_capabilities(caps):
    # 字节上限（max_image_bytes 等）必须留在白名单里：seedance_media 的
    # ``_catalog_config`` 正是从上游目录里读出这些键写进 capabilities，
    # 而这里之前把它们过滤掉了——上游声明的体积限制落库即被丢弃，
    # 于是 media_references.validate_reference_metadata 只能一直用硬编码值。
    allowed = {'resolutions','durations','ratios','modes','max_reference_images','max_reference_videos',
               'max_reference_audios','max_references','max_prompt_chars','camera_movement','supports_cancel',
               'max_image_bytes','max_images_total_bytes','max_video_bytes','max_audio_bytes'}
    result = {k:v for k,v in (caps.items() if isinstance(caps,dict) else []) if k in allowed and isinstance(v,(list,int,bool))}
    value = caps.get('duration_range') if isinstance(caps,dict) else None
    if isinstance(value,dict) and set(value) <= {'min','max','step'} and {'min','max'} <= set(value):
        minimum,maximum,step=value.get('min'),value.get('max'),value.get('step',1)
        if all(type(part) is int for part in (minimum,maximum,step)) and 1 <= minimum <= maximum <= 3600 and 1 <= step <= 3600:
            result['duration_range']={'min':minimum,'max':maximum,'step':step}
    return result


def _audit(action, target, after):
    if has_request_context() and g.get('user') is not None:
        from huishi.admin_audit import record_admin_audit
        record_admin_audit(int(g.user['id']), action, 'model_management', target,
                           summary='更新模型服务配置', after=after)


def _validate_capabilities(caps):
    if not isinstance(caps, dict):
        raise ValueError('模型能力限制必须为对象')
    for key, label in (('durations', '时长'), ('resolutions', '分辨率'), ('ratios', '比例')):
        if key not in caps:
            continue
        values = caps[key]
        if not isinstance(values, list) or not values or len(values) > 100:
            raise ValueError(f'{label}限制必须为非空列表')
        if key == 'durations':
            caps[key] = [_integer(value, '时长', 1, 3600) for value in values]
        elif any(not isinstance(v, str) or not v.strip() or len(v) > 40 for v in values):
            raise ValueError(f'{label}限制格式无效')
        elif key == 'ratios' and any(v not in ('auto','adaptive') and not re.fullmatch(r'[1-9][0-9]*:[1-9][0-9]*', v) for v in values):
            raise ValueError('比例限制格式无效')
    if 'duration_range' in caps:
        if 'durations' in caps:
            raise ValueError('时长范围与固定时长列表不能同时配置')
        value = caps['duration_range']
        if not isinstance(value, dict) or set(value) - {'min','max','step'} or not {'min','max'} <= set(value):
            raise ValueError('时长范围配置格式无效')
        minimum = _integer(value['min'], '最短时长', 1, 3600)
        maximum = _integer(value['max'], '最长时长', minimum, 3600)
        step = _integer(value.get('step', 1), '时长步长', 1, 3600)
        if (maximum - minimum) // step + 1 > 3600:
            raise ValueError('时长范围选项过多')
        caps['duration_range'] = {'min': minimum, 'max': maximum, 'step': step}


def catalog():
    connections = providers.list_providers()
    grouped = {}
    issues = []
    for p in connections:
        for e in p['models']:
            kind = model_type(e,p['provider_type'])
            key = (kind,e['id'])
            m = grouped.setdefault(key,dict(id=e['id'],media_type=kind,label=e.get('label') or e['id'],
                legacy=True,bindings=[],specs=dict(resolutions=[],durations=[],ratios=[]),reasons=[]))
            status = publication(p,e)
            m['legacy'] = m['legacy'] and not e.get('managed')
            if m['label'] != (e.get('label') or e['id']):
                issues.append(dict(media_type=kind,model=e['id'],reason='同一模型的旧名称不一致，保存模型可统一'))
            caps = _safe_capabilities(e.get('capabilities'))
            verification = {k:v for k,v in (e.get('verification') or {}).items() if k in ('generation','stale','checked_at','status') and isinstance(v,(str,bool))}
            binding = dict(provider_id=p['id'],provider_name=p['name'],upstream_id=e.get('upstream_id') or e['id'],
                api_format=e.get('api_format') or p['api_format'],enabled=bool(e.get('enabled',True)),
                priority=e.get('priority',p['priority']),resolutions=_specs(p,e,kind)['resolutions'],capabilities=caps,specs=_specs(p,e,kind),
                cost_amount=e.get('cost_amount',''),cost_currency=e.get('cost_currency',''),cost_unit=e.get('cost_unit',''),
                verification=verification,reasons=status['reasons'],available=status['ready'])
            m['bindings'].append(binding)
            m['reasons'].extend(r for r in status['reasons'] if r not in m['reasons'])
            for field,values in _specs(p,e,kind).items():
                if isinstance(values, list):
                    m['specs'][field].extend(v for v in values if v not in m['specs'][field])
    for (kind,mid),m in grouped.items():
        m['prices'] = _prices(kind,mid)
        m['revision'] = _model_revision(kind,mid,connections)
        m['available_count'] = sum(b['available'] for b in m['bindings'])
        m['state'] = ('published' if m['available_count'] else
                      'pending' if any(b['enabled'] for b in m['bindings']) else 'disabled' if m['prices'] else 'draft')
    for table in ('pricing_rules', 'video_pricing_rules'):
        for row in get_db().execute(f'SELECT * FROM {table} WHERE enabled=1').fetchall():
            kind = 'video' if table == 'video_pricing_rules' else row['media_type']
            if row['model'] != '*' and (kind,row['model']) not in grouped:
                issue = dict(media_type=kind,model=row['model'],reason=f"{row['model']} 已有售价但未关联渠道模型")
                if issue not in issues:
                    issues.append(issue)
    return dict(connections=[_connection(p) for p in connections],models=list(grouped.values()),issues=issues)


def _draft(data):
    pid = _integer(data['id'],'渠道 ID',1) if data.get('id') else None
    old = providers.get_provider(pid) if pid else None
    if pid and old is None:
        raise ValueError('渠道不存在')
    p = deepcopy(old) if old else dict(provider_type='mixed',model='',models=[],resolutions=[],capabilities=[],settings={})
    for field in ('name','base_url','api_format'):
        p[field] = str(data.get(field,p.get(field,'openai' if field=='api_format' else '')) or '').strip()
    p['api_format'] = providers.normalize_provider_api_format(p['api_format'],p['provider_type'])
    providers.validate_provider_endpoint(p['api_format'],p['base_url'])
    p['api_key'] = str(data.get('api_key') or p.get('api_key') or '').strip()
    p['priority'] = _integer(data.get('priority',p.get('priority',100)),'优先级')
    p['enabled'] = bool(data.get('enabled',p.get('enabled',True)))
    if 'proxy_url' in data:
        submitted = str(data.get('proxy_url') or '')
        # A masked value copied from the catalog means preserve the saved secret.
        if old and submitted and submitted == _safe_url(old.get('proxy_url')):
            submitted = old.get('proxy_url','')
        p['proxy_url'] = normalize_proxy_url(submitted)
    else:
        p['proxy_url'] = normalize_proxy_url(p.get('proxy_url',''))
    p['settings']['proxy_url'] = p['proxy_url']
    if 'backup_base_url' in data:
        backup_base_url = str(data.get('backup_base_url') or '').strip()
        if backup_base_url:
            providers.validate_provider_endpoint(p['api_format'], backup_base_url)
            p['settings']['backup_base_url'] = _safe_url(backup_base_url)
        else:
            p['settings'].pop('backup_base_url', None)
    for key in ('max_concurrency','requests_per_minute'):
        if key in data:
            p['settings'][key] = _integer(data[key],key)
    return p


def _save_provider(p):
    return providers.save_provider(provider_type=p['provider_type'],name=p['name'],base_url=p['base_url'],api_key=p['api_key'],
        model=p.get('model',''),priority=p['priority'],enabled=p['enabled'],resolutions=p.get('resolutions'),
        provider_id=p.get('id'),api_format=p['api_format'],capabilities=p.get('capabilities'),models=p['models'],settings=p['settings'])


def save_connection(data):
    with immediate_transaction():
        _lock()
        p = _draft(data)
        original = _raw(p['id']) if p.get('id') else None
        if p.get('id'):
            _check(_revision(p['id']),data.get('revision'))
        pid = _save_provider(p)
        if original:
            # A connection edit must not normalize or migrate its old bindings.
            saved = providers.get_provider(pid)
            checks = {e['id']:e.get('verification') for e in saved['models']}
            entries = _json(original['models_json'],[])
            for e in entries:
                if isinstance(e,dict) and checks.get(e.get('id')):
                    e['verification']=checks[e['id']]
            get_db().execute('UPDATE api_providers SET models_json=?,model=?,resolutions=?,capabilities=? WHERE id=?',
                (json.dumps(entries,ensure_ascii=False,separators=(',',':')),original['model'],original['resolutions'],original['capabilities'],pid))
            invalidate_catalog()
        _audit('provider.connection.save', pid, {'name':p['name'],'enabled':p['enabled']})
    return _connection(providers.get_provider(pid))


def discover(data):
    p = _draft(data)
    if not p.get('api_key'):
        raise ValueError('请先填写 API Key')
    try:
        fetched = providers.fetch_provider_models(p)
    except Exception as exc:
        # Upstream error bodies may contain credentials or echoed request payloads.
        raise ValueError('模型发现失败，请检查地址、协议、Key 和代理配置') from exc
    result=[]
    for e in fetched:
        result.append(dict(id=_identity(e.get('id')),label=str(e.get('label') or e['id'])[:200],
                           media_type=suggested_model_type(e),api_format=e.get('api_format') or p['api_format']))
    return result


def import_models(data):
    pid = _integer(data.get('provider_id'),'渠道 ID',1)
    selections = data.get('models')
    states = data.get('states', [])
    if not isinstance(selections, list) or len(selections) > 500:
        raise ValueError('模型选择列表格式无效')
    if not isinstance(states, list) or len(states) > 500:
        raise ValueError('模型启用状态列表格式无效')
    if not selections and not states:
        raise ValueError('请选择至少一个模型，或修改已有模型的启用状态')
    state_updates = {}
    for state in states:
        if not isinstance(state, dict):
            raise ValueError('模型启用状态格式无效')
        upstream = _identity(state.get('id'))
        if not isinstance(state.get('enabled'), bool):
            raise ValueError('模型启用状态必须是布尔值')
        if upstream in state_updates:
            raise ValueError('模型启用状态重复')
        state_updates[upstream] = state['enabled']
    with immediate_transaction():
        _lock()
        _check(_revision(pid),data.get('revision'))
        p = providers.get_provider(pid)
        # Materialize inherited types only in this explicit import operation.
        entries = _json(_raw(pid)['models_json'],[])
        entries = [dict(e) if isinstance(e,dict) else {'id':str(e),'label':str(e)} for e in entries]
        if p.get('model') and not any(e['id']==p['model'] for e in entries):
            entries.append(deepcopy(next(e for e in p['models'] if e['id']==p['model'])))
        for e in entries:
            e['media_type'] = model_type(e,p['provider_type'])
        imported=0
        for selected in selections:
            if not isinstance(selected,dict):
                raise ValueError('模型格式无效')
            upstream = _identity(selected.get('id'))
            kind = str(selected.get('media_type') or '')
            if kind and kind not in MODEL_TYPES:
                raise ValueError('模型类型无效')
            existing=next((e for e in entries if (e.get('upstream_id') or e['id'])==upstream),None)
            if existing is not None:
                if kind and not existing.get('media_type'):
                    existing.update(media_type=kind,enabled=False,managed=True)
                    if selected.get('api_format'):
                        existing['api_format']=selected['api_format']
                continue
            mid = _identity(selected.get('platform_id') or upstream)
            if any(e['id']==mid for e in entries):
                raise ValueError('该渠道已有此平台模型，不能合并不同别名')
            entry=dict(id=mid,upstream_id=upstream,label=str(selected.get('label') or mid)[:200],media_type=kind,
                       enabled=False,managed=True,api_format=selected.get('api_format') or p['api_format'])
            entries.append(entry)
            imported += 1
        updated = 0
        for upstream, enabled in state_updates.items():
            existing = next((e for e in entries if (e.get('upstream_id') or e['id']) == upstream or e['id'] == upstream), None)
            if existing is None:
                raise ValueError('要更新的模型不在该渠道目录中')
            if enabled and not model_type(existing, 'mixed'):
                raise ValueError('启用模型前必须选择模型类型')
            existing['enabled'] = enabled
            updated += 1
        p.update(provider_type='mixed',models=entries)
        _save_provider(p)
        saved={e['id']:e for e in providers.get_provider(pid)['models']}
        for e in entries:
            if saved.get(e['id'],{}).get('verification'):
                e['verification']=saved[e['id']]['verification']
        get_db().execute('UPDATE api_providers SET models_json=? WHERE id=?',
            (json.dumps(entries,ensure_ascii=False,separators=(',',':')),pid))
        invalidate_catalog()
        _audit('provider.models.import', pid, {'imported':imported, 'updated':updated})
    return dict(connection=_connection(providers.get_provider(pid)),imported=imported,updated=updated)


def _validated_prices(kind, prices, routes):
    if not isinstance(prices,list) or len(prices)>500:
        raise ValueError('售价列表格式无效')
    result=[]
    units={}
    keys=set()
    for raw in prices:
        if not isinstance(raw,dict):
            raise ValueError('售价格式无效')
        resolution=str(raw.get('resolution') or '').strip()
        mode = 'video' if kind=='video' else kind if kind in ('speech','music') else 'text'
        if raw.get('mode',mode) != mode or kind=='prompt':
            raise ValueError('售价模式与模型类型不匹配')
        points=_integer(raw.get('points'),'售价积分',1,2147483647)
        row=dict(resolution=resolution,mode=mode,points=points,enabled=bool(raw.get('enabled',True)),billing_unit='',duration_seconds=0)
        if kind=='video':
            unit=raw.get('billing_unit','per_request')
            if unit not in ('per_second','per_request'):
                raise ValueError('视频计费单位无效')
            # A per-request price with duration_seconds=0 is the explicit
            # unlimited-duration contract; per-second prices also use 0
            # because their cost is calculated from the requested duration.
            seconds=_integer(raw.get('duration_seconds',0),'视频时长',0,3600)
            if unit=='per_second' and seconds:
                raise ValueError('按秒价格的固定时长必须为0')
            if resolution in units and units[resolution]!=unit:
                raise ValueError('同一分辨率不能混用按秒和按次计费')
            units[resolution]=unit
            row.update(billing_unit=unit,duration_seconds=seconds)
        compatible=False
        for p,e in routes:
            specs=_specs(p,e,kind)
            if resolution not in specs['resolutions']:
                continue
            duration_range=specs.get('duration_range') or {}
            duration_step=duration_range.get('step',1)
            range_supports_duration=(duration_step > 0 and duration_range.get('min',0) <= row['duration_seconds'] <= duration_range.get('max',-1)
                and (row['duration_seconds']-duration_range.get('min',0)) % duration_step == 0)
            if kind=='video' and row['billing_unit']=='per_request' and row['duration_seconds'] != 0 and row['duration_seconds'] not in specs['durations'] and not range_supports_duration:
                continue
            if kind=='video' and not specs['durations'] and not specs.get('duration_range'):
                continue
            compatible=True
        if not compatible:
            raise ValueError('售价规格不在实际渠道支持范围内；请先配置模型规格')
        key=(resolution,mode,row['billing_unit'],row['duration_seconds'])
        if key in keys:
            raise ValueError('售价规则重复')
        keys.add(key)
        result.append(row)
    return result


def _write_prices(kind,mid,prices):
    db=get_db()
    if kind=='video':
        db.execute('DELETE FROM video_pricing_rules WHERE model=?',(mid,))
        for p in prices:
            db.execute('INSERT INTO video_pricing_rules(model,resolution,billing_unit,duration_seconds,points,enabled) VALUES (?,?,?,?,?,?)',
                (mid,p['resolution'],p['billing_unit'],p['duration_seconds'],p['points'],int(p['enabled'])))
    else:
        db.execute('DELETE FROM pricing_rules WHERE media_type=? AND model=?',(kind,mid))
        for p in prices:
            db.execute('INSERT INTO pricing_rules(mode,model,resolution,points_per_image,enabled,media_type,duration_tier) VALUES (?,?,?,?,?,?,?)',
                (p['mode'],mid,p['resolution'],p['points'],int(p['enabled']),kind,''))
    invalidate_catalog()


def save_model(data):
    mid=_identity(data.get('id'))
    kind=str(data.get('media_type') or '')
    original_kind=str(data.get('original_media_type',kind) or '')
    if kind not in MODEL_TYPES:
        raise ValueError('请先为模型选择类型')
    bindings=data.get('bindings')
    if not isinstance(bindings,list) or not bindings:
        raise ValueError('模型至少需要一个渠道绑定')
    label=str(data.get('label') or mid).strip()[:200]
    publish=data.get('publish') is True
    with immediate_transaction():
        _lock()
        connections=providers.list_providers()
        old_routes=[(p,e) for p in connections for e in p['models'] if e['id']==mid and model_type(e,p['provider_type'])==original_kind]
        if not old_routes:
            raise ValueError('模型不存在，请先从渠道导入')
        _check(_model_revision(original_kind,mid,connections),data.get('revision'))
        if original_kind!=kind:
            if any(not e.get('managed') or e.get('enabled',True) for _,e in old_routes):
                raise ValueError('只有未发布的管理草稿可以更改模型类型')
            if any(e['id']==mid and model_type(e,p['provider_type'])==kind for p in connections for e in p['models']):
                raise ValueError('目标类型已有同名模型，不能合并不同模型')
            if _prices(original_kind,mid):
                raise ValueError('请先清空旧类型售价再更改模型类型')
        old_by_id={p['id']:(p,e) for p,e in old_routes}
        incoming={}
        for b in bindings:
            if not isinstance(b,dict):
                raise ValueError('渠道绑定格式无效')
            pid=_integer(b.get('provider_id'),'渠道 ID',1)
            if pid in incoming:
                raise ValueError('渠道绑定重复')
            incoming[pid]=b
        if not set(old_by_id).issubset(incoming):
            raise ValueError('请保留全部渠道绑定；可停用不需要的绑定')
        for pid in set(incoming) - set(old_by_id):
            p = next((p for p in connections if p['id']==pid), None)
            if p is None:
                raise ValueError('新增绑定的渠道不存在')
            _check(_revision(pid), incoming[pid].get('provider_revision'))
            if any(e['id']==mid for e in p['models']):
                raise ValueError('该渠道已有同名模型，请先核对类型和映射')
            old_by_id[pid] = (p, {'id':mid,'media_type':kind,'enabled':False,'managed':True})
        updated=[]
        for pid,b in incoming.items():
            p,old=old_by_id[pid]
            e=deepcopy(old)
            e.update(id=mid,label=label,media_type=kind,managed=True,enabled=publish and b.get('enabled',True) is True,
                upstream_id=_identity(b.get('upstream_id') or mid),priority=_integer(b.get('priority',p['priority']),'优先级'),
                api_format=providers.normalize_provider_api_format(b.get('api_format') or p['api_format'],'audio' if kind in ('speech','music') else kind))
            providers.validate_provider_endpoint(e['api_format'],p['base_url'])
            if kind=='image':
                providers.validate_image_model_protocol(e['upstream_id'],e['api_format'])
            for key in ('resolutions','capabilities','cost_amount','cost_currency','cost_unit'):
                if key in b:
                    e[key]=deepcopy(b[key])
            if original_kind!=kind and not e.get('resolutions'):
                e.pop('resolutions',None)
            if 'capabilities' in e and not isinstance(e['capabilities'],dict):
                raise ValueError('模型能力限制必须为对象')
            if 'capabilities' in e:
                _validate_capabilities(e['capabilities'])
                if 'duration_range' in e['capabilities']:
                    effective_caps=video_capabilities(e['api_format'],e.get('upstream_id') or e['id'],e['capabilities'])
                    if 'duration_range' not in effective_caps:
                        raise ValueError('当前渠道模型时长由官方能力固定，不能配置自由时长范围')
            if 'resolutions' in e and not isinstance(e['resolutions'],list):
                raise ValueError('分辨率限制必须为列表')
            if kind=='image' and 'resolutions' in e:
                allowed=providers.provider_supported_resolutions(e['api_format'])
                if not e['resolutions'] or any(r not in allowed for r in e['resolutions']):
                    raise ValueError('分辨率限制包含该协议不支持的规格')
            validate_binding(e)
            fields=('upstream_id','api_format','media_type','resolutions','capabilities')
            if any(e.get(k)!=old.get(k) for k in fields) and e.get('verification'):
                e['verification']={**e['verification'],'stale':True}
            updated.append((p,e))
        prices=_validated_prices(kind,data['prices'],updated) if 'prices' in data else _prices(kind,mid)
        if 'prices' in data:
            _write_prices(kind,mid,prices)
        if publish and not any(publication(p,e)['ready'] for p,e in updated):
            raise ValueError('发布需要已启用且配置完整的渠道，以及与规格匹配的模型售价')
        for p,e in updated:
            raw=_raw(p['id'])
            entries=_json(raw['models_json'],[])
            family = 'audio' if kind in ('speech','music') else kind
            if (original_kind!=kind or family!=p['provider_type']) and p['provider_type']!='mixed':
                entries=[dict(entry) if isinstance(entry,dict) else {'id':str(entry),'label':str(entry)} for entry in entries]
                for entry in entries:
                    entry['media_type']=model_type(entry,p['provider_type'])
                get_db().execute("UPDATE api_providers SET provider_type='mixed' WHERE id=?",(p['id'],))
            found=False
            for index,entry in enumerate(entries):
                if isinstance(entry,dict) and entry.get('id')==mid:
                    entries[index]=e
                    found=True
            if not found:
                entries.append(e)
            get_db().execute('UPDATE api_providers SET models_json=?,updated_at=? WHERE id=?',
                (json.dumps(entries,ensure_ascii=False,separators=(',',':')),utc_now(),p['id']))
        invalidate_catalog()
        _audit('provider.model.save', mid, {'media_type':kind,'published':publish,'binding_count':len(updated)})
    return next(m for m in catalog()['models'] if m['id']==mid and m['media_type']==kind)


def preview(data):
    from huishi.billing import calculate_cost
    from huishi.provider_catalog import local_candidates
    kind=str(data.get('media_type') or '')
    mid=_identity(data.get('model'))
    count=_integer(data.get('count',1),'生成数量',1,100)
    duration=_integer(data.get('duration_seconds',0),'视频时长',0,3600)
    resolution=str(data.get('resolution') or '')
    ratio=str(data.get('ratio') or '16:9')
    actual={p['id'] for p in local_candidates(kind,mid)}
    candidates=[]
    chosen=None
    for p in providers.list_providers():
        for e in p['models']:
            if e['id']!=mid or model_type(e,p['provider_type'])!=kind:
                continue
            reasons=list(publication(p,e)['reasons'])
            specs=_specs(p,e,kind)
            if kind in ('image','speech','music') and resolution not in specs['resolutions']:
                reasons.append('分辨率不在已确认规格内')
            if kind=='video':
                from huishi.media_capabilities import validate_video_request
                caps = video_capabilities(e.get('api_format') or p['api_format'], e.get('upstream_id') or mid, e.get('capabilities'))
                try:
                    validate_video_request(mid, caps, dict(prompt='配置预览', resolution=resolution, ratio=ratio, duration_seconds=duration))
                except ValueError as exc:
                    reasons.append(str(exc))
            if p['id'] not in actual and not reasons:
                reasons.append('不在当前运行路由候选中')
            candidates.append(dict(provider_id=p['id'],name=p['name'],eligible=not reasons,reasons=reasons,
                                   priority=e.get('priority',p['priority']),upstream_id=e.get('upstream_id') or mid))
    candidates.sort(key=lambda c:(c['priority'],c['provider_id']))
    chosen=next((c for c in candidates if c['eligible']),None)
    quote=None
    reasons=[]
    if chosen:
        try:
            points=0 if kind=='prompt' else calculate_cost(kind if kind!='image' else 'text',resolution,count,
                model=mid,media_type=kind,duration_seconds=duration)
            quote=dict(points=points,count=count,duration_seconds=duration,resolution=resolution)
        except ValueError as exc:
            reasons.append(str(exc))
            chosen=None
    else:
        reasons.append('没有满足当前规格的可用渠道')
    return dict(selected={k:chosen[k] for k in ('provider_id','name','upstream_id','priority')} if chosen else None,
                candidates=candidates,quote=quote,reasons=reasons)


def calls(params):
    page=_integer(params.get('page',1),'页码',1,1000000)
    clauses=[]
    args=[]
    for key in ('media_type','model','status'):
        if params.get(key):
            clauses.append('t.'+key+'=?')
            args.append(str(params[key]))
    where=' WHERE '+' AND '.join(clauses) if clauses else ''
    total=get_db().execute('SELECT COUNT(*) AS n FROM generation_tasks t'+where,args).fetchone()['n']
    rows=get_db().execute('SELECT t.*,p.name AS provider_name FROM generation_tasks t LEFT JOIN api_providers p ON p.id=t.provider_id'+where+' ORDER BY t.id DESC LIMIT 25 OFFSET ?',(*args,(page-1)*25)).fetchall()
    result=[]
    fields=('id','media_type','model','provider_id','provider_name','provider_task_id','status','resolution','ratio','count','cost',
            'duration_seconds','created_at','updated_at','finished_at')
    metadata_fields={'route':('provider_id','provider_name','model','upstream_id','api_format','priority','attempt'),
                     'quote':('points','cost','count','model','media_type','mode','resolution','ratio','quality','duration_seconds','output_format','billing_unit','unit_points'),
                     'timing':('queued_at','started_at','submitted_at','completed_at','elapsed_seconds','queue_seconds','queue_ms','upstream_ms')}
    for row in rows:
        item={k:row[k] for k in fields}
        meta=_json(row['metadata_json'],{})
        from huishi.task_billing import billing_summary, billing_message
        item['billing_message'] = billing_message(billing_summary({**dict(row), 'metadata':meta}))
        from huishi.model_lifecycle import error_summary
        item['error_message']=error_summary(row['error_message'])
        storage=meta.get('storage_status','')
        item['storage_status']=storage if storage in ('pending','uploading','stored','saved','failed','completed','local','remote') else ''
        for key,allowed in metadata_fields.items():
            section=meta.get(key,{})
            item[key]={k:v for k,v in section.items() if k in allowed and isinstance(v,(str,int,float,bool))} if isinstance(section,dict) else {}
        result.append(item)
    return dict(calls=result,page=page,page_size=25,total=total)
