"""Resolve static destinations from the current instance's terrain assets."""
from fnmatch import fnmatchcase
import math
import re

from exile.routing import nearest_walkable


def destination_identity(name):
    return ' '.join(name.casefold().split()).removeprefix('the ')


def marker_groups(points):
    """Keep physically separate occurrences of a named tile feature separate."""
    remaining=set(map(tuple,points));groups=[]
    while remaining:
        seed=min(remaining);remaining.remove(seed);group=[seed];pending=[seed]
        while pending:
            x,y=pending.pop()
            for dx in (-23,0,23):
                for dy in (-23,0,23):
                    point=x+dx,y+dy
                    if point in remaining:
                        remaining.remove(point);pending.append(point);group.append(point)
        groups.append(group)
    return groups


def approach(points,grid):
    center=tuple(sum(p[axis]for p in points)/len(points)for axis in (0,1))
    # Stay on a matched feature rather than averaging between distant rooms.
    for point in sorted(points,key=lambda p:math.dist(p,center))[:256]:
        found=nearest_walkable(grid,point,(1,2,3,4,5),24)
        if found is not None:return found
    return None


def resolve_landmarks(area_id,landmarks,grid,rules):
    named={};paths={}
    for tile in landmarks:
        if tile.get('name'):named.setdefault(tile['name'].casefold(),[]).append(tile['grid'])
        paths.setdefault(tile['path'].casefold(),[]).append(tile['grid'])
    selected=[];claimed=set()
    entries=[entry for pattern,rows in rules.items() if fnmatchcase(area_id,pattern)for entry in rows]
    for entry in entries:
        marker=entry['tile'].casefold()
        source=paths if marker.startswith('metadata/') else named
        matched={key:points for key,points in source.items() if fnmatchcase(key,marker)}
        points=[p for positions in matched.values()for p in positions]
        if not points:continue
        claimed.update(matched)
        if source is paths:
            claimed.update(tile['name'].casefold()for tile in landmarks if tile['path'].casefold() in matched)
        groups=marker_groups(points)
        # A feature may contain detached pieces. An explicit one-location rule
        # uses the largest component, never an average across separate exits.
        count=max(1,min(12,entry.get('count',1)))
        groups=sorted(groups,key=lambda group:(-len(group),min(group)))[:count]
        locations=[p for group in groups if (p:=approach(group,grid)) is not None]
        bounds=[(min(x for x,y in group),min(y for x,y in group),max(x for x,y in group)+23,max(y for x,y in group)+23)for group in groups]
        if locations:selected.append(dict(type=entry['kind'],name=entry['label'],locations=locations,bounds=bounds))
    # Map terrain often reuses campaign transition names that do not say
    # "exit" or "arena". Discover dedicated transition tiles without needing
    # their network entity to stream in. Never infer a boss from decoration.
    if area_id.casefold().startswith('map'):
        number=0
        for path,points in sorted(paths.items()):
            if path in claimed or '/transitions/' not in path:continue
            for group in marker_groups(points)[:12]:
                point=approach(group,grid)
                if point is None:continue
                left,top=min(x for x,y in group),min(y for x,y in group)
                right,bottom=max(x for x,y in group)+23,max(y for x,y in group)+23
                if any(any(a-8<=point[0]<=c+8 and b-8<=point[1]<=d+8 for a,b,c,d in target['bounds'])for target in selected):continue
                number+=1
                selected.append(dict(type='exit',name=f'Area transition {number} (approximate)',
                    locations=[point],bounds=[(left,top,right,bottom)]))
            claimed.update(tile['name'].casefold()for tile in landmarks if tile['path'].casefold()==path)
    # Conservative generic markers cover unfamiliar layouts without inventing
    # named destinations from decoration/terrain paths.
    for name,points in named.items():
        if name in claimed:continue
        kind=None;label=None
        if name=='waypoint':kind,label='waypoint','Waypoint'
        elif name=='boss_arena' or re.fullmatch(r'(?:boss|arena)(?:_?(?:area|entrance|transition|room|door|gate))?_?\d*',name):
            kind,label='boss','Boss area'
        elif re.fullmatch(r'(?:exit|entrance|transition|areatransition)(?:up|down|left|right|_?\d+)?',name):
            kind,label='exit','Area exit'
        if kind:
            for number,group in enumerate(marker_groups(points)[:12],1):
                point=approach(group,grid)
                bounds=[(min(x for x,y in group),min(y for x,y in group),max(x for x,y in group)+23,max(y for x,y in group)+23)]
                if point is not None:selected.append(dict(type=kind,name=f'{label} ({name} {number})',locations=[point],bounds=bounds))
    result={}
    for item in selected:
        key=item['type'],destination_identity(item['name'])
        if key in result:
            result[key]['locations'].extend(item['locations']);result[key]['bounds'].extend(item['bounds'])
        else:result[key]=dict(item,key=key,grid=item['locations'][0],approximate=True)
    return list(result.values())
