"""Download a verified portable cloudflared helper, only on explicit Internet hosting."""
import hashlib
import json
from pathlib import Path
import re
import shutil
from urllib.request import Request,urlopen
from exile.storage import read_json,write_json

API='https://api.github.com/repos/cloudflare/cloudflared/releases/latest'

def file_hash(path):
    hasher=hashlib.sha256()
    with path.open('rb')as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):hasher.update(block)
    return hasher.hexdigest()

def prepare_cloudflared(directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    request=Request(API,headers={'User-Agent':'Waymark','Accept':'application/vnd.github+json'})
    with urlopen(request,timeout=20)as response:release=json.loads(response.read(1_000_000))
    asset=next((a for a in release.get('assets',[])if a['name']=='cloudflared-windows-amd64.exe'),None)
    if not asset:raise ValueError('Cloudflare did not publish the Windows helper in this release.')
    expected=asset.get('digest','').removeprefix('sha256:')
    if not re.fullmatch('[a-f0-9]{64}',expected):raise ValueError('The official download has no SHA-256 verification value.')
    url=asset['browser_download_url']
    if not url.startswith('https://github.com/cloudflare/cloudflared/releases/download/'):
        raise ValueError('Unexpected helper download address.')
    target=directory/('cloudflared-'+expected[:16]+'.exe')
    if target.is_file()and file_hash(target)==expected:return str(target)
    partial=target.with_suffix('.download')
    try:
        with urlopen(Request(url,headers={'User-Agent':'Waymark'}),timeout=60)as response,partial.open('wb')as output:
            size=0
            while True:
                block=response.read(256*1024)
                if not block:break
                size+=len(block)
                if size>150_000_000:raise ValueError('The helper download exceeds its size limit.')
                output.write(block)
        if file_hash(partial)!=expected:raise ValueError('Helper verification failed; it was not started.')
        try:partial.replace(target)
        except OSError as exc:
            if getattr(exc,'winerror',None)!=17:raise
            shutil.copyfile(partial,target)
            if file_hash(target)!=expected:raise ValueError('Helper verification failed after saving.')
        write_json(directory/'cloudflared-source.json',dict(version=release['tag_name'],url=url,sha256=expected))
        return str(target)
    finally:
        if partial.exists():partial.unlink()

def tunnel_url(log):
    match=re.search(r'https://[a-z0-9-]+\.trycloudflare\.com\b',log)
    return match[0]if match else''
