"""Suppress duplicate outlines using the PoE window's native map pixels.

This is visual overlap detection, not a claim to read the client's fog-of-war
state. Frames stay in memory, target the exact game HWND, and are never saved.
"""
from concurrent.futures import ThreadPoolExecutor
import logging
import threading
import time

import cv2
import numpy as np
from PySide6.QtGui import QImage

cv2.setNumThreads(1)


def native_line_mask(bgra, margin=6):
    # Use SIMD byte operations for the broad color test, then evaluate the
    # signed background residual only at candidate pixels. Expanding six whole
    # viewport channels to int16 cost ~90 ms per capture on the test machine.
    blue, green, red = (cv2.extractChannel(bgra, i) for i in range(3))
    br, bg = cv2.subtract(blue, red), cv2.subtract(blue, green)
    lines = cv2.bitwise_and(cv2.compare(br, 16, cv2.CMP_GE), cv2.compare(bg, 14, cv2.CMP_GE))
    for test in (cv2.compare(cv2.max(br, bg), 85, cv2.CMP_LT),
                 cv2.compare(cv2.absdiff(red, green), 18, cv2.CMP_LE),
                 cv2.compare(green, 55, cv2.CMP_GE), cv2.compare(red, 55, cv2.CMP_GE)):
        cv2.bitwise_and(lines, test, dst=lines)
    candidates = cv2.findNonZero(lines)
    if candidates is None:
        return lines
    xs, ys = candidates[:, 0, 0], candidates[:, 0, 1]
    # Median on BGRA avoids a full BGR copy; channels are filtered independently.
    background = cv2.medianBlur(bgra, 5)
    sample = background[ys, xs, :3].astype(np.int16)
    keep = ((br[ys, xs].astype(np.int16) - (sample[:, 0] - sample[:, 2]) >= 8)
            & (bg[ys, xs].astype(np.int16) - (sample[:, 0] - sample[:, 1]) >= 6))
    lines[ys[~keep], xs[~keep]] = 0
    # Reject broad blue scene surfaces while retaining thin map geometry.
    broad = cv2.erode(lines, np.ones((5, 5), dtype=np.uint8))
    broad = cv2.dilate(broad, np.ones((7, 7), dtype=np.uint8))
    cv2.bitwise_and(lines, cv2.bitwise_not(broad), dst=lines)
    if margin:
        lines = cv2.dilate(lines, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (margin * 2 + 1, margin * 2 + 1)))
    return lines


def map_translation(transform):
    x, y = transform['player']
    return (transform['center'][0] - (x - y) * transform['basis_x'],
            transform['center'][1] - (x + y) * transform['basis_y'])


def confirmed_native_lines(lines, previous, shift, margin):
    """Require two map-aligned observations; don't mask one-frame scenery."""
    if previous is None:
        return np.zeros_like(lines)
    aligned = cv2.warpAffine(previous, np.float32([[1, 0, shift[0]], [0, 1, shift[1]]]),
                             (lines.shape[1], lines.shape[0]), flags=cv2.INTER_NEAREST)
    tolerance = cv2.dilate(aligned, np.ones((5, 5), dtype=np.uint8))
    confirmed = cv2.bitwise_and(lines, tolerance)
    if margin:
        confirmed = cv2.dilate(confirmed, cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                                               (margin * 2 + 1, margin * 2 + 1)))
    return confirmed


