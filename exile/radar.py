"""Radar categories and conservative classification of loaded world entities."""
import re

# id, name, settings tab, color, radius, enabled, label
CATEGORIES = (
    ('normal', 'Normal monsters', 'Monsters', '#dc6464', 2, True, False),
    ('magic', 'Magic monsters', 'Monsters', '#719cfa', 3, True, False),
    ('rare', 'Rare monsters', 'Monsters', '#f1d354', 5, True, True),
    ('unique', 'Unique monsters / bosses', 'Monsters', '#f2994a', 6, True, True),
    ('friendly', 'Allies and minions', 'Monsters', '#70c99b', 2, False, False),
    ('unknown', 'Unclassified monsters', 'Monsters', '#aeb7c7', 3, True, False),
    ('waypoint', 'Waypoints', 'Objects', '#83b8ff', 6, True, True),
    ('exit', 'Area transitions', 'Objects', '#9cb9e8', 5, True, True),
    ('portal', 'Portals', 'Objects', '#74d8e0', 5, True, True),
    ('strongbox', 'Strongboxes', 'Objects', '#77d6b1', 5, True, True),
    ('shrine', 'Shrines', 'Objects', '#bc97ed', 5, True, True),
    ('quest', 'Quest objects', 'Objects', '#e5c67a', 5, True, True),
    ('recipe', 'Crafting recipes', 'Objects', '#8dd9c4', 4, True, True),
    ('chest', 'Ordinary chests', 'Objects', '#9da8b4', 3, False, False),
    ('legion', 'Legion monoliths', 'Encounters', '#cf9cf0', 6, True, True),
    ('essence', 'Essence monoliths', 'Encounters', '#d9a6ee', 5, True, True),
    ('breach', 'Breach hands', 'Encounters', '#c982ef', 6, True, True),
    ('abyss', 'Abyss cracks / troves', 'Encounters', '#9ccc60', 5, True, True),
    ('ritual', 'Ritual altars', 'Encounters', '#df8e9d', 5, True, True),
    ('expedition', 'Expedition encounter', 'Encounters', '#e1b578', 5, True, True),
    ('harvest', 'Harvest entrances / plots', 'Encounters', '#8bbf88', 5, True, True),
    ('blight', 'Blight pumps / rewards', 'Encounters', '#d9c66b', 5, True, True),
    ('delirium', 'Delirium mirrors / rewards', 'Encounters', '#c2c7d2', 5, True, True),
    ('delve', 'Delve sulphite / encounters', 'Encounters', '#d9ba60', 5, True, True),
    ('heist', 'Heist caches / contracts', 'Encounters', '#6ec9cc', 5, True, True),
    ('ultimatum', 'Ultimatum encounters', 'Encounters', '#de7d79', 5, True, True),
    ('sanctum', 'Sanctum entrances', 'Encounters', '#d8cfab', 5, True, True),
    ('settlers', 'Settlers ore deposits', 'Encounters', '#6fc9cd', 5, True, True),
    ('allflame', 'Allflame encounters / treasure', 'Encounters', '#6bbbd7', 5, True, True),
    ('eldritch', 'Eldritch altars', 'Encounters', '#cf838a', 5, True, True),
    ('harbinger', 'Harbingers', 'Encounters', '#79b8eb', 5, True, True),
    ('masters', 'League NPCs', 'Encounters', '#d4bb88', 5, True, True),
    ('incursion', 'Incursion portals / objects', 'Encounters', '#c58c68', 5, True, True),
    ('betrayal', 'Syndicate supplies / objects', 'Encounters', '#a4bb79', 5, True, True),
    ('trial', 'Labyrinth trials', 'Encounters', '#c4ad7b', 5, True, True),
    ('encounter', 'Other marked encounters', 'Encounters', '#bca4d8', 5, True, True),
)
MONSTERS = frozenset(('normal', 'magic', 'rare', 'unique', 'friendly', 'unknown'))
RARITIES = ('normal', 'magic', 'rare', 'unique')

