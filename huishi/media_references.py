import io
import json
import secrets
import subprocess
import tempfile
from pathlib import Path
from flask import current_app, url_for
from itsdangerous import URLSafeTimedSerializer
from PIL import Image, UnidentifiedImageError
from huishi.db import get_db, utc_now
from huishi.upload_storage import get_upload_storage
from huishi.media_capabilities import validate_video_request


def inspect_media(data, kind):
    meta={'kind':kind,'bytes':len(data)}
    if kind=='image':
        try:
            with Image.open(io.BytesIO(data)) as image:
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                meta.update(width=image.width,height=image.height,animated=bool(getattr(image,'is_animated',False)),
                            mime=Image.MIME.get(image.format,'image/png'),extension=(image.format or 'png').lower())
        except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError) as exc:
            raise ValueError('图片内容无效或尺寸过大') from exc
    elif kind in ('video','audio'):
        with tempfile.NamedTemporaryFile() as source:
            source.write(data)
            source.flush()
            try:
                result=subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',source.name],capture_output=True,timeout=20,check=True)
                payload=json.loads(result.stdout)
            except (FileNotFoundError,subprocess.SubprocessError,ValueError) as exc:
                raise ValueError('无法检查视频/音频，请检查媒体格式或 ffprobe 依赖') from exc
        streams=payload.get('streams') or []
        chosen=next((s for s in streams if s.get('codec_type')==kind),None)
        if not chosen:
            raise ValueError('媒体内容与所选类型不一致')
        allowed={'video':{'h264','hevc'},'audio':{'pcm_s16le','pcm_s24le','pcm_s32le','mp3','aac'}}
        if chosen.get('codec_name') not in allowed[kind]:
            raise ValueError('参考媒体编码不在渠道支持范围内')
        formats=set(str(payload.get('format',{}).get('format_name') or '').split(','))
        if kind=='video' and formats.intersection({'mov','mp4'}):
            mime,extension='video/mp4','mp4'
        elif kind=='audio' and 'wav' in formats:
            mime,extension='audio/wav','wav'
        elif kind=='audio' and 'mp3' in formats:
            mime,extension='audio/mpeg','mp3'
        elif kind=='audio' and 'aac' in formats:
            mime,extension='audio/aac','aac'
        elif kind=='audio' and formats.intersection({'mov','mp4','m4a'}):
            mime,extension='audio/mp4','m4a'
        else:
            raise ValueError('参考媒体容器格式不在渠道支持范围内')
        meta.update(duration=float(payload.get('format',{}).get('duration') or 0),width=chosen.get('width'),height=chosen.get('height'),
                    mime=mime,extension=extension)
    else:
        raise ValueError('不支持的素材类型')
    return meta


def inspect_video_file(path):
    try:
        result=subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)],capture_output=True,timeout=20,check=True)
        payload=json.loads(result.stdout)
        video=next(s for s in payload['streams'] if s.get('codec_type')=='video')
        return {'width':int(video['width']),'height':int(video['height']),
                'duration_ms':round(float(payload.get('format',{}).get('duration') or 0)*1000)}
    except (FileNotFoundError,subprocess.SubprocessError,ValueError,KeyError,StopIteration) as exc:
        raise ValueError('生成结果不是可解码视频或 ffprobe 不可用') from exc


def validate_reference_metadata(protocol,metas):
    for meta in metas:
        kind=meta['kind']
        if protocol=='seedance_media':
            if kind!='image' or meta['bytes']>12*1024*1024:
                raise ValueError('此渠道仅支持不超过12MiB的参考图片')
        elif protocol=='dmc_h3':
            limits={'image':30000000,'video':50000000,'audio':15000000}
            if meta['bytes']>limits[kind]:
                raise ValueError('参考素材体积超过H3限制')
            if kind=='image':
                w,h=meta['width'],meta['height']
                if not (256<=w<=5760 and 256<=h<=5760 and w*h<=33177600 and .4<=w/h<=2.5) or meta.get('animated'):
                    raise ValueError('H3图片尺寸、比例或动画格式不受支持')
            elif meta.get('duration',0)<2:
                raise ValueError('H3参考音视频至少2秒')
    if protocol=='seedance_media' and sum(m['bytes'] for m in metas)>70*1024*1024:
        raise ValueError('参考图片总大小超过70MiB')
    if protocol=='dmc_h3':
        for kind in ('video','audio'):
            if sum(min(15,m.get('duration',0)) for m in metas if m['kind']==kind)>15:
                raise ValueError('参考视频和独立音频分别不能超过15秒有效总时长')


def reference_signer():
    return URLSafeTimedSerializer(current_app.secret_key,salt='huishi-video-reference-v1')


def save_reference(user_id,data,kind):
    if len(data)>50_000_000:
        raise ValueError('参考素材不能超过50MB')
    meta=inspect_media(data,kind)
    asset_id=secrets.token_hex(20)
    key=f'vref_{asset_id}.{meta["extension"]}'
    get_upload_storage().save_bytes(key,data,meta['mime'])
    get_db().execute('INSERT INTO media_reference_assets(id,user_id,storage_key,metadata_json,created_at) VALUES (?,?,?,?,?)',
                     (asset_id,user_id,key,json.dumps(meta),utc_now()))
    get_db().commit()
    return {'id':asset_id,**meta}


