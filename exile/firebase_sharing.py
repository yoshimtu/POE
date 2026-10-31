"""Firebase group protocol; group identifiers are private 128-bit invite capabilities."""
import json, re, secrets, time
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode
from exile.firebase_auth import API_KEY, DATABASE_URL, anonymous_sign_in
from exile.sharing import clean_item

class FirebaseClient:
    def __init__(self, url=DATABASE_URL, token=''):
        self.url=DATABASE_URL
        self.auth=None; self.group=''; self.uid=''; self.member=''; self.cached_state=None; self.last_full=0; self.last_seen=0; self.versions=None
        if token:
            session=json.loads(token); self.auth=session['auth'];self.group=session['group'];self.uid=self.auth['uid'];self.member=self.uid
    def session(self):
        return json.dumps({'auth':self.auth,'group':self.group},separators=(',',':'))
    def refresh(self):
        if not self.auth:self.auth=anonymous_sign_in();self.uid=self.auth['uid'];self.member=self.uid
        if time.time()<self.auth['expires_at']:return
        body=urlencode({'grant_type':'refresh_token','refresh_token':self.auth['refresh_token']}).encode()
        request=Request('https://securetoken.googleapis.com/v1/token?key='+API_KEY,data=body,method='POST')
        with urlopen(request,timeout=10) as response: result=json.loads(response.read(1_000_000))
        self.auth.update(id_token=result['id_token'],refresh_token=result['refresh_token'],expires_at=time.time()+int(result['expires_in'])-60)
    def db(self,method,path='',data=None):
        self.refresh()
        request=Request(self.url+'/groups/'+self.group+('/'+path if path else '')+'.json?'+urlencode({'auth':self.auth['id_token']}),
            data=json.dumps(data,allow_nan=False).encode() if data is not None else None,
            headers={'Authorization':'Bearer '+self.auth['id_token'],'Content-Type':'application/json'},method=method)
        try:
            with urlopen(request,timeout=10) as response:return json.loads(response.read(12_000_001))
        except HTTPError as exc:
            if exc.code in (401,403):raise ValueError('Firebase denied access. Check the group invite and security rules.') from None
            raise ValueError('Firebase request failed (HTTP %s).'%exc.code) from None
    def mark(self):
        self.db('PUT','versions/'+self.uid,{'value':secrets.token_hex(12)})
    def event(self,text,kind='system',author=''):
        key=f'{int(time.time()*1000):013d}'+secrets.token_hex(6)
        self.db('PUT','events/'+key,dict(author=author,kind=kind,text=text,created=time.time()));self.mark()
    def request(self,method,path,data=None):
        data=data or {};self.refresh();now=time.time()
        if path in ('groups','join') and method=='POST':
            name=str(data.get('name','')).strip()[:50]
            if not name:raise ValueError('Enter a display name.')
            self.group=secrets.token_hex(16) if path=='groups' else str(data.get('invite',''))
            if not re.fullmatch('[a-f0-9]{32}',self.group):raise ValueError('Invalid Firebase invite.')
            if path=='groups':
                self.db('PUT','meta',dict(name=str(data.get('group','Private group'))[:80],owner=self.uid))
            self.db('PUT','members/'+self.uid,dict(name=name,seen=now))
            self.event(name+' joined the group.',author=name)
            return dict(token=self.session(),member=self.uid,invite=self.group if path=='groups' else '')
        if not self.group:raise ValueError('Join a group first.')
        if path=='state' and method=='GET':
            if now-self.last_seen>15:
                self.db('PATCH','members/'+self.uid,{'seen':now});self.last_seen=now
            versions=self.db('GET','versions') or {}
            if self.cached_state is None or versions!=self.versions:
                self.cached_state=self.db('GET') or {};self.versions=versions
            raw=self.cached_state;members=self.db('GET','members') or {};events=raw.get('events') or {};shares=raw.get('shares') or {}
            records=[]
            for owner,kinds in shares.items():
                for kind,items in (kinds or {}).items():
                    for key,entry in (items or {}).items():
                        records.append(dict(owner=owner,owner_name=(members.get(owner) or {}).get('name','Player'),kind=kind,key=key,**entry))
            return dict(version=1,group={'name':(raw.get('meta') or {}).get('name','Group')},member=self.uid,
                members=[dict(id=k,**v) for k,v in members.items()],shares=records,events=[events[k] for k in sorted(events)[-200:]])
        if path=='presence' and method=='POST':
            member=self.db('GET','members/'+self.uid) or {};name=member.get('name','Player')
            self.event(name+' came online.',author=name);return {'ok':True}
        if path=='session' and method=='DELETE':
            member=self.db('GET','members/'+self.uid) or {};name=member.get('name','Player')
            self.event(name+' left the group.',author=name)
            self.db('DELETE','shares/'+self.uid);self.mark();self.db('DELETE','members/'+self.uid);return {'ok':True}
        if path=='messages' and method=='POST':
            text=str(data.get('text','')).strip()
            if not text or len(text)>1000:raise ValueError('Messages must contain 1–1000 characters.')
            member=self.db('GET','members/'+self.uid) or {};self.event(text,'message',member.get('name','Player'));return {'ok':True}
        bits=path.split('/')
        if len(bits)!=2 or bits[0] not in ('tabs','items') or not bits[1].isalnum():raise ValueError('Unknown operation.')
        dest='shares/'+self.uid+'/'+path
        if method=='DELETE':
            old=self.db('GET',dest)
            self.db('DELETE',dest);self.mark()
            if old:
                member=self.db('GET','members/'+self.uid) or {};name=member.get('name','Player');item=old.get('data',{})
                if bits[0]=='tabs':
                    scope=item.get('scope','personal');remaining=self.db('GET','shares/'+self.uid+'/tabs') or {}
                    if not any((entry.get('data') or {}).get('scope')==scope for entry in remaining.values()):
                        self.event(name+' has unshared '+scope.title()+' stash.',author=name)
                else:self.event(name+' unshared '+item.get('title','an item')+'.',author=name)
            return {'ok':True}
        if method!='PUT':raise ValueError('Unsupported operation.')
        body={'title':str(data.get('title','Shared item'))[:120],'league':str(data.get('league',''))[:100]}
        if not body['league']:raise ValueError('Select a league in Settings first.')
        if bits[0]=='tabs':body.update(scope=data.get('scope','personal'),partial=True,items=[clean_item(i) for i in data.get('items',[])[:3000]])
        else:body.update(item=clean_item(data.get('item',{})),text=str(data.get('text',''))[:30000])
        old=self.db('GET',dest)
        existing=self.db('GET','shares/'+self.uid+'/tabs') or {} if bits[0]=='tabs' and not old else {}
        self.db('PUT',dest,dict(data=body,updated=now));self.mark()
        if not old:
            member=self.db('GET','members/'+self.uid) or {};name=member.get('name','Player')
            if bits[0]=='tabs':
                scope=body['scope']
                if not any((entry.get('data') or {}).get('scope')==scope for entry in existing.values()):
                    self.event(name+' has shared '+scope.title()+' stash.',author=name)
            else:self.event(name+' shared '+body['title']+'.',author=name)
        return {'ok':True}
