import json,time
import pytest
from exile.firebase_sharing import FirebaseClient

class FakeFirebase(FirebaseClient):
    database={}
    def refresh(self):
        if not self.auth:
            uid='u'+str(len(self.database)+int(time.time_ns()))
            self.auth={'uid':uid,'id_token':'test','refresh_token':'test','expires_at':time.time()+10000};self.uid=uid;self.member=uid
    def db(self,method,path='',data=None):
        self.refresh(); root=self.database.setdefault(self.group,{})
        if not path:return json.loads(json.dumps(root))
        pieces=path.split('/');node=root
        for part in pieces[:-1]:node=node.setdefault(part,{})
        key=pieces[-1]
        if method=='GET':return json.loads(json.dumps(node.get(key)))
        if method=='PUT':node[key]=json.loads(json.dumps(data));return data
        if method=='PATCH':node.setdefault(key,{}).update(data);return data
        if method=='DELETE':node.pop(key,None);return None

def test_group_chat_shares_and_invite():
    FakeFirebase.database={};a=FakeFirebase();b=FakeFirebase()
    x=a.request('POST','groups',{'name':'Alice','group':'Test'});assert len(x['invite'])==32
    b.request('POST','join',{'name':'Bob','invite':x['invite']})
    a.request('PUT','tabs/currency',{'title':'Currency','league':'Test','items':[{'name':'Vaal Orb','quantity':10,'entity':123}]})
    b.request('POST','messages',{'text':'Hello'})
    state=a.request('GET','state')
    assert len(state['members'])==2 and state['shares'][0]['data']['items']==[{'name':'Vaal Orb','quantity':10}]
    assert any(e['text']=='Hello' for e in state['events'])
    a.request('DELETE','tabs/currency');assert not a.request('GET','state')['shares']
    b.request('DELETE','session');assert len(a.request('GET','state')['members'])==1

def test_invalid_invite_rejected():
    with pytest.raises(ValueError):FakeFirebase().request('POST','join',{'name':'Bob','invite':'short'})


def test_stash_activity_occurs_once_per_scope():
    FakeFirebase.database={};a=FakeFirebase();x=a.request('POST','groups',{'name':'Alice','group':'Test'})
    for key in ('first','second'):
        a.request('PUT','tabs/'+key,{'title':key,'scope':'personal','league':'Test','items':[]})
    events=a.request('GET','state')['events']
    assert sum(e['text']=='Alice has shared Personal stash.' for e in events)==1
    assert not any('first' in e['text'] or 'second' in e['text'] for e in events)
    a.request('DELETE','tabs/first')
    assert not any('unshared' in e['text'] for e in a.request('GET','state')['events'])
    a.request('DELETE','tabs/second')
    assert sum(e['text']=='Alice has unshared Personal stash.' for e in a.request('GET','state')['events'])==1
