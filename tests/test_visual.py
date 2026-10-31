import json
from pathlib import Path
import struct
import threading
import time
import pytest

from exile.model import Snapshot
from exile.reader import Reader
from exile.visual import VisualReader, merge_visual


def snapshot(at=None):
    s=Snapshot(source='live',captured_at=time.monotonic() if at is None else at,
        entities=[dict(id=7,address=100,kind='monster',alive=True,life=100,max_life=100,screen=(10,20))])
    s.visual_context=dict(key=('instance',1),actors=((7,100),))
    return s


def test_visual_merge_never_predicts_health_resurrects_a_corpse_or_extends_stale_core():
    s=snapshot(10)
    frame=dict(key=('instance',1),captured_at=10.01,actors={(7,100):dict(life=0,max_life=100,alive=False)})
    assert merge_visual(s,frame,now=10.02)[0]['life']==0
    assert s.entities[0]['life']==100
    frame['actors'][(7,100)]=dict(life=80,max_life=100,alive=True,screen=(30,40))
    merged=merge_visual(s,frame,now=10.02)[0]
    assert merged['screen']==(30,40) and merged['position_captured_at']==10.01
    s.entities[0].update(life=0,alive=False)
    assert merge_visual(s,frame,now=10.02)[0]['life']==0
    s=snapshot(10)
    assert merge_visual(s,frame,now=10.2) is s.entities
    frame['key']=('different instance',2)
    assert merge_visual(s,frame,now=10.02) is s.entities
    frame['key']=('instance',1);frame['captured_at']=9.99
    assert merge_visual(s,frame,now=10.02) is s.entities


def test_visual_reader_updates_between_full_scans_and_stops():
    ready=threading.Event()
    class Backend:
        calls=0
        def poll_visual(self,s):
            self.calls+=1
            if self.calls>=3:ready.set()
            return dict(key=s.visual_context['key'],captured_at=time.monotonic(),
                        actors={(7,100):dict(life=50,max_life=100,alive=True,screen=(self.calls,0))})
    reader,backend,s=VisualReader(interval=.005),Backend(),snapshot()
    try:
        start=time.monotonic()
        reader.poll(backend,s,True)
        assert time.monotonic()-start<.1
        assert ready.wait(1)
        assert reader.poll(backend,s,True)[0]['life']==50
        assert reader.poll(backend,s,False)[0]['life']==100
    finally:
        reader.close()
        reader.future.result(timeout=1)


def test_visual_job_is_rejected_after_reset_without_waiting_for_it():
    started,release=threading.Event(),threading.Event()
    class Backend:
        def poll_visual(self,s):
            started.set()
            assert release.wait(1)
            return dict(key=s.visual_context['key'],captured_at=time.monotonic(),
                        actors={(7,100):dict(life=0,alive=False)})
    reader,backend,s=VisualReader(),Backend(),snapshot()
    try:
        reader.poll(backend,s,True)
        assert started.wait(1)
        reader.clear()
        reader.close()
        release.set()
        reader.future.result(timeout=1)
        assert reader.latest is None
    finally:
        release.set()
        reader.close()


def test_camera_only_refresh_runs_without_monsters_and_does_not_change_health():
    ready=threading.Event()
    class Backend:
        def poll_visual(self,s):
            assert s.visual_context['actors']==()
            ready.set()
            return dict(key=s.visual_context['key'],captured_at=time.monotonic(),actors={},
                        matrix=[0.]*16,viewport=(1920,1080),player_world=(1,2,3))
    reader,backend,s=VisualReader(),Backend(),snapshot()
    s.visual_context['actors']=()
    try:
        reader.poll(backend,s,True,camera_only=True)
        assert ready.wait(1)
        reader.poll(backend,s,True,camera_only=True)
        camera=reader.camera(s)
        assert camera['viewport']==(1920,1080) and camera['player_world']==(1,2,3)
        assert s.entities[0]['life']==100
    finally:
        reader.close()
        reader.future.result(timeout=1)
