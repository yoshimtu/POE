import heapq
import math
from pathlib import Path
import threading
import time

import numpy as np

from exile.model import Snapshot,Mark
from exile.navigation import route
from exile.plugins import PluginManager
from exile.routing import nearest_walkable,world_path,project_path,RoutePlanner,route_tail_cost
from concurrent.futures import Future
from exile.route_legend import legend_height


def plugin():
    manager=PluginManager(Path(__file__).parents[1]/'plugins');manager.discover()
    return next(p for p in manager.plugins if p.id=='routes')


def cost(path):
    return sum(math.dist(a,b) for a,b in zip(path,path[1:]))


def test_route_is_shortest_and_does_not_cut_corners_or_use_low_clearance():
    grid=[bytes([5]*14)for _ in range(14)]
    for y in range(11):grid[y]=grid[y][:6]+bytes([0])+grid[y][7:]
    result=route(grid,(1,1),(11,1),walk_values=(4,5))
    queue=[(0.,(1,1))];seen={}
    expected=None
    while queue:
        distance,point=heapq.heappop(queue)
        if point in seen:continue
        seen[point]=distance
        if point==(11,1):expected=distance;break
        x,y=point
        for dx,dy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
            nx,ny=x+dx,y+dy
            if not 0<=nx<14 or not 0<=ny<14 or grid[ny][nx] not in (4,5):continue
            if dx and dy and (not grid[y][nx] or not grid[ny][x]):continue
            heapq.heappush(queue,(distance+math.hypot(dx,dy),(nx,ny)))
    assert abs(cost(result)-expected)<1e-9
    assert not route([bytes([5,1,5])],(0,0),(2,0),walk_values=(4,5))
    assert route([bytes([5])*5000],(0,0),(2,0),walk_values=(4,5))==[(0,0),(1,0),(2,0)]


def test_blocked_transition_uses_nearby_walkable_approach_and_ground_height():
    grid=[bytes([5,5,0]),bytes([5,5,0])]
    goal=nearest_walkable(grid,(2,1),(4,5))
    assert goal==(1,1)
    path=route(grid,(0,0),goal,walk_values=(4,5))
    world=world_path(path,np.full((2,3),24,np.int16))
    assert np.all(world[:,2]==-187.5)
    assert abs(world[0,0]-(.5*250/23))<1e-9


def test_projection_clips_segments_without_joining_across_an_offscreen_gap():
    matrix=[1. if i%5==0 else 0. for i in range(16)]
    camera=dict(matrix=matrix,viewport=(1000,1000))
    world=np.array([[-.5,0,0],[-.5,2,0],[.5,2,0],[.5,0,0]])
    lines=project_path(world,camera)
    assert len(lines)==2
    assert lines[0][-1]==(250,0) and lines[1][0]==(750,0)
    assert all(0<=x<=1000 and 0<=y<=1000 for line in lines for x,y in line)


def test_routes_have_distinct_stable_colors_and_remove_dead_bosses():
    p=plugin();grid=[bytes([1]*25)]*25
    s=Snapshot(source='preview',area='Test',grid=grid,player_grid=(2,2),entities=[
        dict(id=1,kind='exit',name='Area A',grid=(20,2)),
        dict(id=2,kind='exit',name='Area B',grid=(20,20)),
        dict(id=3,kind='boss',is_map_boss=True,name='Boss',grid=(2,20),life=100,alive=True,hostile=True)])
    try:
        rows=p.tick(s,object())[-1].payload['rows']
        colors={r['name']:r['color'] for r in rows}
        assert len(set(colors.values()))==3
        p.planner.future.result(timeout=2)
        marks=p.tick(s,object())
        assert sum(m.kind=='path' for m in marks)==3
        s.entities[2].update(life=0,alive=False)
        rows=p.tick(s,object())[-1].payload['rows']
        assert len(rows)==2 and all(r['color']==colors[r['name']] for r in rows)
        s.entities=[]
        assert len(p.tick(s,object())[-1].payload['rows'])==2  # known static exits
        s.area='Other';s.grid=[bytes([1]*25)]*25
        assert not p.tick(s,object())[-1].payload['rows']
    finally:p.stop()


def test_planning_is_nonblocking_and_rejects_a_previous_instance_result():
    planner=RoutePlanner(processes=False);entered,release=threading.Event(),threading.Event()
    def search(key,*args):
        entered.set();assert release.wait(2);return key,{'old':'not valid in new instance'}
    planner.search=search
    args=([bytes([5]*4)]*4,None,(0,0),[dict(key=1,grid=(3,3))],(4,5),.5)
    try:
        start=time.monotonic();assert not planner.poll('old',*args)
        assert time.monotonic()-start<.1 and entered.wait(1)
        planner.reset('new');release.set();planner.future.result(timeout=1)
        assert not planner.poll('new',args[0],None,(0,0),[],(4,5),.5)
    finally:release.set();planner.close()


