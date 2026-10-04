"""Portable encrypted channel/pricing backups; imports never overwrite channels."""
import base64
import json
import os
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from huishi.db import get_db, immediate_transaction, utc_now
from huishi.providers import list_providers, save_provider
from huishi.secrets import redact_url

MAX_BYTES=4*1024*1024
CONNECTION_FIELDS=('provider_type','name','base_url','api_key','model','api_format','priority','enabled','resolutions','capabilities','models','settings')
PRICE_FIELDS={'pricing_rules':('mode','model','resolution','points_per_image','enabled','media_type','duration_tier'),
              'video_pricing_rules':('model','resolution','billing_unit','duration_seconds','points','enabled')}
PRICE_KEYS={'pricing_rules':('mode','model','resolution'),'video_pricing_rules':('model','resolution','billing_unit','duration_seconds')}


def export_config(include_secrets=False):
    connections=[]
    for provider in list_providers():
        item={k:provider.get(k) for k in CONNECTION_FIELDS}
        item['models']=[{k:v for k,v in e.items() if k!='verification'} for e in item['models']]
        # Only supported settings, never arbitrary historical credentials or logs.
        item['settings']={k:v for k,v in (item.get('settings') or {}).items() if k in ('proxy_url','speech_path','music_path','poll_interval','create_path','poll_path','file_path')}
        if not include_secrets:
            item['api_key']=''
            item['base_url']=redact_url(item['base_url'])
            item['settings'].pop('proxy_url',None)
        connections.append(item)
    prices={table:[{k:r[k] for k in fields} for r in get_db().execute(f'SELECT * FROM {table}').fetchall()] for table,fields in PRICE_FIELDS.items()}
    return {'format':'huishi-provider-config','version':1,'created_at':utc_now(),'contains_secrets':include_secrets,'connections':connections,'prices':prices}


def _cipher(password,salt):
    if not isinstance(password,str) or not 12<=len(password)<=256:
        raise ValueError('备份口令须为12至256个字符')
    key=Scrypt(salt=salt,length=32,n=2**15,r=8,p=1).derive(password.encode())
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_backup(password):
    salt=os.urandom(16)
    payload=json.dumps(export_config(include_secrets=True),ensure_ascii=False).encode()
    if len(payload)>MAX_BYTES: raise ValueError('配置备份超过4MiB限制')
    token=_cipher(password,salt).encrypt(payload)
    return json.dumps({'format':'huishi-provider-encrypted','version':1,'salt':base64.b64encode(salt).decode(),'token':token.decode()}).encode()


def decrypt_backup(content,password):
    if len(content)>MAX_BYTES*2: raise ValueError('备份文件过大')
    try:
        envelope=json.loads(content)
        if envelope.get('format')!='huishi-provider-encrypted' or envelope.get('version')!=1: raise ValueError()
        salt=base64.b64decode(envelope['salt'],validate=True)
        if len(salt)!=16: raise ValueError()
        document=json.loads(_cipher(password,salt).decrypt(envelope['token'].encode()))
        validate_document(document)
        return document
    except (ValueError,TypeError,KeyError,AttributeError,InvalidToken,UnicodeError) as exc:
        raise ValueError('无法解密备份：口令不正确、文件损坏或格式不支持') from exc


def validate_document(document):
    if not isinstance(document,dict) or document.get('format')!='huishi-provider-config' or document.get('version')!=1:
        raise ValueError('不支持的配置格式')
    connections=document.get('connections')
    if not isinstance(connections,list) or len(connections)>500 or any(not isinstance(p,dict) for p in connections):
        raise ValueError('渠道清单无效或超过500条')
    for provider in connections:
        models=provider.get('models') or []
        if not isinstance(models,list) or any(not isinstance(e,dict) or not isinstance(e.get('id'),str) for e in models):
            raise ValueError('模型清单无效')
        if provider.get('settings') is not None and not isinstance(provider['settings'],dict):
            raise ValueError('渠道设置格式无效')
    if not isinstance(document.get('prices'),dict): raise ValueError('定价清单无效')
    for table,fields in PRICE_FIELDS.items():
        rows=document['prices'].get(table)
        if not isinstance(rows,list) or len(rows)>10000: raise ValueError('定价清单无效或过大')
        seen=set()
        for row in rows:
            if not isinstance(row,dict) or any(k not in row for k in fields): raise ValueError('定价字段缺失')
            key=tuple(str(row[k]) for k in PRICE_KEYS[table])
            if key in seen: raise ValueError('备份中存在重复定价')
            seen.add(key)
            amount=row['points'] if table=='video_pricing_rules' else row['points_per_image']
            if type(amount) is not int or amount<1 or row['enabled'] not in (0,1): raise ValueError('售价或启用状态无效')
            if table=='video_pricing_rules' and (row['billing_unit'] not in ('per_second','per_request') or type(row['duration_seconds']) is not int or row['duration_seconds']<0):
                raise ValueError('视频计费单位无效')


def preview_config(document):
    validate_document(document)
    conflicts=[]
    for table,fields in PRICE_FIELDS.items():
        for row in document['prices'][table]:
            keys=PRICE_KEYS[table]
            old=get_db().execute(f'SELECT * FROM {table} WHERE '+ ' AND '.join(f'{k}=?' for k in keys),tuple(row[k] for k in keys)).fetchone()
            if old and any(old[k]!=row[k] for k in fields): conflicts.append(str(row['model']))
    return {'connections':len(document['connections']),'models':sum(len(p.get('models') or []) for p in document['connections']),
            'prices':sum(len(v) for v in document['prices'].values()),'conflicts':sorted(set(conflicts)),
            'message':'将新增停用渠道；相同价格复用，冲突价格拒绝导入'}


def restore_config(document):
    with immediate_transaction():
        preview=preview_config(document)
        if preview['conflicts']: raise ValueError('定价冲突，请先核对当前规则；未导入任何配置')
        ids=[]
        for p in document['connections']:
            values={k:p.get(k) for k in CONNECTION_FIELDS}
            values['enabled']=False
            values['name']=str(values['name'] or '渠道')+'（恢复）'
            values['models']=[{**e,'verification':{}} for e in (values['models'] or [])]
            ids.append(save_provider(**values))
        for table,fields in PRICE_FIELDS.items():
            for row in document['prices'][table]:
                keys=PRICE_KEYS[table]
                get_db().execute(f'INSERT INTO {table} ({",".join(fields)}) VALUES ({",".join("?" for _ in fields)}) ON CONFLICT ({",".join(keys)}) DO NOTHING',tuple(row[k] for k in fields))
        # Detect a conflicting concurrent insertion as well as pre-existing prices.
        if preview_config(document)['conflicts']: raise ValueError('恢复期间定价发生冲突，已撤销本次导入')
    from huishi.provider_catalog import invalidate_catalog
    invalidate_catalog()
    return ids
