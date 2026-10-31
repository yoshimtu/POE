from pathlib import Path

import pytest

from exile.model import Snapshot
from exile.plugins import PluginManager
from exile.routing import RoutePlanner
from exile.terrain import walkable_regions


def plugin():
    manager=PluginManager(Path(__file__).parents[1]/'plugins');manager.discover()
    return next(p for p in manager.plugins if p.id=='routes')


def test_regions_allow_narrow_corridors_but_do_not_connect_diagonal_corners():
    regions=walkable_regions([bytes([5,0,5]),bytes([0,5,1])])
    assert regions[0,0]!=regions[1,1] and regions[0,0]!=regions[0,2]
    assert regions[1,1]==regions[1,2]==regions[0,2]
    assert not regions.flags.writeable
    with pytest.raises(ValueError):walkable_regions([])


def test_transition_legend_and_line_switch_sides_without_resetting_the_instance():
    p=plugin();p.planner=RoutePlanner(processes=False)
    grid=[bytes([5,5,5,0,5,5,5])for _ in range(5)]
    snapshot=Snapshot(source='preview',area='Cells',player_grid=(0,2),grid=grid,
        walkable_regions=walkable_regions(grid),entities=[
            dict(kind='exit',name='Arena',grid=(2,2)),
            dict(kind='exit',name='Cells',grid=(4,2))])
    try:
        for position,name in (((0,2),'Arena'),((6,2),'Cells'),((0,2),'Arena')):
            snapshot.player_grid=position
            marks=p.tick(snapshot,object())
            assert [r['name']for r in marks[-1].payload['rows']]==[f'Exit · {name}']
            p.planner.future.result(timeout=1)
            marks=p.tick(snapshot,object())
            assert sum(m.kind=='path'for m in marks)==1
            assert [r['name']for r in marks[-1].payload['rows']]==[f'Exit · {name}']
            snapshot.entities=[]  # retain known exits, but never list the other side
    finally:p.stop()


def test_filter_runs_before_route_limit_and_keeps_reachable_alternative_entrances():
    p=plugin();p.settings['max_routes']=1
    grid=[bytes([5,5,5,0,5,5,5])for _ in range(5)]
    snapshot=Snapshot(area='Test',player_grid=(2,2),grid=grid,walkable_regions=walkable_regions(grid),entities=[
        dict(kind='exit',name='Wrong side',grid=(4,2)),
        dict(kind='exit',name='Destination',grid=(5,0)),
        dict(kind='exit',name='Destination',grid=(0,0))])
    try:
        rows=p.targets(snapshot)
        assert len(rows)==1 and rows[0]['name']=='Destination'
        assert rows[0]['locations']==[(0,0)]
        # A fresh terrain generation must invalidate cached blocked-cell regions.
        changed=[bytes([5]*7)for _ in range(5)]
        snapshot.grid=changed;snapshot.walkable_regions=walkable_regions(changed)
        snapshot.player_grid=(6,2)
        assert p.targets(snapshot)[0]['name']=='Wrong side'
    finally:p.stop()
