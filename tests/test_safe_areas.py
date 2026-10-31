from pathlib import Path
import time

import pytest

from exile.areas import town_or_hideout
from exile.model import Snapshot
from exile.plugins import PluginManager


@pytest.mark.parametrize('area_id,name',[
    ('1_1_town',"Lioneye's Watch"),('HideoutCelestialNebula','Celestial Nebula Hideout'),
    ('KaruiShores','Karui Shores'),('Kingsmarch','Kingsmarch'),('HeistHub','The Rogue Harbour'),
])
def test_safe_hubs_include_towns_and_hideouts(area_id,name):
    assert town_or_hideout(area_id,name)


def test_town_in_a_combat_map_identifier_does_not_make_it_a_safe_hub():
    assert not town_or_hideout('MapWorldsGhostTown','Deserted Town')
    assert not town_or_hideout('1_6_1','The Southern Forest')


def modules():
    manager=PluginManager(Path(__file__).parents[1]/'plugins');manager.discover()
    return {p.id:p for p in manager.plugins}


def snapshot(town=False):
    return Snapshot(source='live',captured_at=time.monotonic(),in_game=True,loading=False,town=town,
        area='Map',area_id='MapWorldsExample',player_grid=(1,1),grid=[bytes([5]*12)for _ in range(12)],
        map_transform=dict(mode='large',clip=(0,0,800,600),player=(1,1),center=(400,300),basis_x=.6,basis_y=-.5),
        entities=[dict(kind='valuable',category='waypoint',name='Waypoint',grid=(5,5)),
                  dict(kind='monster',rarity=2,name='Rare',grid=(3,3),screen=(200,200),life=100,max_life=100,alive=True)],
        capabilities={'terrain','entities','health'})


def test_safe_areas_hide_objects_and_resume_them_without_changing_monster_bar_preferences():
    radar=modules()['radar'];s=snapshot()
    assert any(m.text=='Waypoint'for m in radar.tick(s,None))
    s.town=True
    marks=radar.tick(s,None)
    assert not any(m.text=='Waypoint'for m in marks)
    assert any(m.kind=='bar'for m in marks)
    s.town=False
    assert any(m.text=='Waypoint'for m in radar.tick(s,None))


def test_routes_clear_legend_and_stop_planning_in_hubs_then_resume(monkeypatch):
    routes=modules()['routes'];planners=[]
    class Planner:
        closed=False
        def __init__(self,**kwargs):planners.append(self)
        def poll(self,*args,**kwargs):return{}
        def close(self):self.closed=True
    monkeypatch.setitem(type(routes).tick.__globals__,'RoutePlanner',Planner)
    s=snapshot();s.entities=[dict(kind='exit',name='Next Area',grid=(8,8))]
    assert any(m.kind=='route_legend'for m in routes.tick(s,None))
    s.town=True
    assert routes.tick(s,None)==[]and routes.planner is None and planners[0].closed
    s.town=False
    assert any(m.kind=='route_legend'for m in routes.tick(s,None))
    routes.stop()
