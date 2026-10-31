import heapq
import math
import random
import threading

import pytest

from exile.native_route import route,library

pytestmark=pytest.mark.skipif(library() is None,reason='Native Windows route library is not built')


def shortest_cost(grid,start,goal,values):
    queue=[(0.,start)];best={start:0.}
    def walk(x,y):return 0<=x<len(grid[0]) and 0<=y<len(grid) and grid[y][x] in values
    while queue:
        cost,(x,y)=heapq.heappop(queue)
        if cost!=best[(x,y)]:continue
        if (x,y)==goal:return cost
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                if not (dx or dy) or not walk(x+dx,y+dy):continue
                if dx and dy and not (walk(x+dx,y)and walk(x,y+dy)):continue
                point=x+dx,y+dy;candidate=cost+math.hypot(dx,dy)
                if candidate<best.get(point,float('inf')):
                    best[point]=candidate;heapq.heappush(queue,(candidate,point))
    return None


def test_compiled_search_matches_independent_shortest_cost_across_random_grids():
    rng=random.Random(20261028)
    for values in ((4,5),(1,2,3,4,5)):
        for _ in range(35):
            grid=[bytearray(rng.choice((0,0,1,2,3,4,5,5,5))for _ in range(12))for _ in range(12)]
            grid[0][0]=grid[-1][-1]=5
            expected=shortest_cost(grid,(0,0),(11,11),values);stats={}
            path=route(grid,(0,0),(11,11),limit=10000,walk_values=values,stats=stats)
            assert stats['engine']=='native'
            assert bool(path)==(expected is not None)
            if path:
                assert path[0]==(0,0) and path[-1]==(11,11)
                assert abs(stats['cost']-expected)<1e-9
                assert abs(sum(math.dist(a,b)for a,b in zip(path,path[1:]))-expected)<1e-9


def test_compiled_search_bounds_budget_cancellation_and_mutable_buffers():
    grid=[bytearray([5]*20)for _ in range(20)];stats={}
    assert not route(grid,(-1,0),(19,19),stats=stats) and stats['status']=='invalid'
    assert not route(grid,(0,0),(19,19),limit=2,stats=stats) and stats['status']=='limit'
    stop=threading.Event();stop.set()
    assert not route(grid,(0,0),(19,19),cancel=stop,stats=stats) and stats['status']=='cancelled'
    assert route(grid,(0,0),(19,19))
    grid[19][19]=0
    assert not route(grid,(0,0),(19,19))
