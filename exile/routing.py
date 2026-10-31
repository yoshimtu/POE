"""Asynchronous shortest-grid routes and terrain-aware world projection."""
from concurrent.futures import ThreadPoolExecutor,ProcessPoolExecutor
import multiprocessing
import math
import threading
import time

import numpy as np

from exile.navigation import route
from exile.terrain import HEIGHT_UNIT, WORLD_TO_GRID

PALETTE=('#68b4ff','#c493ed','#f0ce68','#78d0b2','#ee986f','#ee859f')

_worker_grid=_worker_heights=_worker_cancel=None


def initialize_worker(grid,heights,cancel):
    global _worker_grid,_worker_heights,_worker_cancel
    _worker_grid,_worker_heights,_worker_cancel=grid,heights,cancel


def search_worker(key,start,targets,values):
    from exile.native_route import route as compiled_route,library
    return RoutePlanner.search(key,_worker_grid,_worker_heights,start,targets,values,_worker_cancel,
                               engine=compiled_route if library() is not None else None)


def nearest_walkable(grid, point, values, radius=24):
    x,y=map(int,point)
    width,height=len(grid[0]),len(grid)
    candidates=[]
    for dy in range(-radius,radius+1):
        for dx in range(-radius,radius+1):
            nx,ny=x+dx,y+dy
            if 0<=nx<width and 0<=ny<height and grid[ny][nx] in values:
                candidates.append((dx*dx+dy*dy,nx,ny))
    if not candidates:return None
    _,x,y=min(candidates)
    return x,y


def clear_segment(grid,start,end,values):
    """Supercover sampling with explicit diagonal corner checks."""
    x0,y0=start;x1,y1=end
    steps=max(1,math.ceil(max(abs(x1-x0),abs(y1-y0))*2))
    previous=None
    for i in range(steps+1):
        x,y=math.floor(x0+(x1-x0)*i/steps),math.floor(y0+(y1-y0)*i/steps)
        if not 0<=y<len(grid) or not 0<=x<len(grid[0]) or grid[y][x] not in values:return False
        if previous and x!=previous[0] and y!=previous[1]:
            if grid[y][previous[0]] not in values or grid[previous[1]][x] not in values:return False
        previous=x,y
    return True


def world_path(path,heights):
    cells=np.asarray(path,dtype=np.int32)
    output=np.empty((len(cells),3),dtype=np.float64)
    output[:,:2]=(cells+.5)/WORLD_TO_GRID
    output[:,2]=heights[cells[:,1],cells[:,0]]*HEIGHT_UNIT if heights is not None else 0
    output.flags.writeable=False
    return output


def route_tail_cost(cells):
    if len(cells)<2:return np.zeros(len(cells))
    difference=np.diff(cells,axis=0)
    length=np.hypot(difference[:,0],difference[:,1])
    return np.r_[np.cumsum(length[::-1])[::-1],0.]


def join_index(result,start,grid,values):
    cells=result['cells']
    if not len(cells):return None,0,0
    distances=(cells[:,0]-start[0])**2+(cells[:,1]-start[1])**2
    closest=int(np.argmin(distances))
    candidates=np.flatnonzero(distances<=400)
    candidates=candidates[np.argsort(distances[candidates])]
    for index in candidates[:128]:
        distance=math.sqrt(distances[index]);point=result['path'][index]
        connector_values=tuple(range(1,6)) if grid[start[1]][start[0]] not in values and distance<=4 else values
        if clear_segment(grid,(start[0]+.5,start[1]+.5),(point[0]+.5,point[1]+.5),connector_values):
            return int(index),closest,math.sqrt(distances[closest])
    return None,closest,math.sqrt(distances[closest])


def clip_segment(a,b,width,height):
    x,y=a;dx,dy=b[0]-x,b[1]-y
    low,high=0.,1.
    for p,q in ((-dx,x),(dx,width-x),(-dy,y),(dy,height-y)):
        if abs(p)<1e-12:
            if q<0:return None
        elif p<0:low=max(low,q/p)
        else:high=min(high,q/p)
        if low>high:return None
    return ((x+low*dx,y+low*dy),(x+high*dx,y+high*dy))


