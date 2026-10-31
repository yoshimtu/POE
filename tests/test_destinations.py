import json
from pathlib import Path
import struct

import pytest

from exile.destinations import resolve_landmarks,marker_groups
from exile.model import Snapshot
from exile.plugins import PluginManager
from exile.reader import Reader

ROOT=Path(__file__).parents[1]
RULES=json.loads((ROOT/'plugins/routes/destinations.json').read_text())['areas']


@pytest.mark.parametrize('area,marker,name',[
    ('1_1_3','watercave','The Submerged Passage'),
    ('2_6_10','tunnel','The Western Forest'),
    ('MapWorldsCitadel','side_entrance','Arena'),
])
def test_zone_specific_terrain_targets_exist_without_loaded_entities(area,marker,name):
    grid=[bytes([5]*100)]*100
    landmarks=[dict(name=marker,path='Metadata/Terrain/Test.tdt',grid=(69,69))]
    rows=resolve_landmarks(area,landmarks,grid,RULES)
    assert len(rows)==1 and rows[0]['name']==name and rows[0]['grid']==(69,69)


def test_generic_features_stay_separate_and_decoration_is_not_a_destination():
    points=[(23,23),(46,23),(230,230)]
    assert sorted(map(len,marker_groups(points)))==[1,2]
    grid=[bytes([5]*300)]*300
    landmarks=[dict(name='entrance',path='Metadata/Terrain/Entrance.tdt',grid=p)for p in points]
    landmarks.append(dict(name='tree',path='Metadata/Terrain/BossTreeDecoration.tdt',grid=(100,100)))
    rows=resolve_landmarks('UnknownArea',landmarks,grid,{})
    assert len(rows)==2 and all(row['type']=='exit'for row in rows)
    assert rows[0]['locations']!=rows[1]['locations']


def test_large_feature_uses_walkable_edge_when_its_center_is_blocked():
    grid=[bytearray(200)for _ in range(200)]
    grid[23][23]=5
    landmarks=[dict(name='tunnel',path='Metadata/Terrain/Tunnel.tdt',grid=(23*x,23*y))
               for x in range(1,7)for y in range(1,7)]
    rows=resolve_landmarks('Zone',landmarks,grid,{'Zone':[dict(tile='tunnel',label='Exit',kind='exit')]})
    assert rows[0]['grid']==(23,23)


def test_exact_entrance_replaces_landmark_and_new_zone_discards_old_targets():
    manager=PluginManager(ROOT/'plugins');manager.discover()
    plugin=next(p for p in manager.plugins if p.id=='routes')
    snapshot=Snapshot(area='Riverways',area_id='2_6_10',grid=[bytes([5]*100)]*100,player_grid=(2,2),
        landmarks=[dict(name='tunnel',path='Metadata/Terrain/Test.tdt',grid=(69,69))])
    try:
        rows=plugin.targets(snapshot)
        assert len(rows)==1 and rows[0]['approximate']
        # A current native name can differ from an older terrain label.
        snapshot.entities=[dict(kind='exit',name='Renamed destination',grid=(75,75))]
        rows=plugin.targets(snapshot)
        assert len(rows)==1 and rows[0]['name']=='Renamed destination' and rows[0]['locations']==[(75,75)]
        snapshot.entities=[]
        assert len(plugin.targets(snapshot))==1  # exact known position retained
        snapshot.area='Coast';snapshot.area_id='1_1_3';snapshot.grid=[bytes([5]*100)]*100
        snapshot.landmarks=[dict(name='watercave',path='Metadata/Terrain/Water.tdt',grid=(46,46))]
        plugin.tick(snapshot,object())
        assert [row['name']for row in plugin.targets(snapshot)]==['The Submerged Passage']
    finally:plugin.stop()


def test_reader_bounds_and_caches_tile_descriptions_per_terrain_generation():
    offsets=dict(terrain_columns=0,terrain_rows=8,terrain_tiles=16,tile_record_size=56,
                 tile_file=8,tile_path=8,tile_detail=40,tile_name=0)
    class TileReader(Reader):
        def __init__(self):
            super().__init__({'offsets':offsets});self.grid_key='first';self.calls=0;self.bad=False
        def integer(self,address):return 2 if address==0 else 1
        def vector(self,address,stride,limit):
            raw=bytearray(112 if not self.bad else 56)
            struct.pack_into('<Q',raw,8,1000)
            if len(raw)>56:struct.pack_into('<Q',raw,64,1000)
            return raw
        def native_string(self,address,maximum=256):
            self.calls+=1
            return 'Metadata/Terrain/Exit.tdt' if address==1008 else 'tunnel'
        def q(self,address):
            assert address==1040
            return 2000
    reader=TileReader()
    first=reader.terrain_landmarks(0)
    assert len(first)==2 and first[1]['grid']==(23,0) and reader.calls==2
    assert reader.terrain_landmarks(0) is first and reader.calls==2
    reader.grid_key='next'
    assert reader.terrain_landmarks(0) is not first and reader.calls==4
    reader.grid_key='bad';reader.bad=True
    with pytest.raises(ValueError,match='allocation'):reader.terrain_landmarks(0)

def test_destination_approach_accepts_narrow_walkable_clearance():
    from exile.destinations import approach
    grid=[bytes([0]*60)for _ in range(60)]
    grid[25]=bytes([0]*20+[1]*20+[0]*20)
    point=approach([(23,23)],grid)
    assert point is not None and grid[point[1]][point[0]]==1

def test_unknown_map_transition_discovered_from_reused_campaign_asset():
    from exile.destinations import resolve_landmarks
    grid=[bytes([1]*80)for _ in range(80)]
    tiles=[dict(name='unfamiliar_campaign_door',path='Metadata/Terrain/Beach/Transitions/door.tdt',grid=(23,23)),dict(name='wall',path='Metadata/Terrain/Decorations/door.tdt',grid=(46,46))]
    targets=resolve_landmarks('MapWorldsUnfamiliar',tiles,grid,{})
    assert len(targets)==1 and targets[0]['type']=='exit' and targets[0]['approximate']
    assert not resolve_landmarks('1_1_1',tiles,grid,{})
