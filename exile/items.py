from __future__ import annotations

from dataclasses import dataclass, field
import re


@dataclass
class Item:
    rarity: str
    name: str
    base: str
    item_class: str
    mods: list[str] = field(default_factory=list)
    links: int = 0
    corrupted: bool = False
    unidentified: bool = False
    special_mods: list[dict] = field(default_factory=list)
    mod_info: dict = field(default_factory=dict)
    sockets: int = 0
    properties: dict = field(default_factory=dict)
    mod_details: list[dict] = field(default_factory=list)


EQUIPMENT_CLASSES={'Body Armours','Helmets','Boots','Gloves','Shields','Rings','Amulets','Belts','Quivers',
    'Jewels','Abyss Jewels','Wands','Staves','Warstaves','Bows','Claws','Daggers','Rune Daggers',
    'Swords','Axes','Maces','Sceptres','One Hand Swords','Thrusting One Hand Swords','Two Hand Swords',
    'One Hand Axes','Two Hand Axes','One Hand Maces','Two Hand Maces'}

def equipment_metadata(metadata):
    return str(metadata).startswith(tuple('Metadata/Items/'+p+'/'for p in ('Armours','Weapons','Rings','Amulets','Belts','Quivers','Jewels')))and 'JewelPassiveTreeExpansion'not in str(metadata)


def parse_item(text: str) -> Item:
    text = text.replace("\r", "").replace('\u00a0', ' ').replace('\u2212', '-').strip()
    sections = re.split(r"\n-{4,}\n", text)
    header = sections[0].splitlines()
    rarity = next((line.split(":", 1)[1].strip() for line in header
                   if line.startswith("Rarity:")), "")
    if not rarity:
        raise ValueError("Copy an English item tooltip with Ctrl+C while hovering an item.")
    index = next(i for i, line in enumerate(header) if line.startswith("Rarity:"))
    names = [line.strip() for line in header[index + 1:] if line.strip()]
    if not names:
        raise ValueError("Item name is missing.")
    item_class = next((line.split(":", 1)[1].strip() for line in header
                       if line.startswith("Item Class:")), "Unknown")
    mods, special_mods, mod_info,mod_details = [], [], {},[]
    # Plain Ctrl+C separates properties, requirements and modifiers into blocks.
    # Advanced Ctrl+Alt+C adds affix annotations; skip those annotations.
    skip = ("Item Level:", "Requirements:", "Level:", "Quality", "Sockets:", "Intangibility:", "Str:", "Dex:", "Int:",
            "Armour:", "Evasion Rating:", "Energy Shield:", "Physical Damage:",
            "Elemental Damage:", "Critical Strike Chance:", "Attacks per Second:",
            "Link Count:", "Socket Count:", "Weapon Range:", "Requires ", "Stack Size:", "Limited to:", "Radius:")
    affix_id=0
    for section in sections[1:]:
        annotation = {}
        for line in section.splitlines():
            line = line.strip()
            if line.startswith('{'):
                affix_id+=1
                tier = re.search(r'Tier:\s*(\d+)', line)
                annotation = {'tier': int(tier[1]) if tier else None,'affix_id':affix_id,
                              'affix': line, 'crafted': 'Crafted' in line,
                              'source': 'Implicit' if 'Implicit Modifier' in line else 'Enchant' if 'Enchant'in line else 'Explicit'}
                continue
            # Advanced copy places roll ranges immediately after the actual roll.
            # Keep the rolled value; annotations are not modifier text.
            rolled=re.search(r'([-+]?\d+(?:\.\d+)?)\((\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)\)',line)
            if rolled:
                actual,low,high=map(float,rolled.groups())
                annotation=dict(annotation,roll_position=max(0.,min(1.,(actual-low)/(high-low)))if high>low else 1.)
            line = re.sub(r'(?<=\d)\([-+\d.,]+(?:\s*(?:to|–|-)\s*[-+\d.,]+)?\)', '', line)
            if not line or line.startswith(skip) or line.startswith(("{", "(")):
                continue
            if line in ("Corrupted", "Unidentified", "Mirrored", "Split", "Fractured Item", "Synthesised Item"):
                continue
            if "(implicit)" in line or "(enchant)" in line or annotation.get('source') in ('Implicit','Enchant'):
                source = 'Enchant' if '(enchant)' in line or annotation.get('source')=='Enchant' else 'Implicit'
                line = line.replace('(implicit)', '').replace('(enchant)', '').strip()
                if re.search(r'\d', line)or annotation:
                    special_mods.append({'mod': line, 'source': source})
                continue
            if re.search(r"\d", line)or annotation:
                mods.append(line)
                mod_info[line] = dict(annotation)
                mod_details.append(dict(annotation))
    socket_line = next((line for line in text.splitlines() if line.startswith("Sockets:")), "")
    links = max((len(group.split("-")) for group in socket_line[8:].split()), default=0)
    item=Item(rarity, names[0], names[-1], item_class, mods, links,
                bool(re.search(r"^Corrupted$", text, re.M)),
                bool(re.search(r"^Unidentified$", text, re.M)), special_mods, mod_info)
    item.sockets=len(re.findall(r'\b[RGBWAD]\b',socket_line[8:]))
    if not socket_line:
        links=re.search(r'^Link Count: (\d+)$',text,re.M);sockets=re.search(r'^Socket Count: (\d+)$',text,re.M)
        if links:item.links=int(links[1])
        if sockets:item.sockets=int(sockets[1])
    item.mod_details=mod_details
    item.properties={line.split(':',1)[0]:line.split(':',1)[1].strip()for line in text.splitlines()
                     if ':'in line and line.startswith(skip)}
    if re.search(r'^Mirrored$',text,re.M):item.properties['Mirrored']='true'
    return item


