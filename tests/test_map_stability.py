import struct
import threading
import time
import pytest

from exile.live import LiveReader
from exile.mapview import MapMotion, outline_rows
from exile.model import Snapshot
from exile.reader import Reader


def test_bad_buff_does_not_discard_other_records():
    class BuffReader(Reader):
        def __init__(self):
            super().__init__({'offsets': dict(buffs_vector=0, buff_definition=8, buff_time=24)})
            self.memory = self
        def vector(self, *_args, **_kwargs):
            return struct.pack('<QQ', 100, 200)
        def read(self, address, count):
            record = bytearray(48)
            struct.pack_into('<QQ', record, 0, 10, address + 200)
            struct.pack_into('<ff', record, 24, 2., 3.)
            return bytes(record)
        def q(self, address):
            return address
        def utf16(self, address):
            return 'valid_buff' if address == 300 else 'unrecognized buff identifier!'
    reader = BuffReader()
    buffs = reader.buffs(10)
    assert [buff['id'] for buff in buffs] == ['valid_buff']
    assert not reader.buff_read_complete


def test_map_outline_has_transparent_interior_and_keeps_holes():
    grid = [bytes([1] * 9) for _ in range(9)]
    rows = outline_rows(grid, 1)
    assert rows[0] == rows[-1] == bytes([1] * 9)
    assert rows[4] == bytes([1, 0, 0, 0, 0, 0, 0, 0, 1])
    grid[4] = bytes([1, 1, 1, 1, 0, 1, 1, 1, 1])
    rows = outline_rows(grid, 1)
    assert rows[4][4] == 0
    assert rows[4][3] == rows[3][4] == 1


def test_map_interpolation_does_not_mutate_live_snapshot_and_resets_on_teleport():
    grid = [[1]]
    def snapshot(captured, x):
        return Snapshot(source='live', captured_at=captured, area='Beacon', grid=grid,
                        map_transform=dict(mode='large', clip=(0, 0, 1920, 1080),
                                           center=(960, 520), player=(x, 0), basis_x=.6, basis_y=-.5))
    motion = MapMotion(delay=.05)
    motion.sample(snapshot(10, 0), now=10)
    latest = snapshot(10.1, 6)
    assert abs(motion.sample(latest, now=10.1)['player'][0] - 3) < 1e-9
    assert latest.map_transform['player'] == (6, 0)
    assert motion.sample(snapshot(10.2, 100), now=10.2)['player'] == (100, 0)
    assert motion.sample(Snapshot(), now=10.3) is None


def test_background_reader_does_not_block_ui_and_rejects_cleared_job():
    started, release = threading.Event(), threading.Event()
    next_started, release_next = threading.Event(), threading.Event()
    class Backend:
        calls = 0
        def poll(self):
            self.calls += 1
            if self.calls > 1:
                next_started.set()
                assert release_next.wait(2)
            started.set()
            assert release.wait(2)
            return Snapshot(source='live', captured_at=time.monotonic(), area='Old area')
    reader, backend = LiveReader(interval=1), Backend()
    try:
        before = time.monotonic()
        assert reader.poll(backend).source == 'disconnected'
        assert time.monotonic() - before < .2
        assert started.wait(1)
        reader.clear()
        release.set()
        # The continuous reader rejects the in-flight generation, then waits
        # rather than relying on a UI poll to dispatch its next read.
        assert next_started.wait(1)
        assert reader.poll(backend).source == 'disconnected'
    finally:
        release.set()
        release_next.set()
        reader.close()
        reader.future.result(timeout=1)


