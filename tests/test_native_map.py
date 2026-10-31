import struct
import cv2
import time
import numpy as np

from exile.native_map import native_line_mask, map_translation, confirmed_native_lines, NativeMapOverlap
from exile.model import Snapshot
from exile.terrain import decode_height_samples, decode_height_tiles, terrain_grid_point, height_correct_outline


def test_palette_heights_and_signed_samples():
    payload = bytearray(137)
    payload[:4] = bytes([0, 1, 255, 254])
    payload[4] = 0b11100100
    assert decode_height_samples(payload)[:4].tolist() == [0, 1, -1, -2]
    assert decode_height_samples(bytes([255])).tolist() == [-1] * 529
    assert decode_height_samples(b'').tolist() == [0] * 529


def test_height_rotation_and_player_projection_use_same_units():
    tile = bytearray(56)
    struct.pack_into('<Q', tile, 0, 123)
    struct.pack_into('<h', tile, 48, 24)
    tile[54] = 4  # horizontal reflection
    raw = bytes((x % 23 for x in range(529)))
    heights = decode_height_tiles(tile, 1, 1, lambda pointer: raw)
    assert heights[0, 0] == 46 and heights[0, 22] == 24
    # A point and its player anchor at the same ground height agree exactly.
    point = terrain_grid_point(np.full((2, 2), 24, dtype=np.int16), (1, 1))
    assert point == (9.625, 9.625)


def test_height_corrected_outline_moves_both_axes_and_preserves_empty_pixels():
    mask, origin = height_correct_outline([bytes([1, 0]), bytes([0, 0])], np.full((2, 2), 24, dtype=np.int16))
    assert origin == (8, 8)
    assert np.count_nonzero(mask) == 4  # subpixel splat, no filled interiors
    flat, origin = height_correct_outline([bytes([1, 0])], None)
    assert flat.tolist() == [[255, 0]]


def test_native_map_mask_finds_lavender_lines_but_not_gold_or_saturated_effects():
    image = np.zeros((40, 60, 4), dtype=np.uint8)
    image[10, 5:20, :3] = [190, 150, 150]
    image[20, 5:20, :3] = [114, 156, 180]  # added gold
    image[30, 5:20, :3] = [255, 50, 10]   # saturated blue effect
    mask = native_line_mask(image, 2)
    assert mask[10, 10] == 255 and mask[12, 10] == 255
    assert mask[20, 10] == 0 and mask[30, 10] == 0


def test_native_mask_translation_tracks_height_corrected_player_and_pan():
    transform = dict(player=(10, 20), center=(960, 520), basis_x=.6, basis_y=-.5)
    assert map_translation(transform) == (966, 535)


def test_optimized_mask_is_pixel_identical_to_original_classifier():
    image = np.random.default_rng(1920).integers(0, 256, (100, 160, 4), dtype=np.uint8)
    blue, green, red = (image[:, :, i].astype(np.int16) for i in range(3))
    background = cv2.medianBlur(np.ascontiguousarray(image[:, :, :3]), 5).astype(np.int16)
    db, dg, dr = (image[:, :, i].astype(np.int16)-background[:, :, i] for i in range(3))
    expected = ((blue-red >= 16) & (blue-green >= 14) & (blue-np.minimum(red,green) < 85)
                & (np.abs(red-green) <= 18) & (green >= 55) & (red >= 55)
                & (db-dr >= 8) & (db-dg >= 6)).astype(np.uint8)*255
    broad = cv2.dilate(cv2.erode(expected, np.ones((5,5),np.uint8)), np.ones((7,7),np.uint8))
    expected[broad > 0] = 0
    expected = cv2.dilate(expected, cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(13,13)))
    assert np.array_equal(native_line_mask(image), expected)


def test_native_mask_confirms_map_motion_and_rejects_transient_scene_lines():
    before = np.zeros((60, 80), np.uint8)
    before[10:30, 20] = 255
    current = np.zeros_like(before)
    current[13:33, 24] = 255  # existing native line after map translation
    current[40:50, 60] = 255  # a scene effect seen in only this frame
    assert not confirmed_native_lines(current, None, (0,0), 6).any()
    result = confirmed_native_lines(current, before, (4,3), 6)
    assert result[20,24] == 255 and result[45,60] == 0


def test_native_capture_stops_when_game_loses_focus():
    class Control:
        stopped = False
        def is_finished(self): return False
        def stop(self): self.stopped = True
    overlap, control = NativeMapOverlap(), Control()
    overlap.control = control
    overlap.configure(type('Window', (), dict(foreground=False))(),
        Snapshot(source='live', captured_at=time.monotonic(), map_transform={'mode':'large'}), True)
    overlap.lifecycle.submit(lambda:None).result(timeout=1)
    assert control.stopped and overlap.control is None and overlap.state is None


def test_slow_capture_shutdown_never_blocks_overlay_thread():
    import threading
    entered=threading.Event();release=threading.Event()
    class Control:
        def is_finished(self):return False
        def stop(self):entered.set();release.wait(2)
    overlap=NativeMapOverlap();overlap.control=Control()
    try:
        start=time.perf_counter();overlap.stop()
        assert time.perf_counter()-start<.1
        assert entered.wait(1)and overlap.control is None
    finally:
        release.set();overlap.lifecycle.shutdown(wait=True)
