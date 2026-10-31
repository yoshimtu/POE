"""Self-hosted private groups. HTTP/JSON v1; SQLite state, hashed invite/session secrets."""
import argparse
import hashlib
import json
import secrets
import string
import sqlite3
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from exile.sharing import MAX_BODY,clean_item

def digest(value):return hashlib.sha256(value.encode()).hexdigest()

class GroupStore:
    def __init__(self,path):
        self.path=str(path);self.lock=threading.Lock();self.attempts={}
        with self.connect()as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS groups(id TEXT PRIMARY KEY,name TEXT NOT NULL,invite TEXT UNIQUE NOT NULL);
            CREATE TABLE IF NOT EXISTS members(id TEXT PRIMARY KEY,group_id TEXT NOT NULL,name TEXT NOT NULL,token TEXT UNIQUE NOT NULL,seen REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS shares(owner TEXT NOT NULL,kind TEXT NOT NULL,key TEXT NOT NULL,data TEXT NOT NULL,updated REAL NOT NULL,PRIMARY KEY(owner,kind,key));
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,group_id TEXT NOT NULL,author TEXT NOT NULL,kind TEXT NOT NULL,text TEXT NOT NULL,created REAL NOT NULL);
            ''')

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path);db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()

    def event(self,db,group,author,kind,text,now):
        db.execute("INSERT INTO events(group_id,author,kind,text,created) VALUES(?,?,?,?,?)",(group,author,kind,text,now))
        db.execute("DELETE FROM events WHERE group_id=? AND id NOT IN (SELECT id FROM events WHERE group_id=? ORDER BY id DESC LIMIT 200)",(group,group))

    def handle(self,method,path,body,token,peer):
        with self.lock,self.connect()as db:
            now=time.time()
            if path in ('groups','join')and method=='POST':
                bucket=(peer,int(now//60));self.attempts={k:v for k,v in self.attempts.items()if k[1]>=bucket[1]-1}
                if len(self.attempts)>2048:raise ValueError('Server busy; try again shortly.')
                self.attempts[bucket]=self.attempts.get(bucket,0)+1
                if self.attempts[bucket]>20:raise ValueError('Too many attempts; wait a minute.')
                name=str(body.get('name','')).strip()[:50]
                if not name:raise ValueError('Enter a display name.')
                invite=''
                if path=='groups':
                    if db.execute('SELECT COUNT(*) FROM groups').fetchone()[0]>=1000:raise ValueError('Server group limit reached.')
                    group=secrets.token_hex(12)
                    alphabet=string.ascii_letters+string.digits
                    for _ in range(20):
                        invite="".join(secrets.choice(alphabet) for _ in range(6))
                        if not db.execute("SELECT 1 FROM groups WHERE invite=?",(digest(invite),)).fetchone():break
                    else:raise ValueError("Could not create a unique invite. Try again.")
                    title=str(body.get('group','Private group')).strip()[:80]or'Private group'
                    db.execute('INSERT INTO groups VALUES(?,?,?)',(group,title,digest(invite)))
                else:
                    row=db.execute('SELECT id FROM groups WHERE invite=?',(digest(str(body.get('invite',''))),)).fetchone()
                    if not row:raise ValueError('Invite code not found.')
                    group=row['id']
                if db.execute('SELECT COUNT(*) FROM members WHERE group_id=?',(group,)).fetchone()[0]>=32:raise ValueError('This group is full.')
                if db.execute('SELECT 1 FROM members WHERE group_id=? AND LOWER(name)=LOWER(?)',(group,name)).fetchone():raise ValueError('Choose a different display name in this group.')
                member=secrets.token_hex(12);secret=secrets.token_urlsafe(32)
                db.execute('INSERT INTO members VALUES(?,?,?,?,?)',(member,group,name,digest(secret),now))
                self.event(db,group,name,'system',name+' joined the group.',now)
                return dict(token=secret,member=member,invite=invite)
            member=db.execute('SELECT * FROM members WHERE token=?',(digest(token),)).fetchone()if token else None
            if not member:raise PermissionError('Session expired or invalid. Create or join a group again.')
            owner=member['id'];group=member['group_id']
            if now-member['seen']>30 and path!='presence':self.event(db,group,member['name'],'system',member['name']+' came online.',now)
            db.execute('UPDATE members SET seen=? WHERE id=?',(now,owner))
            if path=='state'and method=='GET':
                info=db.execute('SELECT id,name FROM groups WHERE id=?',(group,)).fetchone()
                members=[dict(id=r['id'],name=r['name'],seen=r['seen'])for r in db.execute('SELECT * FROM members WHERE group_id=?',(group,))]
                rows=db.execute('SELECT s.*,m.name FROM shares s JOIN members m ON m.id=s.owner WHERE m.group_id=? ORDER BY s.updated DESC',(group,))
                shares=[dict(owner=r['owner'],owner_name=r['name'],kind=r['kind'],key=r['key'],updated=r['updated'],data=json.loads(r['data']))for r in rows]
                events=[dict(r) for r in db.execute('SELECT id,author,kind,text,created FROM events WHERE group_id=? ORDER BY id DESC LIMIT 200',(group,))]
                return dict(version=1,group=dict(info),members=members,shares=shares,member=owner,events=list(reversed(events)))
            if path=='presence' and method=='POST':
                self.event(db,group,member['name'],'system',member['name']+' came online.',now)
                return dict(ok=True)
            if path=='messages' and method=='POST':
                text=str(body.get('text','')).strip()
                if not text or len(text)>1000:raise ValueError('Messages must contain 1–1000 characters.')
                self.event(db,group,member['name'],'message',text,now)
                return dict(ok=True)
            if path=='session'and method=='DELETE':
                self.event(db,group,member['name'],'system',member['name']+' left the group.',now)
                db.execute('DELETE FROM shares WHERE owner=?',(owner,));db.execute('DELETE FROM members WHERE id=?',(owner,))
                if not db.execute('SELECT 1 FROM members WHERE group_id=?',(group,)).fetchone():
                    db.execute('DELETE FROM events WHERE group_id=?',(group,));db.execute('DELETE FROM groups WHERE id=?',(group,))
                return dict(ok=True)
            bits=path.split('/')
            if len(bits)!=2 or bits[0]not in ('tabs','items')or not bits[1].isalnum()or len(bits[1])>64:raise ValueError('Unknown operation.')
            kind,key=bits
            if method=='DELETE':
                previous=db.execute('SELECT data FROM shares WHERE owner=? AND kind=? AND key=?',(owner,kind,key)).fetchone()
                db.execute('DELETE FROM shares WHERE owner=? AND kind=? AND key=?',(owner,kind,key))
                if previous:
                    old=json.loads(previous['data'])
                    if kind=='tabs':
                        scope=old.get('scope','personal');rows=db.execute("SELECT data FROM shares WHERE owner=? AND kind='tabs'",(owner,))
                        if not any(json.loads(r['data']).get('scope')==scope for r in rows):self.event(db,group,member['name'],'system',member['name']+' has unshared '+scope.title()+' stash.',now)
                    else:self.event(db,group,member['name'],'system',member['name']+' unshared '+old.get('title','an item')+'.',now)
                return dict(ok=True)
            if method!='PUT':raise ValueError('Unsupported operation.')
            league=str(body.get('league','')).strip()[:100]
            if not league:raise ValueError('Select an economy league in Settings first.')
            is_new=not db.execute('SELECT 1 FROM shares WHERE owner=? AND kind=? AND key=?',(owner,kind,key)).fetchone()
            if is_new:
                count=db.execute('SELECT COUNT(*) FROM shares WHERE owner=?',(owner,)).fetchone()[0]
                if count>=512:raise ValueError('Withdraw a share before adding more (512 per member).')
            data=dict(league=league,title=str(body.get('title','Shared item'))[:120])
            if kind=='tabs':
                items=body.get('items')
                if not isinstance(items,list)or len(items)>3000 or any(not isinstance(i,dict)for i in items):raise ValueError('Invalid tab contents (maximum 3000 loaded items).')
                data.update(items=[clean_item(i)for i in items],partial=True,scope='guild'if body.get('scope')=='guild'else'personal')
            else:
                if not isinstance(body.get('item'),dict):raise ValueError('Invalid item.')
                data.update(item=clean_item(body.get('item',{})),text=str(body.get('text',''))[:30000])
                if not data['item'].get('name'):raise ValueError('No item selected.')
            encoded=json.dumps(data,allow_nan=False)
            # Bound a complete group response, not only each individual upload.
            size=db.execute('SELECT COALESCE(SUM(LENGTH(data)),0) FROM shares WHERE owner IN (SELECT id FROM members WHERE group_id=?)AND NOT(owner=? AND kind=? AND key=?)',(group,owner,kind,key)).fetchone()[0]
            if size+len(encoded)>8_000_000:raise ValueError('Group storage is full. Withdraw older shares.')
            db.execute('INSERT OR REPLACE INTO shares VALUES(?,?,?,?,?)',(owner,kind,key,encoded,now))
            if is_new:
                if kind=='tabs':
                    rows=db.execute("SELECT data FROM shares WHERE owner=? AND kind='tabs' AND key!=?",(owner,key))
                    if not any(json.loads(r['data']).get('scope')==data['scope'] for r in rows):self.event(db,group,member['name'],'system',member['name']+' has shared '+data['scope'].title()+' stash.',now)
                else:self.event(db,group,member['name'],'system',member['name']+' shared '+data['title']+'.',now)
            return dict(ok=True)

def make_server(address,path):
    store=GroupStore(path)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass  # never log credentials or item payloads
        def setup(self):
            super().setup();self.connection.settimeout(10)
        def do_GET(self):self.dispatch()
        def do_POST(self):self.dispatch()
        def do_PUT(self):self.dispatch()
        def do_DELETE(self):self.dispatch()
        def dispatch(self):
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<=length<=MAX_BODY:raise ValueError('Request too large.')
                if not self.path.startswith('/v1/'):raise ValueError('Unsupported protocol.')
                body=json.loads(self.rfile.read(length))if length else{}
                if not isinstance(body,dict):raise ValueError('Expected an object.')
                auth=self.headers.get('Authorization','');token=auth[7:]if auth.startswith('Bearer ')else''
                result=store.handle(self.command,self.path[4:],body,token,self.client_address[0]);status=200
            except PermissionError as exc:result=dict(error=str(exc));status=401
            except (ValueError,TypeError,KeyError)as exc:result=dict(error=str(exc));status=400
            except Exception:result=dict(error='Server could not complete this request.');status=500
            raw=json.dumps(result,allow_nan=False).encode();self.send_response(status)
            self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)
    class BoundedServer(ThreadingHTTPServer):
        daemon_threads=True
        def __init__(self,*args):
            self.slots=threading.BoundedSemaphore(32);super().__init__(*args)
        def process_request(self,request,client_address):
            if not self.slots.acquire(blocking=False):self.shutdown_request(request);return
            try:super().process_request(request,client_address)
            except Exception:self.slots.release();raise
        def process_request_thread(self,*args):
            try:super().process_request_thread(*args)
            finally:self.slots.release()
    return BoundedServer(address,Handler)

def main(args=None):
    parser=argparse.ArgumentParser(description='Waymark private group server')
    parser.add_argument('--bind',default='127.0.0.1');parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--database',default=str(Path.home()/'Waymark-groups.sqlite'))
    options=parser.parse_args(args)
    server=make_server((options.bind,options.port),options.database)
    print(f'Waymark server listening on {options.bind}:{server.server_port}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
