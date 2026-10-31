"""Exercise the packaged server with local clients; report no credentials."""
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from exile.sharing import SharingClient

def main():
    executable=Path(sys.argv[1]).resolve();report=Path(sys.argv[2]).resolve()
    with tempfile.TemporaryDirectory()as temp:
        with socket.socket()as listener:listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
        process=subprocess.Popen([str(executable),'--sharing-server','--bind','127.0.0.1','--port',str(port),'--database',str(Path(temp)/'test.sqlite')],
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            client=SharingClient('http://127.0.0.1:'+str(port));end=time.monotonic()+20
            while True:
                try:a=client.request('POST','groups',dict(name='Alice',group='Packaged test'));break
                except Exception:
                    if process.poll()is not None or time.monotonic()>end:raise
                    time.sleep(.1)
            client.token=a['token'];other=SharingClient(client.url)
            b=other.request('POST','join',dict(name='Bob',invite=a['invite']));other.token=b['token']
            client.request('PUT','tabs/tab',dict(title='Test tab',league='Test',items=[dict(name='Vaal Orb',quantity=10)]))
            other.request('PUT','items/item',dict(title='Test item',league='Test',item=dict(name='Ring'),text='Example'))
            state=client.request('GET','state')
            assert len(state['members'])==2 and len(state['shares'])==2
            report.write_text(json.dumps(dict(ok=True,version=state['version'],members=2,shares=2)),encoding='utf-8')
        finally:
            process.terminate();process.wait(timeout=10)

if __name__=='__main__':main()