def project_path(world,camera):
    if len(world)<2 or not camera:return []
    matrix=np.asarray(camera['matrix'],dtype=np.float64).reshape(4,4)
    width,height=camera['viewport']
    clip=np.column_stack([world[:,0]*matrix[0,i]+world[:,1]*matrix[1,i]+world[:,2]*matrix[2,i]+matrix[3,i] for i in range(4)])
    valid=np.isfinite(clip).all(axis=1)&(clip[:,3]>.01)
    safe=np.where(valid,clip[:,3],1)
    x=(1+clip[:,0]/safe)*width/2;y=(1-clip[:,1]/safe)*height/2
    keep=(valid[:-1]&valid[1:] & ~((x[:-1]<0)&(x[1:]<0)) & ~((x[:-1]>width)&(x[1:]>width))
          & ~((y[:-1]<0)&(y[1:]<0)) & ~((y[:-1]>height)&(y[1:]>height)))
    segments=[]
    for i in np.flatnonzero(keep):
        clipped=clip_segment((x[i],y[i]),(x[i+1],y[i+1]),width,height)
        if clipped is None:continue
        a,b=clipped
        if segments and math.dist(segments[-1][-1],a)<1e-5:segments[-1].append(b)
        else:segments.append([a,b])
    return segments


class RoutePlanner:
    def __init__(self,processes=True):
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='route-search')
        self.processes=processes
        self.context=multiprocessing.get_context('spawn') if processes else None
        self.process_pool=None
        self.process_key=None
        self.engine_lock=threading.Lock()
        self.future=None
        self.cancel=self.context.Event() if processes else threading.Event()
        self.key=None
        self.results={}
        self.at=0
        self.start=None
        self.goals=None
        self.force=False

    def reset(self,key):
        self.cancel.set()
        self.cancel=self.context.Event() if self.processes else threading.Event()
        with self.engine_lock:
            old=self.process_pool;self.process_pool=None;self.process_key=None
        if old:old.shutdown(wait=False,cancel_futures=True)
        self.key=key
        self.results={}
        self.at=0
        self.start=self.goals=None
        self.force=False

    def request_replan(self,start):
        if self.future is None or self.start is None or math.dist(start,self.start)>1:
            self.force=True

    def execute_search(self,key,grid,heights,start,targets,values,cancel):
        if not self.processes:return self.search(key,grid,heights,start,targets,values,cancel)
        if cancel.is_set():return key,{}
        with self.engine_lock:
            if cancel.is_set():return key,{}
            if self.process_pool is None:
                self.process_pool=ProcessPoolExecutor(max_workers=1,mp_context=self.context,
                    initializer=initialize_worker,initargs=(grid,heights,cancel))
                self.process_key=key
            engine=self.process_pool
        try:
            return engine.submit(search_worker,key,start,targets,values).result()
        except Exception:
            if cancel.is_set():return key,{}
            raise

    @staticmethod
    def search(key,grid,heights,start,targets,values,cancel,engine=None):
        found={}
        origin=nearest_walkable(grid,start,values,4)
        for target in targets:
            if cancel.is_set():break
            best=None;status='no_approach';budget=2_000_000 if engine else 500_000;seen=set()
            for location in target.get('locations',[target['grid']]):
                goal=nearest_walkable(grid,location,values)
                if not origin or not goal or goal in seen:continue
                seen.add(goal)
                if best and math.dist(origin,goal)>=best['cost']:continue
                stats={}
                path=(engine or route)(grid,origin,goal,limit=budget,walk_values=values,cancel=cancel,stats=stats)
                status=stats.get('status','no_approach');budget-=stats.get('visited',0)
                if path and (best is None or stats['cost']<best['cost']):
                    cells=np.asarray(path,dtype=np.float64)
                    best=dict(path=path,cells=cells,world=world_path(path,heights),tail=route_tail_cost(cells),
                              status='ready',cost=stats['cost'],target_location=tuple(location),engine=stats.get('engine','python'))
                if cancel.is_set() or budget<=0:break
            found[target['key']]=best or dict(path=[],world=None,status=status,cost=None)
        return key,found

    def poll(self,key,grid,heights,start,targets,values,interval,stability=0.):
        if key!=self.key:self.reset(key)
        if self.future is not None and self.future.done():
            try:
                owner,results=self.future.result()
                if owner==self.key:
                    for target_key,candidate in results.items():
                        old=self.results.get(target_key)
                        target=next((t for t in targets if t['key']==target_key),None)
                        retain=False
                        if stability and old and old.get('path') and target:
                            locations=target.get('locations',[target['grid']])
                            same_goal=min(math.dist(old.get('target_location',old['path'][-1]),p) for p in locations)<=2
                            index,_,_=join_index(old,start,grid,values)
                            if same_goal and index is not None:
                                previous_cost=float(old['tail'][index])+math.dist(start,old['path'][index])
                                candidate_index,_,_=join_index(candidate,start,grid,values) if candidate.get('path') else (None,0,0)
                                # Compare both paths from the current position, rather
                                # than the position where the background job started.
                                if candidate_index is None:retain=True
                                else:
                                    candidate_cost=float(candidate['tail'][candidate_index])+math.dist(start,candidate['path'][candidate_index])
                                    saving=previous_cost-candidate_cost
                                    retain=saving<max(12. if stability>=.2 else 8.,previous_cost*stability)
                        if not retain:self.results[target_key]=candidate
            finally:self.future=None
        goals=tuple((t['key'],tuple(sorted(t.get('locations',[t['grid']]))))for t in targets)
        moved=self.start is None or tuple(start)!=self.start
        changed=goals!=self.goals
        urgent=self.goals is None or {g[0] for g in goals}!={g[0] for g in self.goals}
        now=time.monotonic()
        # Staying in the existing corridor updates the drawn lead-in locally,
        # rather than queuing another end-to-end search for each cell moved.
        corridor=12 if stability>=.2 else 6
        following=bool(stability and not changed and targets and all(
            self.results.get(t['key'],{}).get('path') and
            np.min(np.sum((self.results[t['key']]['cells']-start)**2,axis=1))<=corridor*corridor
            for t in targets))
        periodic=bool(following and moved and now-self.at>=(4. if stability>=.2 else 2.))
        if self.future is None and targets and (self.force or urgent or ((changed or (moved and not following) or periodic) and now-self.at>=interval)):
            self.force=False
            self.start,self.goals,self.at=tuple(start),goals,now
            self.future=self.pool.submit(self.execute_search,key,grid,heights,tuple(start),targets,values,self.cancel)
        active={t['key']for t in targets}
        self.results={k:v for k,v in self.results.items() if k in active}
        return self.results

    def close(self):
        self.cancel.set()
        with self.engine_lock:
            engine=self.process_pool;self.process_pool=None
        if engine:engine.shutdown(wait=False,cancel_futures=True)
        if self.future:self.future.cancel()
        self.pool.shutdown(wait=False,cancel_futures=True)


