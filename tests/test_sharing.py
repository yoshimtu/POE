import threading
import pytest
from exile.sharing import SharingClient,clean_item
from exile.sharing_server import make_server

@pytest.fixture
def service(tmp_path):
    server=make_server(('127.0.0.1',0),tmp_path/'groups.sqlite')
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    yield 'http://127.0.0.1:'+str(server.server_port),server,tmp_path/'groups.sqlite'
    server.shutdown();server.server_close();worker.join(timeout=2)

def join(url,name,invite=None):
    client=SharingClient(url)
    result=client.request('POST','join'if invite else'groups',dict(name=name,invite=invite,group='Friends'))
    client.token=result['token'];return client,result

def test_two_clients_share_tabs_items_withdraw_and_private_groups(service):
    url,server,path=service
    alice,a=join(url,'Alice');bob,b=join(url,'Bob',a['invite']);outsider,c=join(url,'Outsider')
    tab=dict(title='Currency',scope='personal',league='Test league',items=[dict(name='Vaal Orb',quantity=10,entity=123456,screen=[10,20])])
    alice.request('PUT','tabs/currency',tab)
    state=bob.request('GET','state');assert len(state['members'])==2
    assert state['shares'][0]['data']['items']==[dict(name='Vaal Orb',quantity=10)]
    assert state['shares'][0]['data']['partial']is True
    assert not outsider.request('GET','state')['shares']
    bob.request('DELETE','tabs/currency')  # cannot withdraw Alice's share
    assert len(alice.request('GET','state')['shares'])==1
    bob.request('PUT','items/ring',dict(title='Ring',league='Test league',item=dict(name='Rare ring',mods=['+80 to maximum Life']),text='Rare ring tooltip'))
    assert len(alice.request('GET','state')['shares'])==2
    tab['items']=[];alice.request('PUT','tabs/currency',tab)
    assert next(s for s in bob.request('GET','state')['shares']if s['kind']=='tabs')['data']['items']==[]
    alice.request('DELETE','tabs/currency');assert len(bob.request('GET','state')['shares'])==1
    bob.request('DELETE','session');assert not alice.request('GET','state')['shares']
    with pytest.raises(ValueError,match='Session expired'):bob.request('GET','state')
    with pytest.raises(ValueError,match='Session expired'):SharingClient(url,'bad').request('GET','state')

def test_invite_auth_validation_limits_and_restart_persistence(service):
    url,server,path=service
    alice,a=join(url,'Alice')
    with pytest.raises(ValueError,match='Invite code'):join(url,'Eve','wrong')
    with pytest.raises(ValueError,match='different display'):join(url,'alice',a['invite'])
    with pytest.raises(ValueError,match='league'):alice.request('PUT','tabs/tab',dict(title='Tab',items=[]))
    with pytest.raises(ValueError,match='Invalid tab'):alice.request('PUT','tabs/tab',dict(league='Test',items='bad'))
    with pytest.raises(ValueError,match='Invalid item'):alice.request('PUT','items/item',dict(league='Test',item='bad'))
    # A separate server process can reopen the same persisted group database.
    other=make_server(('127.0.0.1',0),path);thread=threading.Thread(target=other.serve_forever,daemon=True);thread.start()
    try:
        state=SharingClient('http://127.0.0.1:'+str(other.server_port),a['token']).request('GET','state')
        assert state['group']['name']=='Friends'and state['member']==a['member']
    finally:other.shutdown();other.server_close();thread.join(timeout=2)
    assert a['token'].encode()not in path.read_bytes()and a['invite'].encode()not in path.read_bytes()