def test_invalid_cached_connection_forces_replan_even_after_small_position_change():
    p=plugin();grid=[bytearray([5]*10)for _ in range(10)]
    p.planner=RoutePlanner(processes=False)
    for y in range(8):grid[y][4]=0
    s=Snapshot(source='live',town=False,area='Test',grid=grid,terrain_heights=np.zeros((10,10),np.int16),
        player_grid=(3,4),camera=dict(matrix=[1. if i%5==0 else 0. for i in range(16)],viewport=(1000,1000)),
        entities=[dict(id=1,address=100,kind='exit',name='Exit',grid=(3,1))])
    try:
        p.tick(s,object());p.planner.future.result(timeout=1);p.tick(s,object())
        s.player_grid=(5,4)  # only two cells away, but separated by a wall
        rows=p.tick(s,object())[-1].payload['rows']
        assert rows[0]['status']=='Recalculating…' and p.planner.force
        p.tick(s,object());p.planner.future.result(timeout=1)
        assert p.tick(s,object())[-1].payload['rows'][0]['status']==''
    finally:p.stop()


def test_legend_height_is_stable_when_route_status_changes():
    settings=dict(legend_font=11)
    ready=[dict(name='Exit',status='')]
    pending=[dict(name='Exit',status='Recalculating…')]
    assert legend_height(ready,settings)==legend_height(pending,settings)


def test_duplicate_destination_has_one_stable_color_and_uses_shortest_entrance():
    p=plugin();grid=[bytearray([5]*14)for _ in range(14)]
    for y in range(9):grid[y][3]=0
    s=Snapshot(source='preview',area='Test',grid=grid,player_grid=(1,4),entities=[
        dict(id=1,address=100,kind='exit',name='The Spawning Ground',grid=(4,4)),
        dict(id=2,address=200,kind='exit',name='The Spawning Ground',grid=(1,10))])
    try:
        first=p.tick(s,object())[-1].payload['rows']
        assert len(first)==1
        color=first[0]['color']
        p.planner.future.result(timeout=1);p.tick(s,object())
        result=next(iter(p.planner.results.values()))
        assert result['path'][-1]==(1,10) and result['cost']==6
        # An entrance's process address changes when it reloads: no new route.
        s.entities[0].update(id=99,address=999)
        rows=p.tick(s,object())[-1].payload['rows']
        assert len(rows)==1 and rows[0]['color']==color
    finally:p.stop()


def test_path_refresh_preference_migrates_and_has_separate_frame_rate_control():
    manager=PluginManager(Path(__file__).parents[1]/'plugins',{'routes':{'settings':{'replan_ms':500,'refresh_rate':'144 fps'}}})
    manager.discover();p=next(p for p in manager.plugins if p.id=='routes')
    assert p.settings['path_refresh']=='2 / second' and p.settings['refresh_rate']=='144 fps'
    assert not p.enabled


def test_isolated_worker_returns_a_route_and_shuts_down():
    planner=RoutePlanner(processes=True)
    try:
        grid=[bytes([5]*15)]*15
        targets=[dict(key=('exit','test'),grid=(12,12))]
        planner.poll('instance',grid,None,(1,1),targets,(4,5),.5)
        owner,results=planner.future.result(timeout=15)
        assert owner=='instance' and results[('exit','test')]['path'][-1]==(12,12)
    finally:planner.close()


def test_known_exit_cache_only_restores_for_the_same_verified_instance():
    p=plugin();p.planner=RoutePlanner(processes=False)
    s=Snapshot(source='live',town=False,area='Area',grid=[bytes([5]*12)]*12,
        terrain_heights=np.zeros((12,12),np.int16),player_grid=(2,2),
        entities=[dict(id=1,kind='exit',name='Next area',grid=(8,8))])
    s.visual_context=dict(key=(1,2,3,4,5,6,999))
    try:
        p.tick(s,object());saved=dict(p.settings)
    finally:p.stop()

    p=plugin();p.settings.update(saved);p.planner=RoutePlanner(processes=False)
    try:
        s.entities=[];s.grid=[bytes([5]*12)]*12
        s.visual_context=dict(key=(1,2,3,4,5,6,1000))
        assert len(p.tick(s,object())[-1].payload['rows'])==1
        s.visual_context=dict(key=(1,2,3,4,5,7,1000));s.grid=[bytes([5]*12)]*12
        assert not p.tick(s,object())[-1].payload['rows']
    finally:p.stop()


