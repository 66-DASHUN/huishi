"""Bounded media fetches with redirect validation and origin-bound credentials."""
import ipaddress
import socket
from urllib.parse import urlsplit,urljoin
import requests
from huishi.network import request_proxy_kwargs


def validate_public_url(url):
    parsed=urlsplit(url)
    if parsed.scheme not in ('https','http') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('媒体下载地址无效')
    addresses=socket.getaddrinfo(parsed.hostname,parsed.port or (443 if parsed.scheme=='https' else 80),type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError('媒体下载必须使用公网地址')


def download_media(provider,url,*,authenticated=False,timeout=120,max_bytes=256*1024*1024,destination=None):
    from huishi.video_api import VideoApiError
    from huishi.video_adapters.common import RetryableVideoError
    credential_origin=urlsplit(str(provider.get('base_url') or ''))[:2]
    for redirect in range(5):
        validate_public_url(url)
        headers={'Accept':'video/*','User-Agent':'HuishiMediaFetcher/1.0'}
        if authenticated and urlsplit(url)[:2]==credential_origin:
            headers['Authorization']='Bearer '+str(provider.get('api_key') or '')
        response=requests.get(url,headers=headers,timeout=(15,timeout),stream=True,allow_redirects=False,
                              **request_proxy_kwargs(provider.get('proxy_url')))
        try:
            if response.status_code in (301,302,303,307,308):
                url=urljoin(url,response.headers.get('Location',''))
                continue
            if response.status_code==409:
                raise RetryableVideoError('视频结果准备中')
            if response.status_code!=200:
                raise RetryableVideoError(f'视频下载返回 HTTP {response.status_code}')
            mime=response.headers.get('Content-Type','').split(';')[0].lower()
            if mime and not (mime.startswith('video/') or mime=='application/octet-stream'):
                raise VideoApiError('下载内容不是视频')
            from contextlib import nullcontext
            chunks=[]
            size=0
            with destination.open('wb') if destination is not None else nullcontext() as output:
                for chunk in response.iter_content(65536):
                    size+=len(chunk)
                    if size>max_bytes:
                        raise VideoApiError('视频下载超过256MiB限制')
                    if output is not None:
                        output.write(chunk)
                    else:
                        chunks.append(chunk)
            if not size:
                raise RetryableVideoError('视频下载结果为空')
            return destination if destination is not None else b''.join(chunks)
        finally:
            response.close()
    raise VideoApiError('视频下载重定向次数过多')