def test_sharing_ui_empty_tabs_and_selected_data(tmp_path,monkeypatch):
    import exile.app as ui
    from exile.model import Snapshot
    monkeypatch.setattr(ui,'data_root',lambda:tmp_path)
    window=ui.MainWindow();window.timer.stop();window.connections.timer.stop()
    try:
        pane=window.connections
        window.snapshot=Snapshot();window.snapshot.stash_tabs=[dict(scope='personal',index=1,name='Empty',loaded=True)]
        assert pane.loaded_tabs()=={('personal',1,'Empty'):[]}
        pane.poll();assert pane.tabs.count()==1
        assert pane.client is None and not pane.auto.isChecked()
        pane.share_item();assert 'Connect'in pane.status.text()
        assert clean_item(dict(name='Item',entity=123,metadata='private',components=[1],price_label='2c'))==dict(name='Item',price_label='2c')
    finally:window.close()

def test_two_desktop_clients_create_join_publish_and_leave(service,tmp_path):
    import time
    from types import SimpleNamespace
    from PySide6.QtWidgets import QApplication
    from exile.connections import Connections
    from exile.model import Snapshot
    def fake(name):
        return SimpleNamespace(config={},data=tmp_path/name,snapshot=Snapshot(source='live',loading=False),
            economy_league=lambda:'Test league',save=lambda:None,
            latest_shared_item=dict(name='Ring',league='Test league',item=dict(name='Ring',mods=['+80 to maximum Life']),text='Ring tooltip'))
    a=Connections(fake('a'));b=Connections(fake('b'));a.timer.stop();b.timer.stop()
    def until(condition):
        end=time.monotonic()+5
        while not condition()and time.monotonic()<end:QApplication.processEvents();time.sleep(.005)
        assert condition()
    try:
        a.server.setText(service[0]);a.name.setText('Alice');a.group.setText('Party');a.connect_group(True)
        until(lambda:a.client is not None and bool(a.state))
        b.server.setText(service[0]);b.name.setText('Bob');b.invite.setText(a.invite.text());b.connect_group(False)
        until(lambda:b.client is not None and len(b.state.get('members',[]))==2)
        a.app.snapshot.stash=[dict(name='Vaal Orb',quantity=10,scope='guild',tab_index=1,tab='Guild currency')]
        a.app.snapshot.captured_at=time.monotonic();a.poll();until(lambda:not a.busy)
        a.guild_share.setChecked(True);until(lambda:len(a.state.get('shares',[]))==1 and not a.busy)
        b.poll();until(lambda:len(b.state.get('shares',[]))==1 and not b.busy)
        assert b.state['shares'][0]['data']['scope']=='guild'
        a.share_item();until(lambda:len(a.state.get('shares',[]))==2 and not a.busy)
        b.poll();until(lambda:len(b.state.get('shares',[]))==2 and not b.busy)
        b.search.setText('maximum life')
        assert sum(not b.table.isRowHidden(row)for row in range(b.table.rowCount()))==1
        a.leave();until(lambda:a.client is None and not a.busy)
        b.poll();until(lambda:len(b.state.get('members',[]))==1 and not b.busy)
        assert not b.state['shares']
    finally:a.shutdown();b.shutdown();a.close();b.close()


def test_chat_activity_is_private_and_suppresses_repeated_tab_updates(service):
    url,server,path=service
    alice,a=join(url,'Alice');bob,b=join(url,'Bob',a['invite']);other,_=join(url,'Other')
    assert len(a['invite'])==6 and a['invite'].isalnum()
    alice.request('POST','messages',{'text':'Hello, group!'})
    tab=dict(title='Currency',scope='personal',league='Test',items=[])
    alice.request('PUT','tabs/currency',tab);alice.request('PUT','tabs/currency',tab)
    events=bob.request('GET','state')['events']
    assert any(e['text']=='Hello, group!' and e['author']=='Alice' for e in events)
    assert sum('shared Personal stash' in e['text'] for e in events)==1
    assert not any(e['text']=='Hello, group!' for e in other.request('GET','state')['events'])
    alice.request('DELETE','tabs/currency')
    assert any('unshared Personal stash' in e['text'] for e in bob.request('GET','state')['events'])
    with pytest.raises(ValueError):alice.request('POST','messages',{'text':'x'*1001})