def test_route_stability_keeps_small_savings_but_accepts_a_large_improvement():
    grid=[bytearray([5]*30)for _ in range(30)]
    for y in range(5,25):grid[y][10]=0
    old_path=[(9,y)for y in range(6,3,-1)]+[(10,4),(11,4)]+[(11,y)for y in range(5,24)]
    target=dict(key='boss',grid=(11,23),locations=[(11,23)])
    def result(path):
        cells=np.asarray(path,dtype=float)
        return dict(path=path,cells=cells,tail=route_tail_cost(cells),world=world_path(path,None),
                    status='ready',cost=cost(path),target_location=(11,23))
    for start,keep in (((9,7),True),((9,23),False)):
        planner=RoutePlanner(processes=False)
        try:
            planner.reset('area');old=result(old_path);planner.results={'boss':old}
            planner.goals=(('boss',((11,23),)),);planner.start=start;planner.at=time.monotonic()
            candidate=result(route(grid,start,(11,23),walk_values=(4,5)))
            planner.future=Future();planner.future.set_result(('area',{'boss':candidate}))
            selected=planner.poll('area',grid,None,start,[target],(4,5),.2,stability=.12)
            assert (selected['boss'] is old)==keep
        finally:planner.close()


def test_failed_background_candidate_keeps_a_still_walkable_route():
    planner=RoutePlanner(processes=False)
    grid=[bytes([5]*15)]*15
    target=dict(key='exit',grid=(12,12))
    try:
        planner.reset('area')
        _,found=planner.search('area',grid,None,(1,1),[target],(4,5),threading.Event())
        old=found['exit'];planner.results=found
        planner.goals=(('exit',((12,12),)),);planner.start=(2,2);planner.at=time.monotonic()
        planner.future=Future()
        planner.future.set_result(('area',{'exit':dict(path=[],status='limit',cost=None)}))
        result=planner.poll('area',grid,None,(2,2),[target],(4,5),.2,stability=.12)
        assert result['exit'] is old
    finally:planner.close()


def test_encounter_portals_are_not_boss_routes_but_actual_bosses_remain():
    p=plugin()
    s=Snapshot(area='Cells',grid=[bytes([5]*40)]*40,player_grid=(2,2),entities=[
        dict(kind='boss',rarity=3,name='Null Portal',metadata='Metadata/Monsters/TentaclePortal/TentaclePortal1@83',
             grid=(3,3),life=2235804,alive=True,hostile=True,is_map_boss=True),
        dict(kind='boss',rarity=3,name='Translated portal name',metadata='Metadata/Monsters/TentaclePortal/TentaclePortal2@84',
             grid=(4,4),life=100,alive=True,hostile=True,is_map_boss=True),
        dict(kind='boss',rarity=3,name='Null Portal',grid=(5,5),life=100,alive=True,hostile=True,is_map_boss=True),
        dict(kind='boss',rarity=3,name='BeyondPortal1',metadata='Metadata/Monsters/BeyondDemons/BeyondPortal1',
             grid=(6,6),life=100,alive=True,hostile=True,is_map_boss=True),
        dict(kind='boss',rarity=3,name='Actual map boss',metadata='Metadata/Monsters/Test/MapBoss',
             grid=(25,25),life=100,alive=True,hostile=True,is_map_boss=True),
        dict(kind='boss',rarity=3,name='Portal Guardian',metadata='Metadata/Monsters/Test/PortalGuardianBoss',
             grid=(30,30),life=100,alive=True,hostile=True,is_map_boss=True)])
    try:
        assert {t['name']for t in p.targets(s)}=={'Actual map boss','Portal Guardian'}
        assert len(s.entities)==6 and s.entities[0]['life']==2235804
    finally:p.stop()


def test_boss_routes_require_positive_identity_instead_of_unique_rarity():
    p=plugin()
    s=Snapshot(area='Map',grid=[bytes([5]*40)]*40,player_grid=(2,2),entities=[
        dict(kind='boss',rarity=3,name='Legacy unique candidate',grid=(3,3),life=100,hostile=True),
        dict(kind='unique',rarity=3,name='Ordinary unique',grid=(4,4),life=100,hostile=True,is_map_boss=False),
        dict(kind='unique',rarity=3,name='Unreadable identity',grid=(5,5),life=100,hostile=True,is_map_boss=None),
        dict(kind='boss',rarity=3,name='Volatile Core',metadata='Metadata/Monsters/VolatileCore/VolatileCore@83',
             grid=(6,6),life=100,hostile=True,is_map_boss=True),
        dict(kind='boss',rarity=3,name='Verified map boss',grid=(30,30),life=100,hostile=True,is_map_boss=True)])
    try:
        assert [t['name']for t in p.targets(s)]==['Verified map boss']
    finally:p.stop()