def test_map_motion_is_uniform_with_delay_longer_than_sample_interval_and_stops():
    grid = [[1]]
    motion = MapMotion(delay=.05)
    def snapshot(t, x, area='Forest', terrain=grid):
        return Snapshot(source='live', captured_at=t, area=area, grid=terrain,
                        map_transform=dict(mode='large', clip=(0, 0, 1920, 1080),
                                           center=(960, 520), player=(x, 0), basis_x=.6, basis_y=-.5))
    # 100 Hz reads, 200 Hz renders; a two-sample implementation snaps here.
    positions = []
    for frame in range(61):
        now = 10 + frame * .005
        captured = 10 + (frame // 2) * .01
        x = min(20, (captured - 10) * 100)
        latest = snapshot(captured, x)
        positions.append(motion.sample(latest, now=now)['player'][0])
    assert all(abs((b-a)-.5) < 1e-9 for a,b in zip(positions[12:38], positions[13:39]))
    assert max(positions) <= 20 and positions[-1] == 20
    # A new grid in the same named zone is a new instance, with no old motion.
    assert motion.sample(snapshot(10.31, 7, terrain=[[1]]), now=10.31)['player'] == (7, 0)


def test_fast_map_timestamps_advance_between_slow_core_snapshots():
    motion=MapMotion(delay=.02);grid=[[1]];values=[]
    for frame in range(80):
        now=10+frame/240;at=10+(frame//2)/120
        s=Snapshot(source='live',captured_at=10+(frame//20)/12,area='Zone',grid=grid,
            map_transform=dict(mode='large',clip=(0,0,1920,1080),center=(960,520),
                               player=(min(10,(at-10)*100),0),basis_x=.6,basis_y=-.5))
        s.map_captured_at=at
        values.append(motion.sample(s,now=now)['player'][0])
    assert all(abs(b-a-100/240)<1e-8 for a,b in zip(values[8:23],values[9:24]))
    assert values[-1]==10 and max(values)<=10  # no extrapolation/stop overshoot


def test_background_reader_keeps_reading_without_ui_polls_and_stops_cleanly():
    ready = threading.Event()
    class Backend:
        calls = 0
        def poll(self):
            self.calls += 1
            if self.calls >= 3:
                ready.set()
            return Snapshot(source='live', captured_at=time.monotonic())
    backend, reader = Backend(), LiveReader(interval=.005)
    try:
        reader.poll(backend)
        assert ready.wait(1)
    finally:
        reader.close()
        reader.future.result(timeout=1)


def test_entity_traversal_failure_preserves_map_but_not_an_actual_zone_change():
    class SceneReader(Reader):
        def __init__(self):
            super().__init__({'offsets': dict(state_root_rva=16, state_vtable_rva=32,
                state_session=48, session_vtable_rva=64, local_player=80, current_area=96,
                area_counter_rva=112, area_hash=128, positioned_grid=144,
                frame_context=160, camera_matrix=176, camera_viewport=192)})
            self.counter_reads = 0
            self.change_zone = False
            self.memory = self
        def main_image(self): return 0x10000
        def q(self, a):
            return {0x10010:0x20000, 0x20000:0x10020, 0x20030:0x30000,
                0x30000:0x10040, 0x30050:0x40000, 0x30060:0x50000,
                0x50000:1, 0x50008:2, 0x200a0:0x60000}[a]
        def integer(self, a):
            if a == 0x10070:
                self.counter_reads += 1
                return 2 if self.change_zone and self.counter_reads > 1 else 1
            return 99
        def path(self, a): return 'Metadata/Characters/Test'
        def components(self, a): return dict(Player=0x70000, Life=0x80000, Positioned=0x90000)
        def life(self, *args, **kw): return (100,100,100)
        def utf16(self, a): return 'Forest' if a==1 else 'The Forest'
        def terrain(self, *args): return [bytes([1]*10) for _ in range(10)]
        def terrain_heights(self, *args): return None
        def entity_addresses(self, a): raise ValueError('Entity tree changed while reading')
        def preloads(self, *args): return []
        def inventories(self, *args): return ([],[])
        def stash_layout(self, *args): pass
        def native_map(self, state, player, viewport): return dict(player=player, center=(960,520))
        def read(self, a, n):
            return {0x90090:struct.pack('<ii',3,4),
                0x600b0:struct.pack('<16f',*([0.]*16)),
                0x600c0:struct.pack('<ii',1920,1080)}[a]
    reader = SceneReader()
    window = type('Window', (), dict(pid=1))()
    snapshot = Reader.read(reader, reader, window)
    assert snapshot.source == 'live' and snapshot.map_transform['player'] == (3.5,4.5)
    assert snapshot.life == 100 and 'terrain' in snapshot.capabilities
    assert snapshot.entities == snapshot.hazards == []
    assert not {'entities','hazards'} & snapshot.capabilities
    reader.change_zone, reader.counter_reads = True, 0
    with pytest.raises(ValueError, match='Game area changed'):
        Reader.read(reader, reader, window)

def test_background_read_failure_preserves_only_still_fresh_frame():
    import time
    from exile.live import LiveReader
    from exile.model import Snapshot
    for result,keep in ((Snapshot(),True),(Snapshot(source='live',loading=True),False)):
        reader=LiveReader();good=Snapshot(source='live',captured_at=time.monotonic(),in_game=True,loading=False)
        reader.latest=good
        class Backend:
            def poll(self):reader.stopped.set();return result
        reader.backend=Backend()
        reader._run()
        assert (reader.latest is good)==keep
        reader.close()