# Match recognizable encounter controls/rewards, not every decoration in a league.
OBJECT_RULES = (
    ('legion', ('/legion/objects/legioninitiator',), 'Timeless Monolith'),
    ('essence', ('/monolith', '/essence/'), 'Essence monolith'),
    ('breach', ('/breach/breachobject', '/breach/objects/', '/breachchest'), 'Breach'),
    ('abyss', ('/abyss/abyssstartnode', '/abyss/abyssnode', '/abyss/abyssfinalnodechest', '/abysscrackspawners/'), 'Abyss'),
    ('ritual', ('/ritual/objects/', '/ritualaltar'), 'Ritual altar'),
    ('expedition', ('/expedition/objects/', '/expedition/expedition'), 'Expedition'),
    ('harvest', ('/harvest/objects/', '/harvestportal', '/harvest/harvest'), 'Harvest'),
    ('blight', ('/blight/objects/', '/blightchest', '/blightpump'), 'Blight'),
    ('delirium', ('/delirium/objects/', '/affliction/objects/', '/affliction/affliction'), 'Delirium'),
    ('delve', ('/delve/objects/delvemineral',), 'Voltaxic Sulphite'),
    ('delve', ('/delve/objects/encountercontrolobjects/',), 'Delve Encounter'),
    ('heist', ('/heist/objects/', '/heistsmugglerscache', '/heistchest', '/leagueheist/heistchest'), 'Heist cache'),
    ('ultimatum', ('/ultimatum/objects/', '/ultimatum/ultimatum'), 'Ultimatum'),
    ('sanctum', ('/sanctum/objects/', '/sanctumportal', '/sanctum/sanctum'), 'Sanctum'),
)


ORE_NAMES={'verisium':'Verisium Outcrop','crimsoniron':'Crimson Iron Deposit',
    'orichalcum':'Orichalcum Deposit','petrifiedwood':'Petrified Amber Deposit','bismuth':'Bismuth Deposit',
    'demoncopper':'Ore Deposit'}
STRONGBOX_NAMES=(('strongboxdivination',"Diviner's Strongbox"),('diviner',"Diviner's Strongbox"),
    ('strongboxscarab',"Operative's Strongbox"),('operative',"Operative's Strongbox"),
    ('arcanist',"Arcanist's Strongbox"),('cartographer',"Cartographer's Strongbox"),
    ('gemcutter',"Gemcutter's Strongbox"),('jeweller',"Jeweller's Strongbox"),('artisan',"Artisan's Strongbox"),
    ('arsenal',"Blacksmith's Strongbox"),('armory',"Armourer's Strongbox"),
    ('ornate','Ornate Strongbox'),('large','Large Strongbox'),('kaombox',"Kaom's Cache"),('perandusbox','Perandus Bank'))
# Specific interaction assets take priority over broad legacy league rules.
NAMED_OBJECTS=(
    ('allflame','metadata/chests/leaguedeepwater/brinerotstoreschestencounter','Brinerot Plunder'),
    ('allflame','metadata/terrain/leagues/deepwater/objects/brinerotstoreschestencounterspawner','Brinerot Plunder'),
    ('allflame','metadata/chests/leaguedeepwater/cursedtreasurechestencounter','Cursed Treasure'),
    ('allflame','metadata/terrain/leagues/deepwater/objects/cursedtreasurechestencounterspawner','Cursed Treasure'),
    ('eldritch','metadata/miscellaneousobjects/primordialbosses/tanglealtar','Eater of Worlds Altar'),
    ('eldritch','metadata/miscellaneousobjects/primordialbosses/cleansingfirealtar','Searing Exarch Altar'),
    ('eldritch','metadata/miscellaneousobjects/primordialbosses/cleansingaltar','Searing Exarch Altar'),
    ('delirium','metadata/miscellaneousobjects/affliction/afflictioninitiator','Delirium Mirror'),
    ('heist','metadata/chests/leagueheist/heistsmugglerscoincache',"Smuggler's Cache"),
    ('harvest','metadata/terrain/leagues/harvest/objects/harvestfeaturechest','Sacred Grove Entrance'),
    ('blight','metadata/terrain/leagues/blight/objects/blightinitiator','Blight Pump'),
    ('abyss','metadata/miscellaneousobjects/abyss/abysssubareatransition','Abyssal Depths Entrance'),
    ('abyss','metadata/chests/abyss/abyssfinalchest','Abyssal Trove'),
    ('abyss','metadata/miscellaneousobjects/abyss/abyssstartnode','Abyss'),
    ('incursion','metadata/terrain/leagues/incursion/objects/incursionportal','Incursion Portal'),
    ('incursion','metadata/miscellaneousobjects/incursion/incursionportal','Incursion Portal'),
    ('trial','metadata/questobjects/labyrinth/labyrinthtrialportal','Labyrinth Trial'),
    ('betrayal','metadata/chests/leaguebetrayal/betrayalchest','Syndicate Stash'),
)
INTERACTIVE=frozenset(('Targetable','MinimapIcon','Chest','Monolith','Transitionable','AreaTransition','InteractionAction'))


def normalize_path(path):
    return path.replace('\\','/').split('@',1)[0].casefold()


