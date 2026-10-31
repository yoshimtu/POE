"""Single background memory reader; the desktop never waits for a process read."""
from concurrent.futures import ThreadPoolExecutor
import logging
import time
import threading

from exile.model import Snapshot


class LiveReader:
    def __init__(self, interval=1 / 60):
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='memory-reader')
        self.interval = interval
        self.future = None
        self.backend = None
        self.generation = 0
        self.latest = Snapshot()
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.stopped = threading.Event()

    def clear(self):
        with self.lock:
            self.generation += 1
            self.latest = Snapshot()
        self.wake.set()

    def _run(self):
        # Schedule from read start, independently of Qt's paint/timer cadence.
        # The old UI-driven dispatch added up to a whole frame between reads.
        while not self.stopped.is_set():
            started = time.monotonic()
            with self.lock:
                owner, generation = self.backend, self.generation
            try:
                snapshot = owner.poll()
            except Exception:
                snapshot = Snapshot()
                logging.exception('Background memory read failed')
            cost=(time.monotonic()-started)*1000
            samples=getattr(self,'read_samples',[]);samples.append(cost);self.read_samples=samples[-1200:]
            if time.monotonic()-getattr(self,'read_log_at',0)>10:
                self.read_log_at=time.monotonic();ordered=sorted(self.read_samples)
                logging.info('Memory read timing: p50=%.1f p95=%.1f max=%.1f ms',ordered[len(ordered)//2],ordered[int((len(ordered)-1)*.95)],max(ordered));self.read_samples=[]
            with self.lock:
                if owner is self.backend and generation == self.generation:
                    # A failed read must not erase a still-fresh completed frame.
                    # Explicit live loading/logout snapshots still clear immediately.
                    if snapshot.source!='disconnected' or not self.latest.fresh():
                        self.latest = snapshot
            # Event.wait() rounded a requested 2 ms wait to ~15.5 ms on the
            # test machine. Python's high-resolution sleep measured ~2.5 ms.
            # Short bounded sleeps keep close/reset responsive without a spin.
            deadline = started + self.interval
            while not self.stopped.is_set() and not self.wake.is_set():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(.005, remaining))
            self.wake.clear()

    def poll(self, backend):
        if self.backend is not backend:
            with self.lock:
                self.backend = backend
                self.generation += 1
                self.latest = Snapshot()
            self.wake.set()
        if self.future is None:
            self.future = self.pool.submit(self._run)
        with self.lock:
            latest = self.latest
        return latest if latest.fresh() else Snapshot()

    def close(self):
        self.stopped.set()
        self.clear()
        self.pool.shutdown(wait=False, cancel_futures=True)