def item_from_hover(data: dict) -> Item:
    """Convert the item-owned native tooltip to the same assessment model."""
    metadata=data.get('metadata','')
    if not equipment_metadata(metadata):raise ValueError('Rare assessment supports equipment only.')
    classes=(('BodyArmours','Body Armours'),('Helmets','Helmets'),('Boots','Boots'),('Gloves','Gloves'),
             ('Shields','Shields'),('Rings','Rings'),('Amulets','Amulets'),('Belts','Belts'),
             ('Quivers','Quivers'),('Jewels','Jewels'),('Maps','Maps'),('Wands','Wands'),
             ('Staves','Staves'),('Bows','Bows'),('Claws','Claws'),('Daggers','Daggers'),
             ('Swords','Swords'),('Axes','Axes'),('Maces','Maces'),('Sceptres','Sceptres'))
    item_class=next((label for path,label in classes if any(part.endswith(path)for part in metadata.split('/'))),'Equipment')
    if 'JewelAbyss'in metadata:item_class='Abyss Jewels'
    if 'JewelPassiveTreeExpansion'in metadata:item_class='Cluster Jewels'
    rows=data.get('tooltip_rows',[])
    advanced=[row for row in rows if re.search(r'(?:Prefix|Suffix|Implicit|Enchant|Crafted).*Modifier',row)]
    mods=[]
    if advanced:
        for row in advanced:
            lines=row.splitlines()
            mods.append('{ '+lines[0]+' }\n'+'\n'.join(lines[1:]))
    else:
        # The main explicit block is multiline; properties/requirements and
        # the item-name header are filtered by the shared parser.
        mods=[row for row in rows if row!=data['name']+'\n'+data['base'] and
              ('\n'in row or re.match(r'(?:[+\-\d]|Adds |Minions |Socketed |Gain |Regenerate |Cannot |Hits )',row))]
    properties=[];seen_properties=set()
    for row in rows:
        if row.startswith(('Armour:','Evasion Rating:','Energy Shield:','Physical Damage:','Elemental Damage:',
                          'Attacks per Second:','Critical Strike Chance:','Item Level:','Unidentified','Corrupted','Mirrored')):
            key=row.split(':',1)[0]
            if key not in seen_properties:properties.append(row);seen_properties.add(key)
    text=f"Item Class: {item_class}\nRarity: Rare\n{data['name']}\n{data['base']}\n--------\n"
    text+='\n--------\n'.join(properties+mods)
    item=parse_item(text);item.links=data.get('links',0);item.sockets=data.get('sockets',0)
    if advanced:
        # Advanced annotations show the unscaled base roll; the ordinary block
        # shows item-quality-adjusted values. Keep tiers/ranges from the former
        # and score the actual displayed modifiers from the latter.
        normal=[row for row in rows if '\n'in row and not re.search(r'(?:Prefix|Suffix|Implicit|Enchant|Crafted).*Modifier',row)]
        ordinary=parse_item(f"Item Class: {item_class}\nRarity: Rare\n{data['name']}\n{data['base']}\n--------\n"+'\n--------\n'.join(normal))
        signature=lambda value:re.sub(r'[-+]?\d+(?:\.\d+)?','#',value).casefold()
        displayed={signature(mod):mod for mod in ordinary.mods}
        from collections import Counter
        occurrences=Counter(signature(mod)for mod in item.mods)
        updated=[];info={}
        for index,mod in enumerate(item.mods):
            # A displayed line can combine two different affixes. Never assign
            # that combined total to each one and count the value twice.
            actual=displayed.get(signature(mod),mod)if occurrences[signature(mod)]==1 else mod
            updated.append(actual);info[actual]=item.mod_details[index]
        item.mods=updated;item.mod_info=info
    return item


