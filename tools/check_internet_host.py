"""Temporary public HTTPS smoke test, using isolated synthetic data only."""
from pathlib import Path
import json
import queue
import subprocess
import sys
import tempfile
import threading
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from exile.internet_host import prepare_cloudflared,tunnel_url
from exile.sharing import SharingClient
from exile.sharing_server import make_server
from exile.storage import data_root

def main():
    helper=prepare_cloudflared(data_root()/'tools')
    with tempfile.TemporaryDirectory()as temp:
        server=make_server(('127.0.0.1',0),Path(temp)/'synthetic.sqlite')
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        process=subprocess.Popen([helper,'--no-autoupdate','tunnel','--protocol','http2','--url','http://127.0.0.1:'+str(server.server_port)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        lines=queue.Queue()
        def read():
            for line in iter(process.stdout.readline,b''):lines.put(line.decode(errors='replace'))
        threading.Thread(target=read,daemon=True).start()
        log='';end=time.monotonic()+60
        try:
            while time.monotonic()<end:
                try:log=(log+lines.get(timeout=.3))[-40000:]
                except queue.Empty:pass
                address=tunnel_url(log)
                if address and 'Registered tunnel connection'in log:break
                if process.poll()is not None:raise RuntimeError('Tunnel exited: '+log[-2000:])
            else:raise RuntimeError('Tunnel did not connect: '+log[-2000:])
            alice=SharingClient(address)
            Path('.reference/cloudflared-smoke.log').write_text(log,encoding='utf-8')
            # DNS and edge routing can take a few seconds after connection.
            for attempt in range(60):
                try:a=alice.request('POST','groups',dict(name='Alice',group='Synthetic Internet test'));break
                except Exception:
                    if attempt==59:raise
                    time.sleep(1)
            alice.token=a['token'];bob=SharingClient(address)
            b=bob.request('POST','join',dict(name='Bob',invite=a['invite']));bob.token=b['token']
            alice.request('PUT','items/test',dict(title='Test item',league='Test',item=dict(name='Test ring'),text='Synthetic test'))
            state=bob.request('GET','state');assert len(state['members'])==2 and len(state['shares'])==1
            result=dict(ok=True,public_https=True,members=2,shares=1)
            Path('.reference/internet-host-test.json').write_text(json.dumps(result),encoding='utf-8');print(json.dumps(result))
        finally:
            process.terminate();process.wait(timeout=10);server.shutdown();server.server_close();worker.join(timeout=2)

if __name__=='__main__':main()