def test_bulk_sharing_and_combined_invite(service,tmp_path):
    import time
    from types import SimpleNamespace
    from PySide6.QtWidgets import QApplication
    from exile.connections import Connections
    from exile.model import Snapshot
    def fake(name):
        return SimpleNamespace(config={},data=tmp_path/name,snapshot=Snapshot(source='live',loading=False),economy_league=lambda:'Test',save=lambda:None)
    a=Connections(fake('a'));b=Connections(fake('b'));a.timer.stop();b.timer.stop()
    def until(condition):
        end=time.monotonic()+5
        while not condition() and time.monotonic()<end:QApplication.processEvents();time.sleep(.005)
        assert condition()
    try:
        a.server.setText(service[0]);a.name.setText('Alice');a.group.setText('Party');a.connect_group(True)
        until(lambda:a.client is not None and bool(a.state) and not a.busy)
        b.name.setText('Bob');b.choose_join();b.join_code.setText(service[0]+'-'+a.invite.text());b.join_combined()
        until(lambda:b.client is not None and bool(b.state) and not b.busy)
        a.app.snapshot.stash_tabs=[dict(scope='personal',index=0,name='Currency',loaded=True),dict(scope='personal',index=1,name='Maps',loaded=True),dict(scope='guild',index=0,name='Guild',loaded=True)]
        a.app.snapshot.stash=[dict(name='Vaal Orb',quantity=10,scope='personal',tab_index=0,tab='Currency')]
        a.app.snapshot.captured_at=time.monotonic();a.personal_share.setChecked(True)
        until(lambda:len(a.state.get('shares',[]))==2 and not a.busy)
        assert {x['data']['title'] for x in a.state['shares']}=={'Currency','Maps'}
        a.personal_share.setChecked(False)
        until(lambda:not a.state.get('shares') and not a.busy)
        assert a.app.config['connections']['personal_share'] is False
        b.message.setText('Hello');b.send_message();until(lambda:not b.busy and not b.message.text())
        a.poll();until(lambda:any(e['text']=='Hello' for e in a.state.get('events',[])) and not a.busy)
    finally:a.shutdown();b.shutdown();a.close();b.close()


def test_host_and_join_steps_accept_a_stable_server(service,tmp_path):
    import time
    from types import SimpleNamespace
    from PySide6.QtWidgets import QApplication
    from exile.connections import Connections
    from exile.model import Snapshot
    def fake(name):return SimpleNamespace(config={},data=tmp_path/name,snapshot=Snapshot(),economy_league=lambda:'Test',save=lambda:None)
    a=Connections(fake('a'));b=Connections(fake('b'));a.timer.stop();b.timer.stop()
    def until(condition):
        end=time.monotonic()+5
        while not condition() and time.monotonic()<end:QApplication.processEvents();time.sleep(.005)
        assert condition()
    try:
        a.name.setText('Alice');a.choose_host('internet');a.group.setText('Party');a.existing_server.setText(service[0]);a.start_host_group()
        until(lambda:a.client is not None and bool(a.state) and not a.busy)
        assert a.steps.currentIndex()==3 and a.invite_display.text()==service[0]+'-'+a.invite.text()
        b.name.setText('Bob');b.choose_join();b.join_code.setText(a.invite_display.text());b.join_combined()
        until(lambda:b.client is not None and bool(b.state) and not b.busy)
        assert b.group_heading.text()=='Party' and b.steps.currentIndex()==3
    finally:a.shutdown();b.shutdown();a.close();b.close()


