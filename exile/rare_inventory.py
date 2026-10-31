"""Build conservative assessment rows from known modifier definitions and exact rolls.

The bundled catalog derives from https://repoe-fork.github.io/mods.min.json (PoE 3.29.3.3).
"""
import re
import json,zlib
from functools import lru_cache
from exile.storage import resource_root

@lru_cache(maxsize=1)
def catalog():
    return json.loads(zlib.decompress((resource_root()/'assets'/'rare_mod_catalog.json.z').read_bytes()))

_RANGE=re.compile(r'\((-?\d+)\s*-\s*(-?\d+)\)')

@lru_cache(maxsize=1)
def modifier_index():
    result={}
    for ident,entry in catalog()['mods'].items():
        kind,name,text,ranges,groups,stats,weights,level,domain=entry
        if domain!='item' or kind not in ('prefix','suffix') or not weights:continue
        for group in groups:result.setdefault((kind,group,tuple(stats)),[]).append((ident,weights,level))
    return result

@lru_cache(maxsize=4096)
def modifier_tier(ident,metadata):
    data=catalog();entry=data['mods'].get(ident);tags=data['bases'].get(metadata)
    if not entry or not tags:return None
    kind,name,text,ranges,groups,stats,weights,level,domain=entry
    if domain!='item' or kind not in ('prefix','suffix') or len(groups)!=1:return None
    candidates=modifier_index().get((kind,groups[0],tuple(stats)),[])
    tagset=set(tags)
    eligible=[]
    for candidate,weight_rows,required in candidates:
        weight=next((weight for tag,weight in weight_rows if tag in tagset or tag=='default'),0)
        if weight>0:eligible.append((candidate,required))
    if not any(candidate==ident for candidate,required in eligible):return None
    levels=sorted({required for candidate,required in eligible},reverse=True)
    # Multiple distinct mods at the same rank may represent incompatible
    # tiers; leave the rank unknown rather than invent one.
    if sum(required==level for candidate,required in eligible)!=1:return None
    return levels.index(level)+1

def assessment_rows(records,metadata=''):
    rows=[]
    for record in records:
        ident=record.get('id','');values=record.get('values',[]);entry=catalog()['mods'].get(ident)
        if not entry:return None
        kind,name,text,ranges=entry[:4]
        if not 1<=len(values)==len(ranges)<=4:return None
        if any(not isinstance(v,int) or not lo<=v<=hi for v,(lo,hi) in zip(values,ranges)):return None
        from itertools import combinations
        tokens=list(re.finditer(r'\((-?\d+)\s*-\s*(-?\d+)\)|(?<![A-Za-z0-9])-?\d+',text))
        if len(tokens)>len(values):return None
        candidates=set()
        for selected in combinations(range(len(values)),len(tokens)):
            if any(tuple(ranges[i])!=(1,1) for i in range(len(values)) if i not in selected):continue
            pieces=[];last=0;valid=True
            for match,index in zip(tokens,selected):
                value=values[index]
                if match.group(1) is not None:
                    a,b=map(int,match.groups())
                    displayed=abs(value) if value<0 and min(a,b)>=0 else value
                    if not min(a,b)<=displayed<=max(a,b):valid=False;break
                    replacement=str(displayed)
                else:
                    if abs(int(match.group()))!=abs(value):valid=False;break
                    replacement=match.group()
                pieces.extend((text[last:match.start()],replacement));last=match.end()
            if valid:candidates.add(''.join(pieces)+text[last:])
        if len(candidates)!=1:return None
        display=candidates.pop()
        if not display.strip():return None
        section=record.get('section')
        label='Implicit' if section=='implicit' else ('Prefix' if kind=='prefix' else 'Suffix' if kind=='suffix' else '')
        if not label:return None
        tier=modifier_tier(ident,metadata) if section=='explicit' else None
        rank=(' (Tier: '+str(tier)+')') if tier else ''
        rows.append(label+' Modifier "'+ident+'"'+rank+'\n'+display)
    return rows if rows else None


from functools import lru_cache

@lru_cache(maxsize=512)
def inventory_rating(name,base,metadata,links,sockets,records,archetype):
    from exile.hover_assessment import assess_data
    rows=assessment_rows([dict(id=ident,section=section,values=list(values)) for ident,section,values in records],metadata)
    if not rows:return None
    try:
        item,result=assess_data(dict(name=name,base=base,metadata=metadata,links=links,sockets=sockets,tooltip_rows=rows),archetype)
        if result.get('score') is None:return None
        return result['score']
    except (ValueError,TypeError,KeyError):return None

def rating_for_item(item,archetype):
    if item.get('rarity')!=2 or item.get('identified') is not True:return None
    records=item.get('assessment_mods')
    if not records:return None
    try:
        key=tuple((r['id'],r['section'],tuple(r['values'])) for r in records)
        return inventory_rating(item['name'],item['base'],item['metadata'],item.get('links',0),item.get('sockets',0),key,archetype)
    except (KeyError,TypeError,ValueError,OSError):return None
