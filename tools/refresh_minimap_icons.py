"""Refresh bundled minimap art from user-selected public icon catalogs."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request,urlopen
import json,time
from html.parser import HTMLParser

root=Path(__file__).resolve().parents[1]
destination=root/'plugins/radar/icons'
class Icons(HTMLParser):
    def __init__(self):super().__init__();self.icons={}
    def handle_starttag(self,tag,attrs):
        values=dict(attrs)
        if tag=='img' and values.get('alt') and values.get('src'):
            self.icons[values['alt']]=values['src']

manifest={}
for game in ('poe1','poe2'):
    page='https://poedb.tw/us/MinimapIcons'if game=='poe1'else'https://poe2db.tw/us/MinimapIcons'
    parser=Icons();parser.feed(urlopen(Request(page,headers={'User-Agent':'Mozilla/5.0','Referer':page}),timeout=20).read().decode())
    catalog=parser.icons
    for name,url in catalog.items():
        if '/minimap/player/' not in url:continue
        if game=='poe2' and name not in ('RareMonsterAlive','UniqueMonsterAlive'):continue
        manifest[f'{game}:{name}']=dict(file=f'icons/{game}/{name}.webp',url=url)

def fetch(entry):
    key,info=entry;path=destination.parent/info['file']
    if path.is_file() and path.read_bytes()[:4]==b'RIFF':return key
    path.parent.mkdir(parents=True,exist_ok=True)
    headers={'User-Agent':'Mozilla/5.0','Referer':'https://poe2db.tw/us/MinimapIcons'if key.startswith('poe2:')else'https://poedb.tw/us/MinimapIcons','Accept':'image/avif,image/webp,image/*,*/*;q=0.8'}
    for attempt in range(3):
        try:
            data=urlopen(Request(info['url']+('?v=1'if attempt else ''),headers=headers),timeout=20).read(1_000_000)
            if data[:4]!=b'RIFF' or data[8:12]!=b'WEBP':raise ValueError('Unexpected image format')
            path.write_bytes(data);return key
        except Exception:
            if attempt==2:raise
            time.sleep(.5)

if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=4)as pool:
        results=list(pool.map(fetch,manifest.items()))
    (destination.parent/'icon_catalog.json').write_text(json.dumps(dict(sources=['https://poedb.tw/us/MinimapIcons','https://poe2db.tw/us/MinimapIcons'],icons=manifest),indent=2)+'\n',encoding='utf-8')
    print(f'Bundled {len(results)} icons')
