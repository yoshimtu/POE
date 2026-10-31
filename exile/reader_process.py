"""Isolated scene discovery with latest-only IPC and stable terrain identities."""
from concurrent.futures import ThreadPoolExecutor
from copy import copy
import logging
import multiprocessing
import threading
import time
from exile.model import Snapshot

TERRAIN=('grid','terrain_heights','walkable_regions','landmarks')

def pack_snapshot(snapshot,previous):
    result=copy(snapshot)
    identity=tuple(id(getattr(snapshot,k,None))for k in TERRAIN)
    payload={k:getattr(snapshot,k,None)for index,k in enumerate(TERRAIN)if previous is None or identity[index]!=previous[index]}
    if not payload:payload=None
    for key in TERRAIN:
        if hasattr(result,key):setattr(result,key,None)
    return result,identity,payload

def discovery_worker(connection,profile_dir,install):
    from pathlib import Path
    from exile.backend import Backend
    backend=Backend(Path(profile_dir),Path(install));previous=None
    try:
        while True:
            command=connection.recv()
            if command is None:return
            generation,items,*options=command;backend.item_prices_enabled=items;backend.item_link_enabled=bool(options and options[0]);backend.item_assessment_archetype=options[1] if len(options)>1 else 'General';backend.inventory_assessment_enabled=bool(options[2]) if len(options)>2 else False
            started=time.monotonic();snapshot=backend.poll()
            packed,identity,terrain=pack_snapshot(snapshot,previous);previous=identity
            connection.send((generation,packed,identity,terrain,backend.status,(time.monotonic()-started)*1000))
    except (EOFError,BrokenPipeError,OSError):pass
    finally:connection.close()

class ProcessLiveReader:
    def __init__(self,worker=discovery_worker):
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='discovery-ipc')
        self.lock=threading.Lock();self.stopped=threading.Event();self.future=None;self.backend=None
        self.latest=Snapshot();self.generation=0
        self.worker=worker;self.worker_pid=None

    def clear(self):
        with self.lock:self.generation+=1;self.latest=Snapshot()

    def _run(self,owner):
        context=multiprocessing.get_context('spawn');parent,child=context.Pipe()
        process=context.Process(target=self.worker,args=(child,str(owner.profile_dir),str(owner.install)),daemon=True)
        process.start();self.worker_pid=process.pid;child.close();terrain={};samples=[];at=time.monotonic()
        try:
            while not self.stopped.is_set()and owner is self.backend:
                with self.lock:generation=self.generation
                parent.send((generation,owner.item_prices_enabled,getattr(owner,'item_link_enabled',False),getattr(owner,'item_assessment_archetype','General'),getattr(owner,'inventory_assessment_enabled',False)))
                while not parent.poll(.02):
                    if self.stopped.is_set()or owner is not self.backend or not process.is_alive():return
                received,snapshot,identity,updated,status,cost=parent.recv()
                if updated is not None:terrain.update(updated)
                for key,value in terrain.items():setattr(snapshot,key,value)
                # Child-local id() values are stable tokens; parent arrays are
                # sent only on change and reused across all subsequent frames.
                samples.append(cost)
                if time.monotonic()-at>10:
                    ordered=sorted(samples);logging.info('Isolated discovery: p50=%.1f p95=%.1f max=%.1f ms',ordered[len(ordered)//2],ordered[int((len(ordered)-1)*.95)],max(ordered));samples=[];at=time.monotonic()
                with self.lock:
                    if owner is self.backend and received==self.generation:
                        if snapshot.source!='disconnected'or not self.latest.fresh():self.latest=snapshot
                        owner.status=status
                self.stopped.wait(.002)
        except (EOFError,BrokenPipeError,OSError):logging.exception('Discovery process stopped unexpectedly')
        finally:
            try:parent.send(None)
            except (EOFError,BrokenPipeError,OSError):pass
            parent.close();process.join(.3)
            if process.is_alive():process.terminate();process.join(1)

    def poll(self,backend):
        from exile.platform import game_window
        backend.window=game_window()
        if backend is not self.backend:
            with self.lock:self.backend=backend;self.generation+=1;self.latest=Snapshot()
        if self.future is None or self.future.done():self.future=self.pool.submit(self._run,backend)
        with self.lock:latest=self.latest
        # Discovery may take longer than a visual frame. This does not make
        # old metadata fresh: only an independently validated pose can render it.
        return latest if 0<=time.monotonic()-latest.captured_at<=2 else Snapshot()

    def close(self):
        self.stopped.set();self.clear();self.pool.shutdown(wait=False,cancel_futures=True)

def synthetic_worker(connection,*unused):
    grid=[[1]*32 for _ in range(32)];previous=None
    try:
        while True:
            command=connection.recv()
            if command is None:return
            generation=command[0];start=time.monotonic()
            # Deliberately GIL-bound discovery work, representative of the
            # failure case. It must not stall the parent's event loop.
            while time.monotonic()-start<.35:sum(range(200))
            snapshot=Snapshot(source='live',in_game=True,loading=False,captured_at=time.monotonic(),grid=grid)
            packed,key,terrain=pack_snapshot(snapshot,previous);previous=key
            connection.send((generation,packed,key,terrain,'Synthetic',350.))
    except (EOFError,BrokenPipeError,OSError):pass
    finally:connection.close()

def check_worker(destination):
    import os,json
    from pathlib import Path
    from types import SimpleNamespace
    from PySide6.QtCore import QCoreApplication,QTimer
    app=QCoreApplication([]);reader=ProcessLiveReader(synthetic_worker)
    backend=SimpleNamespace(profile_dir=Path('.'),install=Path('.'),item_prices_enabled=False)
    samples=[];frames=set();identities=set();started=time.monotonic();last=started
    def tick():
        nonlocal last
        now=time.monotonic();snapshot=reader.poll(backend)
        if len(frames)>=1:samples.append((now-last)*1000)
        last=now
        if snapshot.source=='live':frames.add(snapshot.captured_at);identities.add(id(snapshot.grid))
        if len(frames)>=6 or now-started>15:app.quit()
    timer=QTimer();timer.timeout.connect(tick);timer.start(8);app.exec();reader.close()
    if reader.future:reader.future.result(timeout=3)
    ordered=sorted(samples)
    result=dict(ok=len(frames)>=6 and len(identities)==1 and reader.worker_pid!=os.getpid(),frames=len(frames),terrain_identities=len(identities),
        synthetic_discovery_ms=350,event_interval_p95_ms=round(ordered[int((len(ordered)-1)*.95)],2)if ordered else None,max_ms=round(max(samples),2)if samples else None)
    Path(destination).write_text(json.dumps(result),encoding='utf-8')
    if not result['ok']:raise RuntimeError('Isolated reader check failed')
