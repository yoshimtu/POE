import time
from exile.model import Snapshot
from exile.reader_process import pack_snapshot
from exile.visual import merge_visual

def test_ipc_terrain_is_sent_only_on_change_without_mutating_source():
    grid=[[1,1],[1,1]];source=Snapshot(source='live',grid=grid)
    packed,key,terrain=pack_snapshot(source,None)
    assert source.grid is grid and packed.grid is None and terrain['grid']is grid
    other,key2,changed=pack_snapshot(source,key)
    assert key2==key and changed is None
    source.grid=[[2]]
    assert pack_snapshot(source,key)[2]['grid']==[[2]]

def test_fresh_validated_pose_updates_old_discovery_without_refreshing_metadata():
    now=time.monotonic();s=Snapshot(source='live',in_game=True,loading=False,captured_at=now-.5,
        entities=[dict(id=7,address=100,life=100,alive=True)])
    s.visual_context=dict(key=('same-session',));s.visual_captured_at=now
    frame=dict(key=('same-session',),captured_at=now,actors={(7,100):dict(life=0,alive=False)})
    assert not s.fresh()and s.visual_fresh()
    assert merge_visual(s,frame)[0]['alive']is False
    assert not s.fresh()  # UI freshness is never applied to item data
    s.captured_at=now-3;assert not s.visual_fresh()
    s.captured_at=now-.5;s.loading=True;assert not s.visual_fresh()
