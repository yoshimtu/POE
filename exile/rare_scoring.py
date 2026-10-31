"""Build-coherent affix scoring; references and weights are reviewable heuristics."""
SCORER_VERSION='coherent-affixes-crafting-2026-10-30.1'

BASE = dict(life=1.,life_scaling=.8,defense=.8,resistance=.85,suppression=1.,ailment=.65,
    es=.8,mobility=1.,attack=.5,physical=.5,caster=.5,critical=.45,dot=.5,damage=.45,
    minion_damage=.5,minion_speed=.5,minion_utility=.2,attribute=.4,attribute_scaling=.4,
    mana=.4,recovery=.4,mana_recovery=.4,utility=.7,conditional=.4,loot=.15,neutral=0.)

# A profile needs at least two independent, useful core affixes, including an
# anchor. A single unrelated T1 roll cannot select a specialised build profile.
PROFILES = {
    'Balanced': (set(('life','life_scaling','defense','resistance','suppression','es','mobility','ailment')),set(),{}),
    'Attack': ({'attack','physical','critical','damage'},{'attack','physical'},
        dict(attack=1.1,physical=1.1,critical=1.,damage=.85,caster=.15,dot=.2,minion_damage=.1,minion_speed=.1)),
    'Spell': ({'caster','critical','damage'},{'caster'},
        dict(caster=1.1,critical=1.,damage=.85,attack=.15,physical=.2,minion_damage=.1,minion_speed=.1)),
    'Damage over time': ({'dot','caster','damage'},{'dot'},
        dict(dot=1.15,caster=.85,damage=.85,critical=.1,attack=.2,minion_damage=.1,minion_speed=.1)),
    'Energy shield': ({'es'},{'es'},dict(es=1.15,life=.3,life_scaling=.3)),
    'Minion': ({'minion_damage','minion_speed','minion_utility'},{'minion_damage','minion_speed'},
        dict(minion_damage=1.1,minion_speed=1.1,minion_utility=.85,es=.7,loot=.2,
             attack=.1,physical=.1,caster=.1,critical=.1,dot=.1,damage=.1)),
    'Mana': ({'mana','mana_recovery','caster'},{'mana'},dict(mana=1.1,mana_recovery=.9,caster=.85)),
    'Attribute stacking': ({'attribute','attribute_scaling'},{'attribute_scaling'},
        dict(attribute=1.,attribute_scaling=1.1)),
    'Item find': ({'loot','mobility','life','resistance'},{'loot'},dict(loot=1.)),
}


def role(row):
    if row['category']=='Life':return 'life'
    if row['category']=='Life scaling':return 'life_scaling'
    if row['category']=='Mana regeneration':return 'mana_recovery'
    if row.get('group')=='defense'and 'Energy Shield'in row['mod']:return 'es'
    return row.get('group','neutral')


def score_profile(rows,name):
    core,anchors,overrides=PROFILES[name];weights=dict(BASE,**overrides)
    affixes={};core_affixes={};tiers={};roles=set();mechanisms=set();contributions=[]
    for index,row in enumerate(rows):
        if row['strength']is None:contributions.append(None);continue
        kind=role(row);weight=weights.get(kind,.4);strength=row['strength'];tier=row.get('tier')
        # Rank complements the actual magnitude; it never makes a low-value T1
        # family as strong as a valuable roll. Filler still has zero weight.
        rank={1:1.,2:.85,3:.7,4:.5,5:.35,6:.2}.get(tier,.1)
        quality=.8*strength+.2*rank if tier else strength
        affix=row.get('affix','')or''
        points=quality*weight;key=affix if '"'in affix else f'line:{index}'
        affixes.setdefault(key,[]).append((index,points));contributions.append(points)
        if kind in core and quality>=.4 and weight>=.6:
            core_affixes.setdefault(key,[]).append((kind,quality))
            roles.add(kind)
            mechanisms.add((kind,row['category']))
            if tier in (1,2)and quality>=.8:tiers[key]=tier
    # Hybrid display lines share an affix slot. A second line helps, but is not
    # another independent high-tier affix for the combination bonus.
    for values in affixes.values():
        strongest=max(values,key=lambda entry:entry[1])[0]
        for index,points in values:
            if index!=strongest:contributions[index]=points*.35
    total=sum(points for points in contributions if points is not None)
    count=len(core_affixes);anchor_ok=not anchors or bool(roles&anchors)
    eligible=name=='Balanced'or(count>=2 and anchor_ok)
    coherence=min(1.4,.45*max(0,len(mechanisms)-1)+.2*max(0,count-2))if count>=2 and anchor_ok else 0.
    tier_bonus=min(.8,.25*max(0,len(tiers)-1))if count>=2 and anchor_ok else 0.
    raw_score=1+total*1.45+coherence+tier_bonus
    score=round(min(10.,max(1.,raw_score)),1)
    return dict(score=score,best_fit=name,eligible=eligible,base_points=round(total*1.45,3),
        coherence_bonus=round(coherence,3),tier_bonus=round(tier_bonus,3),
        uncapped_score=round(raw_score,3),
        coherent_affixes=count,strong_tier_affixes=len(tiers),contributions=contributions,roles=sorted(roles))


def score_affixes(rows,preference):
    if preference=='General':
        candidates=[score_profile(rows,name)for name in PROFILES]
        result=max((r for r in candidates if r['eligible']),key=lambda r:(r['score'],r['coherent_affixes']))
    else:result=score_profile(rows,preference if preference in PROFILES else'Balanced')
    result['selection']='Automatic'if preference=='General'else'Selected'
    for row,points in zip(rows,result.pop('contributions')):
        if points is None:continue
        row['contribution']=round(points*1.45,3)
        row['impact']='No score increase'if points==0 else'Small contribution'if points<.35 else'Contributes'
    reasons=[]
    if result['coherence_bonus']:
        roles=', '.join(role.replace('_',' ')for role in result['roles'])
        reasons.append(f"Synergy: {result['coherent_affixes']} complementary {result['best_fit'].lower()} affixes ({roles}; +{result['coherence_bonus']:g})")
    if result['tier_bonus']:
        reasons.append(f"Synergy: {result['strong_tier_affixes']} strong T1/T2 affixes in the same combination (+{result['tier_bonus']:g})")
    return result,reasons