def classify_actor(path,components):
    """Known mechanic anchors can be NPCs or invulnerable monster actors."""
    lower=normalize_path(path)
    if 'Positioned'not in components:return None
    if lower=='metadata/monsters/avatar/avatar':return 'harbinger','Harbinger'
    actors=(('metadata/monsters/masters/einhar','masters','Einhar, Beastmaster'),
        ('metadata/npc/league/incursion/treasurehunterwild','masters','Alva, Master Explorer'),
        ('metadata/npc/league/delve/delveminerwild','masters','Niko, Master of the Depths'),
        ('metadata/monsters/masters/blightbuilderwild','masters','Sister Cassia'),
        ('metadata/monsters/leagueexpedition/npc/expedition','masters','Expedition NPC'))
    for prefix,category,name in actors:
        if lower.startswith(prefix):return category,name
    return None


def preferred_object_name(native,fallback):
    if not native or native.strip().casefold()in {'encounter','object','chest','strongbox','altar','npc','monolith','portal','shrine','deposit'}:return fallback
    return native


def classify_object(path, components):
    lower = normalize_path(path)
    if lower.startswith(('metadata/monsters/', 'metadata/characters/', 'metadata/effects/')):
        return None
    if lower.endswith(('.ao','.ao.tok','.ot','.ot.tok','.pet','.arm','.gt')):return None
    # One encounter marker, never remnants, chests or explosive-placement runes.
    if any(part in lower for part in ('/expedition/','/leagueexpedition/','/leaguesexpedition/')):
        if 'expeditiondetonator' in lower and set(components)&INTERACTIVE:
            return 'expedition','Expedition'
        return None
    if ('/breach/' in lower and any(word in lower.rsplit('/',1)[-1] for word in ('breachobject','breachportal','breachhand'))) and set(components)&INTERACTIVE:
        return 'breach','Breach'
    ore_prefix='metadata/terrain/leagues/settlers/node/objects/nodetypes/'
    if lower.startswith(ore_prefix):
        leaf=lower[len(ore_prefix):]
        name=ORE_NAMES.get(leaf)
        return ('settlers',name)if name and set(components)&INTERACTIVE else None
    if set(components)&INTERACTIVE:
        for category,prefix,name in NAMED_OBJECTS:
            if lower==prefix or lower.startswith(prefix+'_'):return category,name
        if lower.startswith('metadata/terrain/leagues/expedition/objects/expeditiondetonator'):
            return 'expedition','Expedition Detonator'
        if lower.startswith('metadata/chests/leaguebetrayal/'):
            return 'betrayal','Syndicate Stash'
    if 'Waypoint' in components or lower.endswith('waypoint'):
        return 'waypoint', 'Waypoint'
    if 'Monolith' in components:
        return 'essence', 'Essence monolith'
    for category, fragments, name in OBJECT_RULES:
        if any(fragment in lower for fragment in fragments) and set(components) & {
                'Targetable', 'MinimapIcon', 'Chest', 'Monolith', 'Transitionable', 'AreaTransition'}:
            return category, name
    if 'Shrine' in components:
        return 'shrine', 'Shrine'
    if 'Portal' in components or 'TownPortal' in components:
        return 'portal', 'Portal'
    if 'AreaTransition' in components:
        return 'exit', 'Area transition'
    if 'Quest' in components or 'QuestObject' in components:
        return 'quest', 'Quest object'
    if 'craftingrecipe' in lower or 'craftingunlock' in lower or 'craftunlock' in lower:
        return 'recipe', 'Crafting recipe'
    if 'Chest' in components:
        if 'strongbox' in lower:
            leaf=lower.rsplit('/',1)[-1]
            for prefix,name in STRONGBOX_NAMES:
                if leaf.startswith(prefix):return 'strongbox',name
            return 'strongbox', 'Strongbox'
        if not any(word in lower for word in ('pot', 'barrel', 'urn', 'crate', 'basket')):
            return 'chest', 'Chest'
    if ('MinimapIcon' in components and 'Targetable' in components and
            '/leagues/' in lower and '/objects/' in lower and
            not any(word in lower for word in ('effect', 'decoration', 'light', 'daemon','lamp','claimedmarker'))):
        leaf=path.replace('\\','/').split('@',1)[0].rsplit('/',1)[-1]
        readable=re.sub(r'(?<=[a-z])(?=[A-Z])',' ',leaf).replace('_',' ').strip()
        return 'encounter',readable or'Encounter'
    return None


def monster_category(entity):
    if entity.get('hostile') is False:
        return 'friendly'
    rarity = entity.get('rarity')
    if isinstance(rarity, int) and rarity in range(4):
        return RARITIES[rarity]
    if 'rarity' in entity:
        return 'unknown'
    return {'monster': 'normal', 'magic': 'magic', 'rare': 'rare', 'boss': 'unique',
            'unique': 'unique'}.get(entity.get('kind'), 'unknown')