def test_code_only_invite_selects_firebase(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from exile.connections import Connections
    from exile.model import Snapshot
    from exile.firebase_auth import DATABASE_URL
    fake=SimpleNamespace(config={},data=tmp_path,snapshot=Snapshot(),economy_league=lambda:'Test',save=lambda:None)
    pane=Connections(fake);pane.timer.stop();calls=[]
    try:
        pane.connect_group=lambda create:calls.append(create)
        pane.join_code.setText('a'*32);pane.join_combined()
        assert pane.server.text()==DATABASE_URL and pane.invite.text()=='a'*32 and calls==[False]
        pane.update_invite_display();assert pane.invite_display.text()=='a'*32
        pane.join_code.setText(DATABASE_URL+'-'+'b'*32);pane.join_combined()
        assert pane.invite.text()=='b'*32
    finally:pane.shutdown();pane.close()


def test_chat_item_link_is_clickable_and_escapes_user_text(tmp_path):
    from types import SimpleNamespace
    import time
    from exile.connections import Connections
    from exile.model import Snapshot
    fake=SimpleNamespace(config={},data=tmp_path,snapshot=Snapshot(),economy_league=lambda:'Test',save=lambda:None)
    pane=Connections(fake);pane.timer.stop();pane.link_timer.stop()
    try:
        now=time.time();share=dict(owner='a',owner_name='Alice',kind='items',key='test',updated=now,data=dict(title='<Ring>',league='Test',text='Item tooltip'))
        pane.apply_state(dict(member='a',group=dict(name='Friends'),members=[],shares=[share],events=[dict(created=now,author='Alice',kind='system',text='Alice shared <Ring>.')]))
        assert len(pane.chat_items)==1 and pane.chat_items['0']['data']['text']=='Item tooltip'
        assert 'href="item:0"' in pane.chat.toHtml() and '<Ring>' not in pane.chat.toHtml()
        assert not pane.linked_share.isChecked()
    finally:pane.shutdown();pane.close()


def test_stash_search_can_filter_local_and_remote_tabs(tmp_path,monkeypatch):
    import exile.app as ui
    from exile.model import Snapshot
    monkeypatch.setattr(ui,'data_root',lambda:tmp_path)
    window=ui.MainWindow();window.timer.stop();window.connections.timer.stop()
    try:
        plugin=next(p for p in window.manager.plugins if p.id=='pricing');plugin.enabled=True
        window.snapshot=Snapshot(stash=[dict(name='Chaos Orb',scope='personal',tab='Currency',tab_index=0),dict(name='Vaal Orb',scope='guild',tab='Guild',tab_index=1)])
        window.connections.member='self'
        window.connections.state={'shares':[dict(kind='tabs',owner='friend',owner_name='Friend',key='tab1',data=dict(title='Loot',scope='personal',items=[dict(name='Divine Orb')]))]}
        window.refresh_stash();assert window.stash_table.rowCount()==3 and window.stash_table.columnCount()==4
        sources={('local','personal'):'Personal',('local','guild'):'Guild',('remote','friend'):'Friend'}
        window.set_stash_source(('local','personal'),False,sources)
        assert window.stash_table.rowCount()==2
        assert {window.stash_table.item(i,0).text() for i in range(2)}=={'Vaal Orb','Divine Orb'}
        window.set_stash_tab_visible(('remote','friend','tab1'),False);assert window.stash_table.rowCount()==1
        window.set_stash_tab_visible(('remote','friend','tab1'),True)
        window.set_stash_source(None,True,sources);assert window.stash_table.rowCount()==3
    finally:window.close()


def test_saved_connection_reconnects_automatically(service,tmp_path):
    import time
    from types import SimpleNamespace
    from PySide6.QtWidgets import QApplication
    from exile.connections import Connections
    from exile.model import Snapshot
    client,joined=join(service[0],'Auto reconnect')
    config={'connections':dict(server=service[0],name='Auto reconnect',invite=joined['invite'],token=joined['token'],host_mode='external')}
    fake=SimpleNamespace(config=config,data=tmp_path,snapshot=Snapshot(),economy_league=lambda:'Test',save=lambda:None)
    pane=Connections(fake);pane.timer.stop();pane.link_timer.stop()
    try:
        end=time.monotonic()+5
        while (not pane.client or not pane.state) and time.monotonic()<end:QApplication.processEvents();time.sleep(.01)
        assert pane.client and pane.state['member']==joined['member']
    finally:pane.shutdown();pane.close()
