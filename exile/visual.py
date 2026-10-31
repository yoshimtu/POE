"""Independent bounded refresh of visual actor poses/vitals, never game input."""
from concurrent.futures import ThreadPoolExecutor
import logging
import threading
import time
from copy import copy


def merge_visual(snapshot, frame, now=None):
    now = time.monotonic() if now is None else now
    context = getattr(snapshot, 'visual_context', None)
    if (snapshot.source != 'live' or not (0 <= now-snapshot.captured_at <= .3 or snapshot.visual_fresh()) or
            not frame or not context or frame['key'] != context['key'] or
            not 0 <= now-frame['captured_at'] <= .075 or frame['captured_at'] < snapshot.captured_at):
        return snapshot.entities
    entities = []
    for entity in snapshot.entities:
        key = (entity.get('id'),entity.get('address'))
        if key not in frame['actors'] or entity.get('alive') is False:
            entities.append(entity)
            continue
        current = frame['actors'][key]
        visual = dict(entity)
        if current is None:
            visual['alive'] = False
        else:
            visual.update(current)
            if 'health_world' in current and 'matrix' in frame:
                visual['health_camera'] = (frame['matrix'],frame['viewport'])
            visual['position_captured_at'] = frame['captured_at']
        entities.append(visual)
    return entities


class VisualReader:
    def __init__(self, interval=1/120):
        self.interval = interval
        self.pool = ThreadPoolExecutor(max_workers=1,thread_name_prefix='visual-reader')
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.stopped = threading.Event()
        self.future = None
        self.key = None
        self.backend = self.snapshot = self.latest = None
        self.generation = 0

    def clear(self):
        with self.lock:
            self.generation += 1
            self.key = None
            self.latest = None
        self.wake.set()

    def _run(self):
        while not self.stopped.is_set():
            started = time.monotonic()
            with self.lock:
                backend,snapshot,key,generation = self.backend,self.snapshot,self.key,self.generation
            active = bool(key and snapshot and 0<=time.monotonic()-snapshot.captured_at<=2)
            result = None
            if active:
                try:
                    result = backend.poll_visual(snapshot)
                except Exception:
                    logging.exception('Visual reader failed')
            with self.lock:
                if backend is self.backend and key == self.key and generation == self.generation:
                    self.latest = result
            if not active:
                self.wake.wait(.05)
            else:
                deadline = started+self.interval
                while not self.stopped.is_set() and not self.wake.is_set():
                    remaining = deadline-time.monotonic()
                    if remaining <= 0:
                        break
                    time.sleep(min(.005,remaining))
            self.wake.clear()

    def poll(self, backend, snapshot, enabled, camera_only=False):
        context = getattr(snapshot,'visual_context',None)
        key = (context['key'],id(getattr(backend,'visual_adapter',None)),camera_only) if enabled and context else None
        working = snapshot
        if camera_only and context:
            working = copy(snapshot)
            working.visual_context = dict(context,actors=())
        with self.lock:
            if backend is not self.backend or key != self.key:
                self.generation += 1
                self.latest = None
                self.wake.set()
            self.backend,self.snapshot,self.key = backend,working,key
            latest = self.latest
        if key is not None and self.future is None:
            self.future = self.pool.submit(self._run)
        valid=bool(latest and context and latest['key']==context['key']and 0<=time.monotonic()-latest['captured_at']<=.075)
        if valid and latest.get('invalidated'):snapshot.loading=True
        snapshot.visual_captured_at=latest['captured_at']if valid and not latest.get('invalidated')else 0
        return merge_visual(snapshot,latest)

    def camera(self,snapshot):
        with self.lock:
            frame=self.latest
        context=getattr(snapshot,'visual_context',None)
        if (not frame or not context or frame['key']!=context['key'] or
                not 0<=time.monotonic()-snapshot.captured_at<=2 or not 0<=time.monotonic()-frame['captured_at']<=.075 or 'matrix' not in frame):
            return snapshot.camera
        return dict(matrix=frame['matrix'],viewport=frame['viewport'],captured_at=frame['captured_at'],
                    player_world=frame.get('player_world'))

    def map_pose(self,snapshot):
        with self.lock:frame=self.latest
        context=getattr(snapshot,'visual_context',None)
        if (not frame or not context or frame['key']!=context['key']or 'map_transform'not in frame or
                not 0<=time.monotonic()-snapshot.captured_at<=2 or not 0<=time.monotonic()-frame['captured_at']<=.075 or
                frame['captured_at']<snapshot.captured_at):
            return snapshot.map_transform,snapshot.captured_at
        return frame['map_transform'],frame['captured_at']

    def close(self):
        self.stopped.set()
        self.clear()
        self.pool.shutdown(wait=False,cancel_futures=True)
