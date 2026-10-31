"""Private group UI. Network work stays off the game-reader and UI threads."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
import logging
import html
import json
import re
import os
import secrets
import threading
import time
from PySide6.QtCore import Qt,QTimer,Signal,QProcess
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QPushButton,QComboBox,
    QCheckBox,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QPlainTextEdit,QStackedWidget,QFrame,QTextBrowser,QDialog)
from exile.sharing import SharingClient,clean_item,tab_key

class Connections(QWidget):
    completed=Signal(int,object,object)
    def __init__(self,app):
        super().__init__();self.app=app;self.client=None;self.member='';self.state={};self.closed=False
        self.generation=0;self.busy=False;self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='waymark-sharing')
        self.rendered_shares=None
        self.internet_process=None;self.internet_address='';self.tunnel_log='';self.stopping_internet=False
        self.completed.connect(self.finish);self.subscriptions={};self.sent={};self.local_server=None
        saved=app.config.get('connections',{})
        self.host_mode=saved.get('host_mode','');self.pending_host=False;self.pending_reconnect=False;self.rendered_events=None
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.steps=QStackedWidget();layout.addWidget(self.steps,1)
        setup=QWidget();start=QVBoxLayout(setup);start.setContentsMargins(12,12,12,12)
        start.addWidget(QLabel('Connect with your group'))
        self.name=QLineEdit(saved.get('name',''));self.name.setPlaceholderText('Your display name');self.name.setMaxLength(50);start.addWidget(self.name)
        row=QHBoxLayout();self.add_button(row,'Host',lambda:self.choose_host('internet'));self.add_button(row,'Host (LAN)',lambda:self.choose_host('lan'));self.add_button(row,'Join',self.choose_join);start.addLayout(row)
        self.reconnect_button=QPushButton('Reconnect to saved group');self.reconnect_button.clicked.connect(self.reconnect);self.reconnect_button.setVisible(bool(saved.get('token')));start.addWidget(self.reconnect_button)
        start.addStretch();self.steps.addWidget(setup)
        host_page=QWidget();host_layout=QVBoxLayout(host_page);host_layout.setContentsMargins(12,12,12,12)
        self.host_title=QLabel('Create a group');host_layout.addWidget(self.host_title)
        self.group=QLineEdit();self.group.setPlaceholderText('Group name');self.group.setMaxLength(80);host_layout.addWidget(self.group)
        self.existing_server=QLineEdit();self.existing_server.setPlaceholderText('Existing server address (optional)');host_layout.addWidget(self.existing_server)
        row=QHBoxLayout();self.add_button(row,'Back',lambda:self.steps.setCurrentIndex(0));self.add_button(row,'Create group',self.start_host_group);host_layout.addLayout(row);host_layout.addStretch();self.steps.addWidget(host_page)
        join_page=QWidget();join_layout=QVBoxLayout(join_page);join_layout.setContentsMargins(12,12,12,12)
        join_layout.addWidget(QLabel('Join a group'))
        self.join_code=QLineEdit();self.join_code.setPlaceholderText('Paste your invite code');join_layout.addWidget(self.join_code)
        row=QHBoxLayout();self.add_button(row,'Back',lambda:self.steps.setCurrentIndex(0));self.add_button(row,'Join group',self.join_combined);join_layout.addLayout(row);join_layout.addStretch();self.steps.addWidget(join_page)
        # Retain the separate fields internally for saved sessions and older servers.
        self.server=QLineEdit(saved.get('server','http://127.0.0.1:8765'));self.invite=QLineEdit(saved.get('invite',''))
        connected=QWidget();main=QVBoxLayout(connected);main.setContentsMargins(4,4,4,4)
        top=QHBoxLayout();self.group_heading=QLabel('Group');top.addWidget(self.group_heading,1)
        self.invite_display=QLineEdit();self.invite_display.setReadOnly(True);self.invite_display.setPlaceholderText('Invite unavailable');top.addWidget(self.invite_display,2)
        self.add_button(top,'Copy invite',lambda:self.copy(self.invite_display.text()));main.addLayout(top)
        center=QHBoxLayout();center.setSpacing(0)
        self.chat=QTextBrowser();self.chat.setOpenLinks(False);self.chat.setPlaceholderText('Group messages and activity appear here.')
        self.chat.setStyleSheet('QTextBrowser {background-color:#121211; background-image:none; border:1px solid #5b4a32; padding:8px; color:#ddd1b7;}')
        self.chat.anchorClicked.connect(self.open_chat_item);center.addWidget(self.chat,4)
        actions=QFrame();actions.setStyleSheet('QFrame {background-color:#171613; background-image:none; border-top:1px solid #5b4a32; border-bottom:1px solid #5b4a32;}')
        quick=QVBoxLayout(actions);quick.setContentsMargins(7,8,7,8);quick.addWidget(QLabel('Share item'))
        self.add_button(quick,'Alt+F item',self.share_item);self.add_button(quick,'Copied item',self.share_copied_item);quick.addStretch();center.addWidget(actions)
        members_panel=QFrame();members_panel.setStyleSheet('QFrame {background-color:#1d1b17; background-image:none; border:1px solid #5b4a32;} QLabel {background:transparent; border:0;}')
        member_box=QVBoxLayout(members_panel);member_box.setContentsMargins(10,8,10,8);member_box.addWidget(QLabel('Members'));self.members=QLabel('');self.members.setWordWrap(True);self.members.setAlignment(Qt.AlignmentFlag.AlignTop);member_box.addWidget(self.members,1);center.addWidget(members_panel,1);main.addLayout(center,2)
        row=QHBoxLayout();self.message=QLineEdit();self.message.setPlaceholderText('Write a message…');self.message.setMaxLength(1000);self.message.returnPressed.connect(self.send_message);row.addWidget(self.message,1);self.add_button(row,'Send',self.send_message);main.addLayout(row)
        main.addWidget(QLabel('Sync / share'))
        row=QHBoxLayout();self.personal_share=QCheckBox('Personal stash');self.guild_share=QCheckBox('Guild stash');self.personal_share.setChecked(bool(saved.get('personal_share',False)));self.guild_share.setChecked(bool(saved.get('guild_share',False)));row.addWidget(self.personal_share);row.addWidget(self.guild_share);self.linked_share=QCheckBox('Share linked items');self.linked_share.setChecked(bool(saved.get('linked_share',False)));row.addWidget(self.linked_share);self.linked_share.toggled.connect(self.sharing_changed);row.addStretch();main.addLayout(row)
        note=QLabel('Tabs are shared as PoE loads them. Open each tab in game to include it.');note.setWordWrap(True);main.addWidget(note)
        for checkbox in (self.personal_share,self.guild_share):checkbox.toggled.connect(self.sharing_changed)
        row=QHBoxLayout();self.add_button(row,'Shared items and tabs',self.toggle_shares);self.add_button(row,'Settings and server management',self.toggle_settings);row.addStretch();main.addLayout(row)
        self.shares_panel=QWidget();share_layout=QVBoxLayout(self.shares_panel);share_layout.setContentsMargins(0,0,0,0)
        row=QHBoxLayout();self.search=QLineEdit();self.search.setPlaceholderText('Search shared items and tabs');self.search.textChanged.connect(self.filter_shared);row.addWidget(self.search,1);self.add_button(row,'Withdraw selected item',self.withdraw);share_layout.addLayout(row)
        self.table=QTableWidget(0,5);self.table.setHorizontalHeaderLabels(['Player','Type','Shared data','League','Updated'])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents);self.table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self.details);share_layout.addWidget(self.table,1)
        self.detail=QPlainTextEdit();self.detail.setReadOnly(True);self.detail.setMaximumHeight(110);share_layout.addWidget(self.detail);main.addWidget(self.shares_panel,2);self.shares_panel.hide()
        self.settings_panel=QWidget();settings=QVBoxLayout(self.settings_panel);settings.setContentsMargins(0,0,0,0)
        self.host_info=QLabel('');self.host_info.setWordWrap(True);settings.addWidget(self.host_info)
        row=QHBoxLayout();self.add_button(row,'Disconnect',self.disconnect);self.add_button(row,'Leave group',self.leave);self.add_button(row,'Stop hosting',self.stop_hosting);row.addStretch();settings.addLayout(row);main.addWidget(self.settings_panel);self.settings_panel.hide()
        self.steps.addWidget(connected)
        self.status=QLabel('Enter your display name to get started.');self.status.setWordWrap(True);layout.addWidget(self.status)
        # Compatibility controls for existing integrations; bulk sharing supersedes them.
        self.tabs=QComboBox();self.tabs.hide();self.auto=QCheckBox();self.auto.hide()
        for label in (self.status,self.members,self.host_info,self.group_heading):label.setTextFormat(Qt.TextFormat.PlainText)
        self.timer=QTimer(self);self.timer.timeout.connect(self.poll);self.timer.start(4000)
        from exile.hover_tracker import HoverTracker
        self.hover_tracker=HoverTracker()
        if saved.get('token'):
            QTimer.singleShot(1000,self.reconnect)
        self.link_mouse_down=False;self.pending_link=None;self.link_timer=QTimer(self);self.link_timer.timeout.connect(self.check_link_click);self.link_timer.start(5)

    def choose_host(self,mode):
        if not self.name.text().strip():self.status.setText('Enter your display name first.');return
        self.host_mode=mode;self.existing_server.setVisible(mode=='internet');self.host_title.setText('Create a group · '+('Internet' if mode=='internet' else 'LAN'))
        self.steps.setCurrentIndex(1);self.status.setText('Choose a group name.')

    def choose_join(self):
        if not self.name.text().strip():self.status.setText('Enter your display name first.');return
        self.host_mode='';self.steps.setCurrentIndex(2);self.status.setText('Paste the invite from your host.')

    def start_host_group(self):
        if not self.group.text().strip():self.status.setText('Enter a group name.');return
        if self.host_mode=='internet' and self.existing_server.text().strip():
            try:SharingClient(self.existing_server.text())
            except ValueError as exc:self.status.setText(str(exc));return
            self.server.setText(self.existing_server.text().strip());self.host_mode='external';self.connect_group(True)
        elif self.host_mode=='internet':
            from exile.firebase_auth import DATABASE_URL
            self.server.setText(DATABASE_URL);self.host_mode='firebase';self.connect_group(True)
        elif self.host():self.connect_group(True)

    def join_combined(self):
        combined=self.join_code.text().strip()
        try:
            from exile.firebase_auth import DATABASE_URL
            if re.fullmatch(r'[a-f0-9]{32}',combined):address,code=DATABASE_URL,combined
            # Older invitations used 32 URL-safe characters, which can include hyphens.
            elif len(combined)>33 and combined[-33]=='-':address,code=combined[:-33],combined[-32:]
            else:address,code=combined.rsplit('-',1)
            if not code or len(code)>128:raise ValueError()
            SharingClient(address)
        except ValueError:self.status.setText('Paste the complete server address and invite code.');return
        self.server.setText(address);self.invite.setText(code);self.connect_group(False)

    def display_address(self):
        if self.host_mode=='internet' and self.internet_address:return self.internet_address
        if self.host_mode=='lan' and self.local_server:
            import socket
            addresses=[a for a in socket.gethostbyname_ex(socket.gethostname())[2] if not a.startswith('127.')]
            if addresses:return 'http://'+addresses[0]+':8765'
        return self.server.text().strip().rstrip('/')

    def update_invite_display(self):
        address=self.display_address();code=self.invite.text().strip()
        from exile.firebase_auth import DATABASE_URL
        self.invite_display.setText((code if address==DATABASE_URL else address+'-'+code) if address and code else '')

    def toggle_shares(self):self.shares_panel.setVisible(not self.shares_panel.isVisible())
    def toggle_settings(self):self.settings_panel.setVisible(not self.settings_panel.isVisible())

    def sharing_changed(self):
        if not self.linked_share.isChecked():self.pending_link=None
        self.store();self.poll()

    def send_message(self):
        if not self.client:self.status.setText('Connect to a group first.');return
        text=self.message.text().strip()
        if not text:return
        client=self.client
        def sent(_):
            if self.message.text().strip()==text:self.message.clear()
            self.poll()
        self.run(lambda:client.request('POST','messages',dict(text=text)),sent)

    def stop_hosting(self):
        self.stop_internet()
        if self.local_server:
            server=self.local_server;self.local_server=None
            def stop():server.shutdown();server.server_close()
            threading.Thread(target=stop,daemon=True).start()
        self.disconnect();self.status.setText('Hosting stopped.')

    def add_button(self,row,title,action):
        b=QPushButton(title);b.clicked.connect(action);row.addWidget(b);return b

    def copy(self,text):
        from PySide6.QtWidgets import QApplication
        if text:QApplication.clipboard().setText(text)

    def store(self,token=None):
        saved=dict(self.app.config.get('connections',{}))
        saved.update(server=self.server.text().strip(),name=self.name.text().strip(),invite=self.invite.text(),host_mode=self.host_mode,personal_share=self.personal_share.isChecked(),guild_share=self.guild_share.isChecked(),linked_share=self.linked_share.isChecked())
        if token is not None:saved['token']=token
        self.app.config['connections']=saved;self.app.save()

    def run(self,operation,callback):
        if self.closed:return
        if self.busy:self.status.setText('Finishing the current request; try again in a moment.');return
        self.busy=True;generation=self.generation
        def work():
            try:value=(True,operation())
            except Exception as exc:value=(False,str(exc))
            if not self.closed:self.completed.emit(generation,callback,value)
        self.pool.submit(work)

    def finish(self,generation,callback,value):
        if self.closed or generation!=self.generation:return
        self.busy=False
        if value[0]:
            try:callback(value[1])
            except (KeyError,TypeError,ValueError):self.status.setText('The server returned an incompatible response.')
        else:self.status.setText('Connection: '+str(value[1]))

    def host(self,bind='0.0.0.0'):
        if self.local_server:return True
        try:
            from exile.sharing_server import make_server
            self.local_server=make_server((bind,8765),self.app.data/'groups.sqlite')
            threading.Thread(target=self.local_server.serve_forever,daemon=True).start()
            self.server.setText('http://127.0.0.1:8765')
            import socket
            addresses=[a for a in socket.gethostbyname_ex(socket.gethostname())[2]if not a.startswith('127.')]
            self.host_info.setText('Friends connect to: '+(' / '.join('http://'+a+':8765'for a in addresses)or'this computer’s LAN address on port 8765'))
            self.status.setText('Hosting on port 8765. Friends on your network use this computer’s LAN address. Hosting stops when Waymark closes.')
            return True
        except OSError as exc:self.status.setText('Could not start server: '+str(exc));return False

    def host_internet(self):
        if self.internet_process and self.internet_process.state()!=QProcess.ProcessState.NotRunning:return
        if self.busy:self.status.setText('Wait for the current connection request, then try again.');return
        if not self.host('127.0.0.1'):return
        self.status.setText('Preparing Cloudflare Internet hosting. The first start downloads and verifies its portable helper.')
        from exile.internet_host import prepare_cloudflared
        def ready(executable):
            process=QProcess(self);self.internet_process=process;self.internet_address='';self.tunnel_log='';self.stopping_internet=False
            process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
            process.readyReadStandardOutput.connect(self.read_tunnel)
            process.finished.connect(self.tunnel_finished)
            process.errorOccurred.connect(lambda error:self.status.setText('Internet helper could not run.')if error==QProcess.ProcessError.FailedToStart else None)
            process.setProgram(executable)
            process.setArguments(['--no-autoupdate','tunnel','--protocol','http2','--url','http://127.0.0.1:8765'])
            process.start();self.status.setText('Creating your temporary HTTPS address…')
        self.run(lambda:prepare_cloudflared(self.app.data/'tools'),ready)

    def read_tunnel(self):
        from exile.internet_host import tunnel_url
        self.tunnel_log=(self.tunnel_log+bytes(self.internet_process.readAllStandardOutput()).decode(errors='replace'))[-40000:]
        address=tunnel_url(self.tunnel_log)
        if address and 'Registered tunnel connection'in self.tunnel_log and not self.internet_address:
            self.internet_address=address
            from exile.storage import write_json
            import os
            write_json(self.app.data/'internet-host.json',dict(address=address,pid=os.getpid()))
            self.host_info.setText('Internet address: '+address+' · temporary; changes when hosting restarts')
            self.status.setText('Internet hosting is ready.')
            self.update_invite_display()
            if self.pending_host:
                self.pending_host=False;self.connect_group(True)
            elif self.pending_reconnect:
                self.pending_reconnect=False;self.reconnect()

    def tunnel_finished(self,code,status):
        self.internet_address='';self.host_info.setText('Internet hosting stopped.')
        from exile.storage import write_json
        write_json(self.app.data/'internet-host.json',{})
        if not self.closed:self.status.setText('Internet hosting stopped.'if self.stopping_internet else'Internet connection ended. Start hosting again to get a new address.')

    def stop_internet(self):
        self.stopping_internet=True;self.pending_host=False;self.pending_reconnect=False
        if self.internet_process and self.internet_process.state()!=QProcess.ProcessState.NotRunning:self.internet_process.kill()
        self.internet_address=''

    def connect_group(self,create):
        if self.busy:return
        if self.client:self.status.setText('Leave the current group before creating or joining another.');return
        from exile.firebase_auth import DATABASE_URL
        from exile.firebase_sharing import FirebaseClient
        factory=FirebaseClient if self.server.text().strip().rstrip('/')==DATABASE_URL else SharingClient
        try:client=factory(self.server.text())
        except ValueError as exc:self.status.setText(str(exc));return
        body=dict(name=self.name.text(),group=self.group.text(),invite=self.invite.text())
        def joined(value):
            self.client=factory(client.url,value['token']);self.member=value['member']
            if value.get('invite'):self.invite.setText(value['invite'])
            self.steps.setCurrentIndex(3);self.update_invite_display();self.store(value['token']);self.poll()
        self.run(lambda:client.request('POST','groups'if create else'join',body),joined)

    def reconnect(self):
        if self.closed or self.client:return
        saved=self.app.config.get('connections',{});token=saved.get('token')
        if token and self.host_mode in ('lan','internet') and not self.local_server:
            if self.host_mode=='internet':
                self.pending_reconnect=True;self.host_internet();return
            if not self.host():return
        if not token:self.status.setText('Create or join a group first.');return
        if self.server.text().strip().rstrip('/')!=saved.get('server','').rstrip('/'):
            self.status.setText('The saved session belongs to a different server. Use its address to reconnect, or create/join on this server.');return
        from exile.firebase_auth import DATABASE_URL
        from exile.firebase_sharing import FirebaseClient
        factory=FirebaseClient if self.server.text().strip().rstrip('/')==DATABASE_URL else SharingClient
        try:client=factory(self.server.text(),token)
        except (ValueError,KeyError,TypeError):self.status.setText('The saved session is invalid. Join again.');return
        def connected(value):
            self.client=client;self.steps.setCurrentIndex(3);self.update_invite_display();self.apply_state(value)
            if callable(getattr(client,'session',None)):self.store(client.session())
        def resume():
            client.request('POST','presence',{})
            return client.request('GET','state')
        self.run(resume,connected)

    def leave(self):
        if not self.client:return
        client=self.client
        def left(value):
            self.pending_link=None;self.client=None;self.member='';self.state={};self.subscriptions={};self.sent={};self.auto.setChecked(False)
            self.server.setEnabled(True);self.name.setEnabled(True);self.invite.setReadOnly(False)
            self.store('');self.invite.clear();self.table.setRowCount(0);self.detail.clear();self.members.clear()
            self.steps.setCurrentIndex(0);self.reconnect_button.setVisible(False)
            self.personal_share.setChecked(False);self.guild_share.setChecked(False)
            self.status.setText('Left the group. Your shared items and tabs were withdrawn.')
        self.run(lambda:client.request('DELETE','session'),left)

    def disconnect(self):
        self.pending_link=None;self.generation+=1;self.busy=False;self.client=None;self.member='';self.state={};self.subscriptions={};self.sent={}
        self.auto.setChecked(False);self.server.setEnabled(True);self.name.setEnabled(True);self.invite.setReadOnly(False)
        self.rendered_events=None;self.rendered_shares=None;self.chat.clear()
        self.table.setRowCount(0);self.detail.clear();self.members.clear()
        self.steps.setCurrentIndex(0);self.reconnect_button.setVisible(bool(self.app.config.get('connections',{}).get('token')))
        self.status.setText('Disconnected. Shared snapshots remain on the server until you reconnect and withdraw them.')

    def loaded_tabs(self):
        grouped={}
        for tab in getattr(self.app.snapshot,'stash_tabs',[]):
            if tab.get('loaded')and tab.get('scope')in ('personal','guild'):
                grouped[(tab['scope'],tab['index'],str(tab['name']))]=[]
        for item in self.app.snapshot.stash:
            if item.get('scope')not in ('personal','guild')or item.get('tab_index')is None:continue
            key=(item['scope'],item['tab_index'],str(item.get('tab','Tab')))
            grouped.setdefault(key,[]).append(item)
        return grouped

    def poll(self):
        current=self.tabs.currentData();loaded=self.loaded_tabs()
        self.tabs.blockSignals(True);self.tabs.clear()
        for key,items in loaded.items():self.tabs.addItem(f'{key[0].title()} · {key[2]} · {len(items)} loaded items',key)
        index=self.tabs.findData(current)
        if index>=0:self.tabs.setCurrentIndex(index)
        self.tabs.blockSignals(False)
        if not self.client or self.busy:return
        client=self.client;updates=[];withdrawals=[]
        scopes={'personal':self.personal_share.isChecked(),'guild':self.guild_share.isChecked()}
        if self.app.snapshot.source=='live' and self.app.snapshot.fresh() and not self.app.snapshot.loading:
            for source,items in loaded.items():
                if not scopes[source[0]]:continue
                key=tab_key(*source);body=self.tab_payload(source,items)
                signature=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest()
                if self.sent.get(key)!=signature and len(updates)<4:updates.append((key,body,signature))
        for share in self.state.get('shares',[]):
            if share.get('owner')==self.member and share.get('kind')=='tabs' and not scopes.get(share.get('data',{}).get('scope'),False):
                withdrawals.append(share['key'])
        def fetch():
            for key in withdrawals:client.request('DELETE','tabs/'+key)
            for key,body,signature in updates:client.request('PUT','tabs/'+key,body)
            return client.request('GET','state')
        def done(value):
            for key in withdrawals:self.sent.pop(key,None)
            for key,body,signature in updates:self.sent[key]=signature
            self.apply_state(value)
            if callable(getattr(client,'session',None)):
                token=client.session()
                if token!=self.app.config.get('connections',{}).get('token'):self.store(token)
        self.run(fetch,done)

    def tab_payload(self,source,items):
        return dict(title=source[2],scope=source[0],league=self.app.economy_league(),items=[clean_item(i)for i in items])

    def share_tab(self):
        if not self.client:self.status.setText('Connect to a group first.');return
        source=self.tabs.currentData();loaded=self.loaded_tabs()
        if source not in loaded:self.status.setText('Open a stash tab in PoE to load its items first.');return
        if self.app.snapshot.source!='live' or not self.app.snapshot.fresh()or self.app.snapshot.loading:
            self.status.setText('Wait for fresh in-game stash data before publishing.');return
        body=self.tab_payload(source,loaded[source]);key=tab_key(*source);client=self.client
        def done(value):self.subscriptions[key]=source;self.sent.pop(key,None);self.poll()
        self.run(lambda:client.request('PUT','tabs/'+key,body),done)

    def share_item(self):
        if not self.client:self.status.setText('Connect to a group first.');return
        context=getattr(self.app,'latest_shared_item',None)
        if not context:self.status.setText('Use Alt+F on an item first.');return
        client=self.client;key=secrets.token_hex(12)
        body=dict(title=context['name'],league=context['league'],item=context['item'],text=context['text'])
        self.run(lambda:client.request('PUT','items/'+key,body),lambda _:self.poll())

    def check_link_click(self):
        from PySide6.QtGui import QCursor
        snapshot=self.app.snapshot;window=getattr(getattr(self.app,'backend',None),'window',None)
        preserve=False
        if os.name=='nt':
            import ctypes
            keys=ctypes.windll.user32.GetAsyncKeyState
            preserve=bool(keys(0x11)&0x8000 or keys(0x12)&0x8000)
        self.hover_tracker.sample(QCursor.pos(),time.monotonic(),snapshot,bool(window and window.foreground),preserve)
        if self.pending_link and not self.busy and self.client and self.linked_share.isChecked():
            client=self.client;body=self.pending_link;self.pending_link=None;key=secrets.token_hex(12)
            self.run(lambda:client.request('PUT','items/'+key,body),lambda _:self.poll())
        if os.name!='nt':return
        import ctypes
        keys=ctypes.windll.user32.GetAsyncKeyState
        state=keys(0x01)
        down=bool(state&0x8000)
        rising=(down and not self.link_mouse_down) or (bool(state&1) and not self.link_mouse_down);self.link_mouse_down=down
        ctrl=bool(keys(0x11)&0x8000);alt=bool(keys(0x12)&0x8000)
        if rising and (ctrl or alt) and self.client and self.linked_share.isChecked() and getattr(getattr(self.app,'backend',None),'window',None) and self.app.backend.window.foreground:
            logging.info('LINK_DIAG click ctrl=%s alt=%s enabled=%s connected=%s',ctrl,alt,self.linked_share.isChecked(),bool(self.client))
        if not rising or not self.client or not self.linked_share.isChecked() or not(ctrl and alt):return
        position=QCursor.pos();started=time.monotonic()
        cached=self.hover_tracker.current(position,started,self.app.snapshot)
        self.capture_link_item(position,started,retries=12,cached=cached)

    def capture_link_item(self,position,started,retries,cached=None):
        from PySide6.QtGui import QCursor
        if not self.client or not self.linked_share.isChecked() or (QCursor.pos()-position).manhattanLength()>8:return
        snapshot=self.app.snapshot;window=getattr(getattr(self.app,'backend',None),'window',None)
        if not window or not window.foreground or snapshot.source!='live' or not snapshot.fresh() or snapshot.loading:
            logging.info('LINK_DIAG rejected focus=%s source=%s fresh=%s loading=%s',bool(window and window.foreground),snapshot.source,snapshot.fresh(),snapshot.loading);return
        item=cached or snapshot.hovered_item
        if item and not cached and (item.get('hover_captured_at',snapshot.captured_at)<started or time.monotonic()-item.get('hover_captured_at',snapshot.captured_at)>.5):item=None
        if not item or not item.get('tooltip_rows'):
            if retries and time.monotonic()-started<1:QTimer.singleShot(60,lambda:self.capture_link_item(position,started,retries-1))
            elif not retries:
                logging.info('LINK_DIAG no tooltip after retry snapshot_age_ms=%.0f',1000*(time.monotonic()-snapshot.captured_at));self.status.setText('No item tooltip was available for that click.')
            return
        logging.info('LINK_DIAG captured tooltip rows=%d age_ms=%.0f',len(item['tooltip_rows']),1000*(time.monotonic()-item.get('hover_captured_at',snapshot.captured_at)))
        name=str(item.get('name') or item.get('base') or 'Item')
        rarity={0:'Normal',1:'Magic',2:'Rare',3:'Unique'}.get(item.get('rarity'),'Unknown')
        rows=[str(row) for row in item['tooltip_rows'] if row]
        text='Rarity: '+rarity+'\n'+name+'\n'+'\n--------\n'.join(rows)
        body=dict(title=name,league=self.app.economy_league(),item=clean_item(item),text=text[:30000])
        if self.busy:self.pending_link=body;return
        client=self.client;key=secrets.token_hex(12)
        self.run(lambda:client.request('PUT','items/'+key,body),lambda _:self.poll())

    def share_copied_item(self):
        if not self.client:self.status.setText('Connect to a group first.');return
        from PySide6.QtWidgets import QApplication
        from dataclasses import asdict
        from exile.items import parse_item
        text=QApplication.clipboard().text()
        if len(text)>30000:self.status.setText('Copied item text is too long.');return
        try:item=parse_item(text)
        except ValueError as exc:self.status.setText(str(exc));return
        client=self.client;key=secrets.token_hex(12)
        body=dict(title=item.name,league=self.app.economy_league(),item=clean_item(asdict(item)),text=text)
        self.run(lambda:client.request('PUT','items/'+key,body),lambda _:self.poll())

    def selected_share(self):
        rows=self.table.selectionModel().selectedRows()
        return self.table.item(rows[0].row(),0).data(Qt.ItemDataRole.UserRole)if rows else None

    def withdraw(self):
        share=self.selected_share()
        if not self.client or not share:return
        if share['owner']!=self.member:self.status.setText('Only the player who shared this can withdraw it.');return
        client=self.client
        def done(value):self.subscriptions.pop(share['key'],None);self.sent.pop(share['key'],None);self.poll()
        self.run(lambda:client.request('DELETE',share['kind']+'/'+share['key']),done)

    def apply_state(self,value):
        self.server.setEnabled(False);self.name.setEnabled(False);self.invite.setReadOnly(True)
        self.state=value;self.member=value['member'];selected=self.selected_share();selected_key=(selected['owner'],selected['kind'],selected['key'])if selected else None
        self.status.setText('Connected · '+value['group']['name']);self.group_heading.setText(value['group']['name']);self.update_invite_display()
        self.members.setText('\n'.join(m['name']+(' (offline)'if time.time()-m['seen']>20 else'')for m in value['members']))
        events=value.get('events',[])
        render_signature=(events,value.get('shares',[]))
        if render_signature!=self.rendered_events:
            self.rendered_events=render_signature
            self.chat_items={}
            lines=[]
            for e in events:
                text=e['text'];rendered=html.escape(text)
                if e.get('kind')=='system':
                    matches=[share for share in value.get('shares',[]) if share.get('kind')=='items' and text==share['owner_name']+' shared '+share['data']['title']+'.']
                    if matches:
                        share=min(matches,key=lambda item:abs(item['updated']-e['created']))
                        if abs(share['updated']-e['created'])<15:
                            key=str(len(self.chat_items));self.chat_items[key]=share
                            rendered=html.escape(share['owner_name'])+' shared <a href="item:'+key+'" style="color:#dfbd7d;">'+html.escape(share['data']['title'])+'</a>.'
                prefix=datetime.fromtimestamp(e['created']).strftime('%H:%M')+'  '+(e['author']+': ' if e['kind']=='message' else '')
                lines.append('<p style="margin:0 0 7px 0;">'+html.escape(prefix)+rendered+'</p>')
            self.chat.setHtml(''.join(lines))
            self.chat.verticalScrollBar().setValue(self.chat.verticalScrollBar().maximum())
        if hasattr(self.app,'pages')and self.app.pages.currentWidget()is not self:return
        if self.rendered_shares==value['shares']:return
        self.rendered_shares=value['shares']
        self.table.blockSignals(True);self.table.setRowCount(len(value['shares']))
        for row,share in enumerate(value['shares']):
            data=share['data'];stamp=datetime.fromtimestamp(share['updated']).strftime('%b %d %H:%M:%S')
            for col,text in enumerate((share['owner_name'],'Tab'if share['kind']=='tabs'else'Item',data['title'],data['league'],stamp)):
                cell=QTableWidgetItem(text);cell.setData(Qt.ItemDataRole.UserRole,share);self.table.setItem(row,col,cell)
            if (share['owner'],share['kind'],share['key'])==selected_key:self.table.selectRow(row)
        self.table.blockSignals(False);self.details()
        self.filter_shared()

    def open_chat_item(self,url):
        if url.scheme()!='item':return
        share=getattr(self,'chat_items',{}).get(url.path())
        if not share:return
        dialog=QDialog(self);dialog.setWindowTitle(share['data'].get('title','Shared item'));dialog.resize(440,520)
        layout=QVBoxLayout(dialog);detail=QPlainTextEdit();detail.setReadOnly(True);detail.setPlainText(share['data'].get('text',''));layout.addWidget(detail)
        dialog.exec()

    def showEvent(self,event):
        super().showEvent(event)
        if self.state:QTimer.singleShot(0,lambda:self.apply_state(self.state)if self.state and not self.closed else None)

    def filter_shared(self):
        query=self.search.text().casefold().strip()
        for row in range(self.table.rowCount()):
            share=self.table.item(row,0).data(Qt.ItemDataRole.UserRole)
            self.table.setRowHidden(row,bool(query)and query not in (share['owner_name']+' '+json.dumps(share['data'],ensure_ascii=False)).casefold())

    def details(self):
        share=self.selected_share()
        if not share:self.detail.clear();return
        data=share['data']
        if share['kind']=='items':self.detail.setPlainText(data.get('text',''));return
        lines=['Loaded items only · '+data['title']]
        for item in data['items']:
            lines.append(f"{item.get('quantity',1)} × {item.get('name',item.get('base','Item'))}  {item.get('price_label','')}")
            lines.extend('    '+str(mod)for mod in item.get('mods',[]))
        self.detail.setPlainText('\n'.join(lines))

    def shutdown(self):
        self.closed=True;self.timer.stop();self.link_timer.stop();self.pool.shutdown(wait=False,cancel_futures=True)
        self.stop_internet()
        if self.internet_process:self.internet_process.waitForFinished(1500)
        if self.local_server:
            server=self.local_server
            def stop():server.shutdown();server.server_close()
            threading.Thread(target=stop,daemon=True).start()