# A transparent equipment heuristic, not a learned market-price model or a
# substitute for item-specific tier data. Rules intentionally live in one file.
RULES = [
    (r'Bow Attacks fire (\d+) additional Arrows', 'Additional arrows', 2, 'attack'),
    (r'Gain (\d+)% of Physical Damage as Extra (?:Fire|Cold|Lightning|Chaos) Damage', 'Physical as extra damage', 20, 'damage'),
    (r'\+(\d+) to [Mm]aximum number of Curses', 'Additional curse', 1, 'utility'),
    (r'(\d+)% increased Cooldown Recovery Rate', 'Cooldown recovery', 20, 'utility'),
    (r'(\d+)% of Damage taken Recouped as Life', 'Life recoup', 20, 'recovery'),
    (r'(\d+)% increased effect of Non-Curse Auras from your Skills', 'Aura effect', 20, 'utility'),
    (r'Minions deal (\d+)% increased Damage if you\'ve used a Minion Skill Recently', 'Conditional minion damage', 20, 'minion_damage'),
    (r'Minions have (\d+)% chance to (?:Taunt|Blind) on Hit with Attacks', 'Minion utility', 8, 'minion_utility'),
    (r'\+(\d+)% to Critical Strike Multiplier (?:with|while|for) .+', 'Conditional critical multiplier', 18, 'critical'),
    (r'(\d+)% increased (?:Attack|Cast) Speed (?:with|while|if) .+', 'Conditional speed', 8, 'conditional'),
    (r'(\d+)% increased Damage (?:with|while|if) .+', 'Conditional damage', 20, 'conditional'),
    (r'(\d+)% increased Stun and Block Recovery', 'Stun recovery', 30, 'neutral'),
    (r'\+(\d+)% to (?:Global )?Damage over Time Multiplier', 'DoT multiplier', 26, 'dot'),
    (r'(\d+)% increased (?:Strength|Dexterity|Intelligence|Attributes)', 'Attribute scaling', 12, 'attribute_scaling'),
    (r'(\d+)% increased (?:Flask Effect Duration|Flask Charges gained)', 'Flask utility', 40, 'utility'),
    (r'(\d+)% reduced Mana Cost of Skills', 'Mana cost reduction', 10, 'utility'),
    (r'(?:Non-Channelling Skills have |Channelling Skills have )?-(\d+) to Total Mana Cost', 'Flat mana cost reduction', 7, 'utility'),
    (r'\+(\d+)% to Global Critical Strike Multiplier', 'Critical multiplier', 38, 'critical'),
    (r'(\d+)% chance to Avoid Elemental Ailments', 'Ailment avoidance', 35, 'ailment'),
    (r'(\d+)% chance to Suppress Spell Damage', 'Spell suppression', 22, 'suppression'),
    (r'Minions deal (\d+)% increased Damage', 'Minion damage', 42, 'minion_damage'),
    (r'Minions have (\d+)% increased Attack and Cast Speed', 'Minion attack & cast speed', 16, 'minion_speed'),
    (r'Minions have (\d+)% increased (?:Attack|Cast) Speed', 'Minion speed', 16, 'minion_speed'),
    (r'Minions have (\d+)% increased Movement Speed', 'Minion movement speed', 30, 'minion_utility'),
    (r'Minions have (\d+)% increased maximum Life', 'Minion life', 35, 'minion_utility'),
    (r'Minions have \+(\d+)% to all Elemental Resistances', 'Minion resistances', 15, 'minion_utility'),
    (r'(\d+)% increased Rarity of Items found', 'Item rarity', 28, 'loot'),
    (r'\+(\d+)% to (?:Fire|Cold|Lightning) and Chaos Resistances', 'Elemental & chaos resistance', 20, 'resistance'),
    (r"\+(\d+) to maximum Life", "Life", 120, "defense"),
    (r"\+(\d+)% to (?:Fire|Cold|Lightning) Resistance", "Elemental resistance", 48, "resistance"),
    (r"\+(\d+)% to Chaos Resistance", "Chaos resistance", 35, "resistance"),
    (r"\+(\d+)% to all Elemental Resistances", "All elemental resistances", 16, "resistance"),
    (r"(\d+)% increased Movement Speed", "Movement speed", 35, "mobility"),
    (r"(\d+)% increased Attack Speed", "Attack speed", 27, "attack"),
    (r"(\d+)% increased Cast Speed", "Cast speed", 32, "caster"),
    (r"(\d+)% increased Spell Damage", "Spell damage", 100, "caster"),
    (r"(\d+)% increased Physical Damage", "Physical damage", 170, "physical"),
    (r"\+(\d+)% to (?:Global )?Critical Strike Multiplier", "Critical multiplier", 38, "critical"),
    (r"\+(\d+) to Level of all .*Skill Gems", "Gem levels", 2, "caster"),
    (r"\+(\d+)% to .*Damage over Time Multiplier", "DoT multiplier", 26, "dot"),
    (r"(\d+)% increased maximum Energy Shield", "Energy shield scaling", 100, "es"),
    (r"\+(\d+) to maximum Energy Shield", "Flat energy shield", 100, "es"),
    (r"\+(\d+) to (?:Strength|Dexterity|Intelligence)", "Attribute", 55, "attribute"),
    (r"(\d+)% increased Mana Reservation Efficiency", "Reservation efficiency", 12, "utility"),
    (r"\+(\d+)% chance to Suppress Spell Damage", "Spell suppression", 22, "suppression"),
    (r"\+(\d+) to maximum Mana", "Mana", 100, "mana"),
    (r"(\d+)% increased (?:Elemental Damage with Attack Skills|Elemental Damage)", "Elemental damage", 60, "attack"),
    (r"(\d+)% increased (?:Fire|Cold|Lightning|Chaos) Damage", "Damage scaling", 80, "damage"),
    (r"(\d+)% increased (?:Armour and Evasion|Armour and Energy Shield|Evasion and Energy Shield|Armour|Evasion Rating)", "Defence scaling", 120, "defense"),
    (r"\+(\d+) to Armour", "Flat armour", 500, "defense"),
    (r"\+(\d+) to Evasion Rating", "Flat evasion", 500, "defense"),
    (r"\+(\d+)% to (?:Fire and Cold|Fire and Lightning|Cold and Lightning) Resistances", "Dual resistance", 24, "resistance"),
    (r"\+(\d+) to all Attributes", "All attributes", 25, "attribute"),
    (r"(\d+)% increased Critical Strike Chance", "Critical chance", 38, "critical"),
    (r"(\d+)% increased Projectile Speed", "Projectile speed", 40, "utility"),
    (r"(\d+)% increased Damage over Time", "Damage over time", 50, "dot"),
    (r"\+(\d+) to Accuracy Rating", "Accuracy", 600, "attack"),
    (r'(\d+)% increased maximum Life', 'Life scaling', 10, 'defense'),
    (r'(\d+)% increased maximum Mana', 'Mana scaling', 12, 'mana'),
    (r'Regenerate (\d+) Life per second', 'Life regeneration', 100, 'recovery'),
    (r'Regenerate (\d+)% of Life per second', 'Life regeneration', 2, 'recovery'),
    (r'(\d+)% increased Mana Regeneration Rate', 'Mana regeneration', 70, 'recovery'),
    (r'\+(\d+)% Chance to Block(?: Attack Damage)?', 'Block chance', 10, 'defense'),
    (r'(\d+)% increased (?:Global )?Critical Strike Chance', 'Critical chance', 40, 'critical'),
    (r'\+(\d+) to Level of (?:all |Socketed )?.*Gems', 'Gem levels', 2, 'caster'),
    (r'Socketed Gems are Supported by Level (\d+) .*', 'Built-in support', 20, 'utility'),
    (r'(\d+)% increased (?:Brand|Totem|Trap|Mine) Damage', 'Specialized damage', 50, 'damage'),
    (r'\+(\d+) to Maximum (?:Frenzy|Power|Endurance) Charges', 'Maximum charges', 1, 'utility'),
    (r'\+(\d+)% to maximum (?:Fire|Cold|Lightning|all Elemental) Resistances?', 'Maximum resistance', 3, 'defense'),
    (r'(\d+)% increased Light Radius', 'Light radius', 20, 'neutral'),
    (r'(\d+)% reduced Attribute Requirements', 'Reduced requirements', 32, 'neutral'),
    (r'Reflects (\d+) .*Damage to .*Attackers', 'Reflected damage', 100, 'neutral'),
]