def visual_scene():
    profile=json.loads((Path(__file__).parents[1]/'profiles/steam-25113903.read-only.json').read_text())
    r=Reader(profile)
    regions={}
    def allocation(pointer,size,owner=None):
        data=bytearray(size)
        if owner:struct.pack_into('<Q',data,8,owner)
        regions[pointer]=data
        return data
    entity,render,life=0x60000,0x70000,0x80000
    pointers=struct.pack('<QQ',render,life)
    head=allocation(entity,0x90)
    struct.pack_into('<QQQ',head,0x10,0x90000,0x90010,0x90010)
    struct.pack_into('<I',head,0x88,7)
    regions[0x90000]=bytearray(pointers)
    data=allocation(render,0x200,entity);struct.pack_into('<fff',data,0x120,.5,.25,0)
    data=allocation(life,0x200,entity);struct.pack_into('<ii',data,0x178+0x2c,100,50)
    data=allocation(0xa0000,0x400)
    struct.pack_into('<16f',data,r.o['camera_matrix'],*(1. if i%5==0 else 0. for i in range(16)))
    struct.pack_into('<ii',data,r.o['camera_viewport'],1920,1080)
    class Memory:
        def read(self,address,count):
            for start,data in regions.items():
                if start<=address and address+count<=start+len(data):
                    return bytes(data[address-start:address-start+count])
            raise OSError('Missing test memory')
    s=snapshot();s.visual_context=dict(key=('instance',1),pid=8,base=0x10000,state=0x20000,session=0x30000,
        player=0x50000,area_record=0x40000,counter=1,area_hash=2,actors=((entity,7,render,life,pointers),))
    c=s.visual_context
    roots={c['base']+r.o['state_root_rva']:c['state'],c['state']:c['base']+r.o['state_vtable_rva'],
        c['state']+r.o['state_session']:c['session'],c['session']:c['base']+r.o['session_vtable_rva'],
        c['session']+r.o['local_player']:c['player'],c['session']+r.o['current_area']:c['area_record'],
        c['state']+r.o['frame_context']:0xa0000}
    r.q=lambda address:roots[address]
    r.integer=lambda address:1 if address==c['base']+r.o['area_counter_rva'] else 2
    return r,Memory(),s,type('Window',(),dict(pid=8))(),regions,roots


def test_fast_visual_reads_refresh_camera_health_and_validate_component_membership():
    r,m,s,w,regions,roots=visual_scene()
    frame=r.read_visual(m,w,s)
    actor=frame['actors'][(7,0x60000)]
    assert actor['life']==50 and actor['screen']==(1440,405)
    struct.pack_into('<i',regions[0x80000],0x178+0x30,0)
    assert r.read_visual(m,w,s)['actors'][(7,0x60000)]['alive'] is False
    struct.pack_into('<Q',regions[0x90000],8,0xb0000)
    assert (7,0x60000) not in r.read_visual(m,w,s)['actors']  # failed ownership read is not a death
    roots[s.visual_context['state']+r.o['state_session']]=0xc0000
    assert r.read_visual(m,w,s) is None


def test_fast_map_pose_uses_the_same_ground_height_projection_and_current_native_map():
    r,m,s,w,regions,roots=visual_scene();context=s.visual_context
    player_render=0xb0000;raw=bytearray(0x200)
    struct.pack_into('<QQ',raw,0,1,context['player'])
    struct.pack_into('<fff',raw,r.o['render_position'],2500.,5000.,10.)
    struct.pack_into('<f',raw,r.o['render_ground_height'],30.)
    regions[player_render]=raw;context['player_render']=player_render;s.terrain_heights=[[0]]
    calls=[]
    def native(state,player,viewport):
        calls.append((state,player,viewport))
        return dict(player=player,center=(960,520),mode='large',clip=(0,0,1920,1080),basis_x=.6,basis_y=-.5)
    r.native_map=native
    frame=r.read_visual(m,w,s)
    assert frame['map_transform']['player']==pytest.approx((228.62,458.62))
    assert calls[0][0]==context['state']and calls[0][2]==(1920,1080)
    assert frame['player_world']==(2500.,5000.,30.)
    assert s.map_transform is None  # worker does not mutate the core snapshot
    def changing_native(*args):
        roots[context['state']+r.o['state_session']]=0x99999
        return native(*args)
    r.native_map=changing_native
    assert r.read_visual(m,w,s)is None


def test_map_pose_rejects_stale_or_other_instance_frames_but_can_hide_a_closed_map():
    reader=VisualReader();s=snapshot();now=time.monotonic();s.captured_at=now-.05
    s.map_transform=dict(player=(1,2));key=s.visual_context['key']
    try:
        reader.latest=dict(key=key,captured_at=now-.005,map_transform=dict(player=(3,4)))
        transform,at=reader.map_pose(s)
        assert transform['player']==(3,4)and at>s.captured_at
        assert s.map_transform['player']==(1,2)and s.entities[0]['life']==100
        reader.latest['key']=('wrong instance',)
        assert reader.map_pose(s)==(s.map_transform,s.captured_at)
        reader.latest.update(key=key,captured_at=now-.08)
        assert reader.map_pose(s)==(s.map_transform,s.captured_at)
        reader.latest.update(captured_at=now,map_transform=None)
        assert reader.map_pose(s)==(None,now)
    finally:reader.close()

def test_camera_keeps_refreshing_without_live_health_bar_actors():
    ready=threading.Event()
    s=snapshot();s.visual_context=dict(key=('instance',1),actors=())
    class Backend:
        def poll_visual(self,s):
            ready.set()
            return dict(key=s.visual_context['key'],captured_at=time.monotonic(),actors={},matrix=tuple(range(16)),viewport=(1920,1080))
    reader=VisualReader(interval=.005)
    try:
        reader.poll(Backend(),s,True,camera_only=False)
        assert ready.wait(1)
        assert reader.key is not None
    finally:
        reader.close()
        if reader.future:reader.future.result(timeout=1)
