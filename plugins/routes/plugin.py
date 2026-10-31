import math
import json
from pathlib import Path

from exile.model import Mark, Plugin
from exile.mapview import map_point
from exile.routing import PALETTE, RoutePlanner, project_path, remaining_route, nearest_walkable
from exile.terrain import WORLD_TO_GRID
from exile.destinations import resolve_landmarks,destination_identity
from exile.areas import safe_area


class Routes(Plugin):
    id, name, category = 'routes', 'Route overlay', 'Navigation'
    description = 'Colored ground paths to known exits, bosses and objectives, with a draggable destination legend.'
    requires = {'terrain'}
    defaults = dict(exits=True,bosses=True,waypoints=False,quests=False,objects=False,
                    max_routes=4,line_width=3,opacity=85,path_refresh='5 / second',refresh_rate='120 fps',stability='Balanced',
                    legend=True,legend_font=11,legend_width=230,legend_opacity=85,
                    legend_anchor='Top right',legend_locked=False,legend_position=[],legend_size=[],
                    known_instance=[],known_destinations=[])
    fields = {
        'exits':('Routes to area exits','bool'),
        'bosses':('Routes to map bosses / boss areas','bool'),
        'waypoints':('Routes to waypoints','bool'),
        'quests':('Routes to quest objects','bool'),
        'objects':('Routes to other unused encounter objects','bool'),
        'max_routes':('Maximum simultaneous routes','int',1,6),
        'line_width':('Ground line width (pixels)','int',1,7),
        'opacity':('Ground line opacity %','int',20,100),
        'path_refresh':('Path refresh rate','choice',['1 / second','2 / second','5 / second','10 / second']),
        'refresh_rate':('Drawing frame rate','choice',['60 fps','90 fps','120 fps','144 fps']),
        'stability':('Route stability','choice',['Always shortest','Balanced','Prefer existing route']),
        'legend':('Show destination legend','bool'),
        'legend_font':('Legend text size (pixels)','int',9,16),
        'legend_width':('Legend width (pixels)','int',160,360),
        'legend_opacity':('Legend background opacity %','int',30,100),
        'legend_anchor':('Legend placement','choice',['Top right','Custom position']),
        'legend_locked':('Lock legend position (click through)','bool'),
    }
    settings_groups = {
        'Destinations': ['exits','bosses','waypoints','quests','objects','max_routes'],
        'Ground lines': ['refresh_rate','path_refresh','stability','line_width','opacity'],
        'Legend': ['legend','legend_font','legend_width','legend_opacity','legend_anchor','legend_locked'],
    }

    def __init__(self):
        super().__init__()
        self.planner=None
        self.epoch=None
        self.known={}
        self.colors={}
        self.landmark_epoch=None
        self.landmark_targets=[]
        self.region_map=None
        self.region_goals={}
        definitions=json.loads(Path(__file__).with_name('destinations.json').read_text(encoding='utf-8'))
        self.destination_rules=definitions['areas']
        exclusions=definitions.get('boss_exclusions',{})
        self.boss_excluded_prefixes=tuple(p.casefold()for p in exclusions.get('metadata_prefixes',[]))
        self.boss_excluded_names={destination_identity(n)for n in exclusions.get('names',[])}

    def stop(self):
        if self.planner:self.planner.close()
        self.planner=None
        self.region_map=None;self.region_goals.clear()

    def migrate_settings(self,saved):
        settings=dict(saved.get('routes',{}).get('settings',{}))
        if 'path_refresh' not in settings and 'replan_ms' in settings:
            old=max(.1,float(settings['replan_ms'])/1000)
            hz=min((1,2,5,10),key=lambda n:abs(1/n-old))
            settings['path_refresh']=f'{hz} / second'
        return settings

    def point_region(self,snapshot,point,radius=24):
        regions=snapshot.walkable_regions
        x,y=map(int,point)
        if 0<=y<len(regions) and 0<=x<len(regions[0]) and regions[y,x]:
            return int(regions[y,x])
        key=(x,y,radius)
        if key not in self.region_goals:
            if len(self.region_goals)>=4096:self.region_goals.clear()
            goal=nearest_walkable(snapshot.grid,(x,y),(1,2,3,4,5),radius)
            self.region_goals[key]=int(regions[goal[1],goal[0]])if goal else 0
        return self.region_goals[key]

    def targets(self,snapshot):
        grouped={}
        for entity in snapshot.entities:
            point=entity.get('grid')
            if not point:continue
            kind,category=entity.get('kind'),entity.get('category')
            target_type=None
            if kind=='exit':target_type='exit'
            elif category=='waypoint':target_type='waypoint'
            elif entity.get('is_map_boss') is True and entity.get('hostile') is not False:
                if entity.get('alive') is False or not entity.get('life') or entity['life']<=0:continue
                # Unique rarity also belongs to encounter machinery. Exclude
                # known spawners by asset identity, without altering radar/life.
                metadata=(entity.get('metadata')or'').split('@',1)[0].casefold()
                if metadata.startswith(self.boss_excluded_prefixes):continue
                if destination_identity(entity.get('name')or'') in self.boss_excluded_names:continue
                target_type='boss'
            elif category=='quest' or kind=='quest':target_type='quest'
            elif kind=='valuable' and category!='chest' and entity.get('used') is not True:target_type='object'
            if target_type is None or entity.get('used') is True:continue
            name=entity.get('name') or target_type.title()
            normalized=destination_identity(name)
            # Network addresses can change as the same entrance loads again.
            # Destination names, not transient entity pointers, identify routes.
            identity=(normalized if normalized not in ('area transition','areatransition','exit')
                      else (normalized,round(point[0]/8),round(point[1]/8)))
            key=(target_type,identity)
            if key not in grouped:
                previous=self.known.get(key) if target_type in ('exit','waypoint') else None
                grouped[key]=dict(key=key,type=target_type,name=name,
                                  locations=list(previous['locations']) if previous else [])
            locations=grouped[key]['locations']
            near=next((i for i,p in enumerate(locations) if math.dist(p,point)<=6),None)
            if near is None:locations.append(tuple(point))
            else:locations[near]=tuple(point)
        for key,target in grouped.items():
            if target['type'] in ('exit','waypoint'):self.known[key]=target
        for key,target in self.known.items():grouped.setdefault(key,target)
        landmark_epoch=(snapshot.area_id,id(snapshot.landmarks),id(snapshot.grid))
        if landmark_epoch!=self.landmark_epoch:
            self.landmark_epoch=landmark_epoch
            self.landmark_targets=resolve_landmarks(snapshot.area_id,snapshot.landmarks,snapshot.grid,self.destination_rules)
        for target in self.landmark_targets:
            # Exact current/observed entity locations replace approximate terrain
            # anchors, instead of competing with them as shorter false goals.
            overlapping=any(other['type']==target['type'] and
                any(left-8<=x<=right+8 and top-8<=y<=bottom+8
                    for x,y in other['locations']for left,top,right,bottom in target['bounds'])
                for other in grouped.values())
            if not overlapping:grouped.setdefault(target['key'],target)
        enabled=dict(exit=self.settings['exits'],boss=self.settings['bosses'],waypoint=self.settings['waypoints'],
                     quest=self.settings['quests'],object=self.settings['objects'])
        priority={'exit':0,'boss':1,'quest':2,'waypoint':3,'object':4}
        if self.region_map is not snapshot.walkable_regions:
            self.region_map=snapshot.walkable_regions;self.region_goals.clear()
        player_region=self.point_region(snapshot,snapshot.player_grid,4) if self.region_map is not None else None
        selected=[]
        for target in grouped.values():
            if not enabled[target['type']]:continue
            target=dict(target)
            if player_region is not None:
                target['locations']=[point for point in target['locations']
                    if player_region and self.point_region(snapshot,point)==player_region]
                if not target['locations']:continue
            target['locations']=sorted(target['locations'],key=lambda p:math.dist(snapshot.player_grid,p))[:4]
            target['grid']=target['locations'][0]
            selected.append(target)
        selected.sort(key=lambda t:(priority[t['type']],math.dist(snapshot.player_grid,t['grid']),str(t['key'])))
        return selected[:self.settings['max_routes']]

    def tick(self,snapshot,ctx):
        if safe_area(snapshot):
            if self.planner:self.stop()
            return []
        if not snapshot.player_grid or not snapshot.grid:return []
        epoch=(snapshot.area,id(snapshot.grid),id(snapshot.terrain_heights))
        if epoch!=self.epoch:
            self.epoch=epoch;self.known.clear();self.colors.clear()
            context=getattr(snapshot,'visual_context',None)
            instance=list(context['key'][:6])+[snapshot.area] if context else []
            if instance and instance==self.settings['known_instance']:
                for saved in self.settings['known_destinations'][:32]:
                    if saved.get('type') not in ('exit','waypoint'):continue
                    locations=[tuple(p) for p in saved.get('locations',[])[:8]
                               if len(p)==2 and all(isinstance(v,int)for v in p)
                               and 0<=p[0]<len(snapshot.grid[0]) and 0<=p[1]<len(snapshot.grid)]
                    if not locations:continue
                    normalized=destination_identity(saved['name'])
                    identity=(normalized if normalized not in ('area transition','areatransition','exit')
                              else (normalized,round(locations[0][0]/8),round(locations[0][1]/8)))
                    key=(saved['type'],identity)
                    self.known[key]=dict(key=key,type=saved['type'],name=saved['name'],locations=locations)
            else:self.settings['known_destinations']=[]
            self.settings['known_instance']=instance
        targets=self.targets(snapshot)
        self.settings['known_destinations']=[dict(type=t['type'],name=t['name'],locations=[list(p)for p in t['locations']])for t in self.known.values()]
        keys={t['key'] for t in targets}
        self.colors={k:v for k,v in self.colors.items() if k in keys}
        for t in targets:
            if t['key'] not in self.colors:
                self.colors[t['key']]=next(c for c in PALETTE if c not in self.colors.values())
        if self.planner is None:self.planner=RoutePlanner(processes=snapshot.source=='live')
        player=snapshot.player_grid
        if snapshot.player_world:
            candidate=(int(snapshot.player_world[0]*WORLD_TO_GRID),int(snapshot.player_world[1]*WORLD_TO_GRID))
            if 0<=candidate[0]<len(snapshot.grid[0]) and 0<=candidate[1]<len(snapshot.grid):player=candidate
        # Nonzero collision values are clearance levels, not blocked terrain.
        # Narrow corridors remain valid; diagonal corner cutting stays forbidden.
        values=(1,2,3,4,5) if snapshot.source=='live' else (1,4,5)
        results=self.planner.poll(epoch,snapshot.grid,snapshot.terrain_heights,player,
                                  targets,values,1/int(self.settings['path_refresh'].split()[0]),
                                  {'Always shortest':0.,'Balanced':.12,'Prefer existing route':.25}[self.settings['stability']])
        marks=[];rows=[]
        for target in targets:
            color=self.colors[target['key']]
            result=results.get(target['key'])
            status='Calculating…'
            if result:
                status={'ready':'','unreachable':'No walkable route','limit':'Search limit reached',
                        'no_approach':'No walkable approach','invalid':'No walkable approach'}.get(result['status'],'Calculating…')
                if result['path']:
                    if snapshot.source=='live':
                        diagnostics={}
                        world=remaining_route(result,player,snapshot.grid,values,snapshot.player_world,diagnostics)
                        if world is None:
                            status='Recalculating…'
                            self.planner.request_replan(player)
                            # Keep the already verified path visible while its
                            # start is replaced, without drawing a wall shortcut.
                            world=result['world'][diagnostics.get('index',0):]
                        segments=project_path(world,snapshot.camera) if world is not None and snapshot.terrain_heights is not None else []
                        if snapshot.camera is None or snapshot.terrain_heights is None:status='Ground projection unavailable'
                    else:
                        segments=[[map_point(snapshot,(x+.5,y+.5)) for x,y in result['path']]]
                    for points in segments:
                        if len(points)>1:
                            marks.append(Mark('path',*points[0],color=color,size=self.settings['line_width'],
                                value=self.settings['opacity']/100,points=points,payload={'ground_route':True}))
            prefix={'exit':'Exit','boss':'Boss','waypoint':'Waypoint','quest':'Quest','object':'Object'}[target['type']]
            rows.append(dict(name=f"{prefix} · {target['name']}",color=color,status=status))
        if self.settings['legend']:
            marks.append(Mark('route_legend',0,0,payload=dict(rows=rows,settings=dict(self.settings))))
        return marks


def create_plugin():
    return Routes()