def rate_rare(item: Item, archetype: str = "General") -> dict:
    if item.rarity != "Rare":
        raise ValueError("The affix rating is for rare equipment only.")
    if item.unidentified or item.item_class not in EQUIPMENT_CLASSES:
        return {"score": None, "summary": "Not rated: unidentified or unsupported item class.",
                "reasons": [], "unknown": item.mods, "confidence": "Unsupported"}
    reasons, unknown, evaluated = [], [], []
    for index,mod in enumerate(item.mods):
        info=item.mod_details[index]if len(item.mod_details)==len(item.mods)else item.mod_info.get(mod,{})
        recognized = False
        constant={'cannot be frozen':('Freeze immunity',1.,'ailment'),
                  'cannot be chilled':('Chill immunity',.6,'ailment'),
                  'cannot be shocked':('Shock immunity',.8,'ailment'),
                  'cannot be ignited':('Ignite immunity',.6,'ailment'),
                  "hits can't be evaded":('Hits cannot be evaded',1.,'attack')}.get(mod.casefold())
        if constant:
            label,strength,group=constant
            reasons.append(label+': useful non-numeric modifier')
            evaluated.append(dict(mod=mod,category=label,strength=strength,group=group,
                                  tier=info.get('tier'),impact='Contributes'))
            continue
        for pattern, label, ceiling, group in RULES:
            match = re.fullmatch(pattern.replace(r'(\d+)', r'(\d+(?:\.\d+)?)') + r'(?: \((?:crafted|fractured)\))?', mod, re.I)
            if match:
                if label=='Life':ceiling={'Rings':90,'Amulets':89,'Boots':100,'Gloves':100,'Body Armours':150,'Helmets':120,'Shields':110,'Belts':120}.get(item.item_class,ceiling)
                if label=='Flat energy shield':ceiling={'Rings':51,'Amulets':51,'Body Armours':200,'Helmets':100,'Gloves':75,'Boots':75,'Shields':100}.get(item.item_class,ceiling)
                if label=='Attack speed'and item.item_class in ('Gloves','Rings','Quivers'):ceiling=16
                if label=='Gem levels'and 'Socketed'not in mod:ceiling=1
                if item.item_class in ('Jewels','Abyss Jewels'):
                    ceiling={'Life':40,'Life scaling':7,'Minion damage':20,'Minion attack & cast speed':8,
                        'Minion speed':8,'Spell damage':16,'Attack speed':8,'Cast speed':8,'Critical multiplier':18,
                        'Flat energy shield':40,'Energy shield scaling':8,'Elemental resistance':12,
                        'All elemental resistances':10,'Chaos resistance':13,'DoT multiplier':8,'Attribute':16,
                        'All attributes':8,'Mana':40}.get(label,ceiling)
                strength = min(1., float(match[1]) / ceiling)
                tier = info.get('tier')
                reasons.append(f"{label}: {round(strength * 100)}% of heuristic reference")
                evaluated.append(dict(mod=mod, category=label, strength=strength, tier=tier,group=group,
                                      roll_position=info.get('roll_position'),
                                      affix=info.get('affix'),
                                      impact='Contributes'))
                recognized = True
                break
        if not recognized:
            minion=re.fullmatch(r'Minions deal (\d+) to (\d+) additional (Physical|Fire|Cold|Lightning|Chaos) Damage',mod,re.I)
            if minion:
                strength=min(1.,(float(minion[1])+float(minion[2]))/2/25)
                reasons.append('Added minion damage: complementary damage source')
                evaluated.append(dict(mod=mod,category='Added minion damage',strength=strength,group='minion_damage',
                                      tier=info.get('tier'),impact='Contributes'))
                recognized=True
        if not recognized:
            match = re.fullmatch(r'Adds (\d+) to (\d+) (Physical|Fire|Cold|Lightning|Chaos) Damage(?: to (Attacks|Spells))?(?: \(crafted\))?', mod, re.I)
            if match:
                average = (int(match[1]) + int(match[2])) / 2
                group = 'caster' if (match[4] or '').lower() == 'spells' else 'physical' if match[3].lower() == 'physical' else 'attack'
                reference=(9 if group=='physical'else 40)if item.item_class in ('Rings','Amulets','Gloves')else(50 if group=='physical'else 100)
                strength=min(1.,average/reference)
                reasons.append(f'Added {match[3].lower()} damage: average {average:g} (slot-dependent reference)')
                evaluated.append(dict(mod=mod, category='Added damage', strength=strength,group=group,
                                      tier=info.get('tier'), impact='Contributes'))
                recognized = True
        if not recognized:
            unknown.append(mod)
            evaluated.append(dict(mod=mod, category='Needs review', strength=None, tier=info.get('tier'), impact='Not scored'))
    socket_notes=[]
    if item.links>=6:socket_notes=['Six linked sockets: useful independently of affix quality; check base and socket colours.']
    elif item.links==5:socket_notes=['Five linked sockets: levelling / early progression utility.']
    elif item.sockets>=6:socket_notes=['Six sockets, not six-linked; socket count alone does not imply strong affixes.']
    if not reasons:
        return {"score": None, "summary": "No supported modifiers; manual review required.",
                "reasons": [], "unknown": unknown, "confidence": "Low", "evaluated": evaluated,
                "link_notes":socket_notes,"links":item.links,"sockets":item.sockets}
    from exile.rare_scoring import score_affixes
    assessment,synergies=score_affixes(evaluated,archetype)
    reasons.extend(synergies)
    score=assessment['score'];affix_score=score
    crafting=crafting_potential(item,assessment)
    assessment['crafting_bonus']=crafting['bonus']
    if crafting['bonus']:
        score=round(min(10.,score+crafting['bonus']),1)
        assessment['score']=score
        reasons.append(f"Crafting: {crafting['open_prefixes']} open prefixes / {crafting['open_suffixes']} open suffixes (+{crafting['bonus']:g})")
    metrics={}
    speed=re.search(r'\d+(?:\.\d+)?',item.properties.get('Attacks per Second',''))
    if speed:
        aps=float(speed[0])
        for prop,key in (('Physical Damage','Physical DPS'),('Elemental Damage','Elemental DPS')):
            ranges=re.findall(r'(\d+)\s*[-–]\s*(\d+)',item.properties.get(prop,''))
            if ranges:metrics[key]=round(sum((float(a)+float(b))/2 for a,b in ranges)*aps,1)
    return {"score": round(score, 1), "summary": "Affix quality and synergy heuristic; not a market price.",
            "affix_score":affix_score,"assessment":assessment,"crafting":crafting,"link_notes":socket_notes,"sockets":item.sockets,"links":item.links,"metrics":metrics,
            "reasons": reasons, "unknown": unknown,
            "confidence": "Limited" if unknown else "Heuristic", "evaluated": evaluated}