def remaining_route(result,start,grid,values,player_world=None,diagnostics=None):
    path=result['path']
    if not path:return None
    # Use a local connection only when it is also walkable. The search will
    # replace an old path after a deviation; never draw a shortcut through walls.
    index,closest,distance=join_index(result,start,grid,values)
    if diagnostics is not None:diagnostics.update(index=index if index is not None else closest,distance=distance)
    if index is None:
        return None
    world=result['world'][index:]
    if player_world is not None:
        world=np.vstack((np.asarray(player_world,dtype=float),world))
    return world


def check_worker(destination):
    """Exercise the real spawned worker, including in the frozen Windows app."""
    import json
    from pathlib import Path
    planner=RoutePlanner(processes=True)
    started=time.monotonic()
    try:
        grid=[bytearray([5]*24)for _ in range(24)]
        for y in range(20):grid[y][12]=0
        target=dict(key='exit',grid=(20,2))
        planner.poll('check',grid,None,(2,2),[target],(4,5),.2)
        owner,results=planner.future.result(timeout=20)
        result=results['exit']
        assert owner=='check' and result['path'][-1]==(20,2)
        assert all(grid[y][x]==5 for x,y in result['path'])
        import sys
        if getattr(sys,'frozen',False):assert result['engine']=='native'
        report=dict(ok=True,elapsed_ms=(time.monotonic()-started)*1000,
                    cells=len(result['path']),cost=result['cost'],engine=result['engine'])
    except Exception as exc:
        report=dict(ok=False,error=str(exc))
    finally:planner.close()
    Path(destination).write_text(json.dumps(report,indent=2),encoding='utf-8')
    if not report['ok']:raise SystemExit(1)
