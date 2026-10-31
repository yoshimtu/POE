import hashlib
import io
import json
import pytest
from exile.internet_host import prepare_cloudflared,tunnel_url

def test_helper_download_is_verified_and_cached(tmp_path,monkeypatch):
    import exile.internet_host as hosting
    content=b'synthetic-executable-not-run';expected=hashlib.sha256(content).hexdigest();downloads=[]
    def fetch(request,timeout):
        if 'api.github.com'in request.full_url:
            return io.BytesIO(json.dumps(dict(tag_name='test',assets=[dict(name='cloudflared-windows-amd64.exe',digest='sha256:'+expected,
                browser_download_url='https://github.com/cloudflare/cloudflared/releases/download/test/helper.exe')])).encode())
        downloads.append(request.full_url);return io.BytesIO(content)
    monkeypatch.setattr(hosting,'urlopen',fetch)
    first=prepare_cloudflared(tmp_path);second=prepare_cloudflared(tmp_path)
    assert first==second and len(downloads)==1
    from pathlib import Path
    Path(first).write_bytes(b'tampered')
    assert prepare_cloudflared(tmp_path)==first and Path(first).read_bytes()==content

def test_helper_rejects_checksum_mismatch(tmp_path,monkeypatch):
    import exile.internet_host as hosting
    def fetch(request,timeout):
        if 'api.github.com'in request.full_url:
            return io.BytesIO(json.dumps(dict(tag_name='test',assets=[dict(name='cloudflared-windows-amd64.exe',digest='sha256:'+'a'*64,
                browser_download_url='https://github.com/cloudflare/cloudflared/releases/download/test/helper.exe')])).encode())
        return io.BytesIO(b'incorrect')
    monkeypatch.setattr(hosting,'urlopen',fetch)
    with pytest.raises(ValueError,match='verification failed'):prepare_cloudflared(tmp_path)
    assert not list(tmp_path.glob('*.exe'))and not list(tmp_path.glob('*.download'))

def test_tunnel_link_and_ready_ui(tmp_path,monkeypatch):
    import exile.app as ui
    monkeypatch.setattr(ui,'data_root',lambda:tmp_path)
    w=ui.MainWindow();w.timer.stop();pane=w.connections
    class Process:
        def readAllStandardOutput(self):return b'Your tunnel: https://four-word-test.trycloudflare.com\nRegistered tunnel connection\n'
    try:
        assert tunnel_url('https://example.com')==''
        pane.internet_process=Process();pane.read_tunnel()
        assert pane.internet_address=='https://four-word-test.trycloudflare.com'
        assert 'Internet address:'in pane.host_info.text()
        pane.tunnel_finished(0,None);assert not pane.internet_address
    finally:pane.internet_process=None;w.close()

def test_tunnel_dns_fallback_caches_only_public_addresses(monkeypatch):
    import exile.sharing as sharing
    sharing._TUNNEL_DNS.clear();requests=[]
    def fetch(request,timeout):
        requests.append(request.full_url)
        return io.BytesIO(json.dumps(dict(Answer=[]if len(requests)==1 else[dict(type=1,data='104.16.230.132')])).encode())
    monkeypatch.setattr(sharing,'urlopen',fetch)
    assert sharing.tunnel_addresses('unit-test.trycloudflare.com')==['104.16.230.132']
    assert sharing.tunnel_addresses('unit-test.trycloudflare.com')==['104.16.230.132']and len(requests)==2
    sharing._TUNNEL_DNS.clear()
    monkeypatch.setattr(sharing,'urlopen',lambda *a,**k:io.BytesIO(json.dumps(dict(Answer=[dict(type=1,data='127.0.0.1')])).encode()))
    with pytest.raises(ValueError):sharing.tunnel_addresses('unit-test.trycloudflare.com')

def test_tunnel_fallback_keeps_tls_hostname_and_does_not_affect_other_hosts(monkeypatch):
    import socket,ssl
    import exile.sharing as sharing
    seen=[]
    def connect(self):
        seen.append((self.host,self._context.check_hostname,self._context.verify_mode))
        if len(seen)==1:raise socket.gaierror('synthetic DNS failure')
        self._create_connection((self.host,443),5)
    monkeypatch.setattr(sharing.HTTPSConnection,'connect',connect)
    monkeypatch.setattr(sharing,'tunnel_addresses',lambda host:['104.16.230.132'])
    endpoints=[];monkeypatch.setattr(socket,'create_connection',lambda address,*args:endpoints.append(address))
    sharing.TunnelConnection('unit-test.trycloudflare.com').connect()
    assert endpoints==[('104.16.230.132',443)]
    assert all(row==('unit-test.trycloudflare.com',True,ssl.CERT_REQUIRED)for row in seen)
    seen.clear()
    with pytest.raises(socket.gaierror):sharing.TunnelConnection('example.com').connect()