def crafting_potential(item,assessment):
    result=dict(bonus=0.,open_prefixes=None,open_suffixes=None,reason='Affix slots not confirmed')
    if item.corrupted or item.properties.get('Mirrored'):
        return dict(result,reason='Corrupted or mirrored; ordinary crafting unavailable')
    if item.item_class in ('Jewels','Abyss Jewels','Cluster Jewels','Maps','Flasks')or not item.mod_details:return result
    slots={'Prefix':set(),'Suffix':set()}
    for info in item.mod_details:
        kind=next((k for k in slots if k+' Modifier'in info.get('affix','')),None)
        if kind is None:return result
        slots[kind].add(info.get('affix_id',info['affix']))
    if any(len(v)>3 for v in slots.values()):return result
    result.update(open_prefixes=3-len(slots['Prefix']),open_suffixes=3-len(slots['Suffix']),reason='Confirmed advanced affix annotations')
    # Crafting space helps an existing useful combination, not empty filler.
    if assessment.get('coherent_affixes',0)>=2 and assessment.get('score',0)>=3:
        result['bonus']=round(min(.6,.15*(result['open_prefixes']+result['open_suffixes'])),2)
    return result


def item_text(item):
    """Readable assessment source using measured counts, not invented socket colours."""
    parts=[f'Item Class: {item.item_class}\nRarity: {item.rarity}\n{item.name}\n{item.base}']
    parts.append('\n'.join(f'{k}: {v}'for k,v in item.properties.items()if k!='Mirrored'))
    parts.append(f'Link Count: {item.links}\nSocket Count: {item.sockets}')
    parts.extend(f"{m['mod']} ({m['source'].lower()})"for m in item.special_mods)
    lines=[];previous=None
    for index,mod in enumerate(item.mods):
        info=item.mod_details[index]if index<len(item.mod_details)else item.mod_info.get(mod,{})
        identity=info.get('affix_id',info.get('affix'))
        if info.get('affix')and identity!=previous:lines.append(info['affix'])
        lines.append(mod);previous=identity
    parts.append('\n'.join(lines))
    if item.corrupted:parts.append('Corrupted')
    if item.properties.get('Mirrored'):parts.append('Mirrored')
    return '\n--------\n'.join(p for p in parts if p)