def prepare_multipart_submission(user_id, payload, uploads, *, provider_id=None):
    """Deduplicate logical multipart requests before allocating reference assets."""
    import hashlib
    from huishi.media_tasks import request_replay
    uploads=[file for file in uploads if file.filename]
    if len(uploads)>30:
        raise ValueError('参考素材数量不能超过30')
    raw_subject_index = payload.get('subject_index')
    subject_index = None
    if raw_subject_index not in (None, '', '-1'):
        try:
            subject_index = int(raw_subject_index)
        except (TypeError, ValueError) as exc:
            raise ValueError('主体图片索引无效') from exc
        if subject_index < 0 or subject_index >= len(uploads):
            raise ValueError('主体图片索引无效')
        if not str(uploads[subject_index].mimetype or '').lower().startswith('image/'):
            raise ValueError('主体必须是图片')
    identity={key:payload.get(key) for key in ('model','prompt','duration_seconds','resolution','ratio','reference_mode','camera_movement')}
    identity['subject_index'] = subject_index
    raw_dialogue = str(payload.get('dialogue_id') or '').strip()
    try:
        identity['dialogue_id'] = int(raw_dialogue) if raw_dialogue else None
    except ValueError as exc:
        raise ValueError('对话参数无效') from exc
    identity['create_dialogue'] = str(payload.get('create_dialogue') or '') == '1'
    if provider_id is not None:
        identity['test_provider_id']=provider_id
    identity['file_hashes']=[]
    for file in uploads:
        digest=hashlib.sha256()
        size=0
        while chunk:=file.stream.read(65536):
            size+=len(chunk)
            if size>50_000_000:
                raise ValueError('参考素材不能超过50MB')
            digest.update(chunk)
        identity['file_hashes'].append(digest.hexdigest())
        file.stream.seek(0)
    existing=request_replay(user_id,payload['request_key'],identity) if payload.get('request_key') else None
    if existing:
        return payload,identity,existing
    if uploads:
        saved_assets=[]
        for file in uploads:
            kind='video' if file.mimetype.startswith('video/') else 'audio' if file.mimetype.startswith('audio/') else 'image'
            asset=save_reference(user_id,file.stream.read(50_000_001),kind)
            saved_assets.append((asset, kind))
        if subject_index is not None:
            selected = saved_assets[subject_index]
            saved_assets = [selected, *saved_assets[:subject_index], *saved_assets[subject_index + 1:]]
        references=[]
        for index,(asset, kind) in enumerate(saved_assets):
            mode=payload.get('reference_mode') or 'reference'
            role=('first_frame' if index==0 else 'last_frame') if mode=='keyframes' else mode if mode in ('first_frame','last_frame') else 'reference_'+kind
            references.append({'id':asset['id'],'role':role,'is_subject':subject_index is not None and index == 0})
        payload={**payload,'references':references}
        if subject_index is not None:
            payload['subject_reference_id'] = references[0]['id']
    return payload,identity,None


def prepare_references(user_id,protocol,caps,request,references):
    if not isinstance(references,list) or len(references)>30:
        raise ValueError('参考素材数量或格式错误')
    content=[{'type':'text','text':request['prompt']}]
    metas=[]
    keyframes={}
    subject_reference_id = None
    for ref in references:
        if not isinstance(ref,dict):
            raise ValueError('参考素材格式错误')
        asset=get_db().execute('SELECT * FROM media_reference_assets WHERE id=? AND user_id=?',(str(ref.get('id') or ''),user_id)).fetchone()
        if not asset:
            raise ValueError('参考素材不存在或不属于当前用户')
        meta=json.loads(asset['metadata_json'])
        # Inspect stored bytes again instead of trusting submitted/browser metadata.
        source=get_upload_storage().ensure_local(asset['storage_key'])
        meta=inspect_media(source.read_bytes(),meta['kind'])
        metas.append(meta)
        if ref.get('is_subject') is True:
            if meta['kind'] != 'image':
                raise ValueError('主体必须是图片')
            if subject_reference_id is not None:
                raise ValueError('只能绑定一个主体图片')
            subject_reference_id = str(asset['id'])
        role=ref.get('role') or 'reference_'+meta['kind']
        if role in ('first_frame','last_frame'):
            keyframes[role]=meta
        token=reference_signer().dumps({'id':asset['id']})
        url=url_for('workspace.signed_media_reference',token=token,_external=True,_scheme='https')
        kind=meta['kind']+'_url'
        nested = {'url': url}
        # H3/JiasuAPI need the inspected media metadata to enforce and forward
        # reference-video/audio constraints. The signed URL remains the only
        # transport location; metadata is not trusted from the browser.
        if meta.get('duration') is not None and kind in ('video_url', 'audio_url'):
            nested['duration_seconds'] = float(meta['duration'])
        if meta.get('mime') and kind in ('video_url', 'audio_url'):
            nested['mime'] = str(meta['mime'])
        content_item={'type':kind,kind:nested,'role':role}
        if ref.get('is_subject') is True:
            content_item['is_subject'] = True
        content.append(content_item)
    validate_reference_metadata(protocol,metas)
    if len(keyframes)==2:
        first,last=keyframes['first_frame'],keyframes['last_frame']
        if abs((first['width']/first['height'])/(last['width']/last['height'])-1)>.02:
            raise ValueError('H3首尾帧比例差异不能超过2%')
    normalized = {**request,'content':content}
    if subject_reference_id:
        normalized['subject_reference_id'] = subject_reference_id
    return validate_video_request(request['model'],caps,normalized)