class NativeMapOverlap:
    def __init__(self):
        self.lock = threading.Lock()
        self.control = None
        self.capture = None
        self.hwnd = 0
        self.state = None
        self.last = None
        self.last_frame = 0
        self.previous_lines = None
        self.retry_at = 0
        self.error = ''
        self.lifecycle=ThreadPoolExecutor(max_workers=1,thread_name_prefix='map-capture-lifecycle')
        self.starting=False;self.capture_generation=0

    def configure(self, window, snapshot, enabled, margin=6):
        active = bool(enabled and window.foreground and snapshot.source == 'live'
                      and (snapshot.fresh()or snapshot.visual_fresh()) and snapshot.map_transform)
        if not active:
            with self.lock:
                self.state = None
                self.last = None
                self.previous_lines = None
            self.stop()
            return
        transform = dict(snapshot.map_transform)
        key = (snapshot.area, id(snapshot.grid), transform['mode'], transform['clip'],
               transform['basis_x'], transform['basis_y'], margin)
        state = dict(key=key, transform=transform, size=(window.width, window.height), margin=margin)
        with self.lock:
            self.state = state
        if self.hwnd != window.hwnd:
            self.stop()
            self.hwnd = window.hwnd
            with self.lock:
                self.state = state
        if self.control is not None and self.control.is_finished():
            self.control = None
            self.retry_at = 0
        if self.control is None and not self.starting and time.monotonic()>=self.retry_at:
            self.retry_at=time.monotonic()+10;self.starting=True
            self.lifecycle.submit(self._start_capture,window.hwnd,self.capture_generation)

    @staticmethod
    def _release_capture(control,capture):
        if control is not None:
            try:
                if not control.is_finished():control.stop()
            except Exception:logging.exception('Native map capture stop failed')

    def _start_capture(self,hwnd,generation):
        try:
            from windows_capture import WindowsCapture
            capture=WindowsCapture(window_hwnd=hwnd,cursor_capture=False,draw_border=False,
                secondary_window=False,minimum_update_interval=100)
            @capture.event
            def on_frame_arrived(frame,control):
                if generation==self.capture_generation:self._frame(frame)
            @capture.event
            def on_closed():
                with self.lock:
                    if generation==self.capture_generation:self.state=self.last=None
            control=capture.start_free_threaded()
            with self.lock:
                accepted=generation==self.capture_generation
                if accepted:self.capture=capture;self.control=control;self.error=''
            if not accepted:self._release_capture(control,capture)
        except Exception as exc:
            self.error=str(exc);logging.warning('Native map capture unavailable: %s',exc)
        finally:self.starting=False

    def _frame(self, frame):
        now = time.monotonic()
        if now - self.last_frame < .09:
            return
        with self.lock:
            state = self.state
        if state is None:
            return
        self.last_frame = now
        if (frame.width, frame.height) != state['size']:
            self.error = 'Game capture size differs from client viewport'
            return
        x, y, width, height = state['transform']['clip']
        x, y = max(0, int(x)), max(0, int(y))
        right, bottom = min(frame.width, int(x + width)), min(frame.height, int(y + height))
        if right <= x or bottom <= y:
            return
        try:
            lines = native_line_mask(frame.frame_buffer[y:bottom, x:right], 0)
            translation = map_translation(state['transform'])
            with self.lock:
                previous = self.previous_lines
            if (previous is not None and previous['key'] == state['key'] and
                    now - previous['at'] < .3):
                shift = tuple(a-b for a,b in zip(translation, previous['translation']))
                mask = confirmed_native_lines(lines, previous['lines'], shift, state['margin'])
            else:
                mask = confirmed_native_lines(lines, None, (0, 0), state['margin'])
            stride = (mask.shape[1] + 3) & ~3
            if stride != mask.shape[1]:
                mask = np.pad(mask, ((0, 0), (0, stride - mask.shape[1])))
            image = QImage(mask.tobytes(), right - x, bottom - y, stride, QImage.Format.Format_Indexed8).copy()
            image.setColorTable([(alpha << 24) | 0xffffff for alpha in range(256)])
            image = image.convertToFormat(QImage.Format.Format_RGBA8888)
            result = dict(key=state['key'], image=image, origin=(x, y), at=now,
                          translation=translation)
            with self.lock:
                if self.state is not None and self.state['key'] == state['key']:
                    self.last = result
                    self.previous_lines = dict(key=state['key'], lines=lines, at=now, translation=translation)
            self.error = ''
        except Exception as exc:
            self.error = str(exc)

    def get(self, snapshot):
        with self.lock:
            last, state = self.last, self.state
        if not last or not state or last['key'] != state['key'] or time.monotonic() - last['at'] > .5:
            return None
        current = map_translation(snapshot.map_transform)
        shift = (last['origin'][0] + current[0] - last['translation'][0],
                 last['origin'][1] + current[1] - last['translation'][1])
        return last['image'], shift

    def stop(self):
        with self.lock:
            self.capture_generation+=1
            control,capture=self.control,self.capture
            self.control=self.capture=None
            self.state=self.last=None;self.previous_lines=None
        if control is not None or capture is not None:self.lifecycle.submit(self._release_capture,control,capture)
