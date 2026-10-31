import struct
import time
from pathlib import Path

import pytest

from exile.model import Snapshot
from exile.plugins import PluginManager
from exile.radar import classify_object,classify_actor,preferred_object_name
from exile.reader import Reader
from exile.mapview import EntityMotion

ROOT = Path(__file__).resolve().parents[1]


def radar(saved=None):
    manager = PluginManager(ROOT/'plugins', saved)
    manager.discover()
    assert not manager.errors
    assert 'health' not in {p.id for p in manager.plugins}
    return next(p for p in manager.plugins if p.id == 'radar')


def sample(**updates):
    monster = dict(id=42, kind='monster', rarity=2, grid=(10,10), screen=(300,300),
                   life=100, max_life=100, alive=True, hostile=True, name='Rare')
    monster.update(updates)
    return Snapshot(source='preview', captured_at=time.monotonic(), in_game=True, loading=False,
                    entities=[monster], capabilities={'entities','health'})


def test_radar_categories_sizes_colors_and_health_merge():
    p = radar()
    for rarity, category in enumerate(('normal','magic','rare','unique')):
        marks = p.tick(sample(rarity=rarity), object())
        circle = next(m for m in marks if m.kind=='dot')
        assert circle.color == p.settings[f'color_{category}']
        assert circle.size == p.settings[f'size_{category}']
        assert any(m.kind=='bar' for m in marks) == (rarity>=2)
    assert p.settings['size_normal'] < p.settings['size_rare'] < p.settings['size_unique']
    p.settings.update(size_rare=9, color_rare='#123456')
    circle = p.tick(sample(),object())[0]
    assert (circle.size,circle.color)==(9,'#123456')


def test_corpses_unknown_health_and_minions_are_hidden_without_grace_period():
    p=radar()
    assert p.tick(sample(),object())
    for updates in (dict(life=0,alive=False),dict(life=None),dict(life=float('nan')),dict(hostile=False)):
        assert not p.tick(sample(**updates),object())
    p.settings['show_friendly']=True
    marks=p.tick(sample(hostile=False),object())
    assert len(marks)==1 and marks[0].color==p.settings['color_friendly']
    # A resurrection is accepted from fresh life data; no permanent corpse ID cache.
    assert p.tick(sample(life=100,alive=True),object())


def test_health_bars_work_with_map_closed_and_optional_capability():
    p=radar()
    s=sample()
    s.source='live'
    s.map_transform=None
    marks=p.tick(s,object())
    assert len(marks)==1 and marks[0].kind=='bar'
    s.capabilities.discard('health')
    assert not p.tick(s,object())


def test_legacy_health_preferences_migrate_without_enabling_module():
    p=radar({'health':{'settings':dict(width=140,rare_only=False)}})
    assert not p.enabled and p.settings['health_width']==140
    assert p.settings['health_filter']=='All enemies'
    p=radar({'health':{'settings':dict(width=140)},'radar':{'settings':dict(health_width=60)}})
    assert p.settings['health_width']==60


@pytest.mark.parametrize('path,components,category',[
    ('Metadata/Terrain/Leagues/Legion/Objects/LegionInitiator',{'Targetable'},'legion'),
    ('Metadata/MiscellaneousObjects/Monolith',{'Monolith'},'essence'),
    ('Metadata/MiscellaneousObjects/Waypoint',{'MinimapIcon'},'waypoint'),
    ('Metadata/MiscellaneousObjects/Breach/BreachObject',{'Targetable'},'breach'),
    ('Metadata/Terrain/Leagues/Delve/Objects/DelveMineral',{'Targetable'},'delve'),
    ('Metadata/Chests/LeagueHeist/HeistChestCurrency',{'Chest'},'heist'),
    ('Metadata/Terrain/Leagues/Ritual/Objects/RitualRuneInteractable',{'Targetable'},'ritual'),
    ('Metadata/Monsters/LeagueBlight/Monster',{'Monster'},None),
    ('Metadata/Effects/Leagues/Legion/Objects/LegionInitiator',set(),None),
    ('Metadata/Terrain/Leagues/Expedition/Objects/DecorativeLight',set(),None),
])
def test_object_categories_do_not_promote_monsters_or_effects(path,components,category):
    result=classify_object(path,components)
    assert (result[0] if result else None)==category


@pytest.mark.parametrize('path,components,expected',[
    ('Metadata/Terrain/Leagues/Settlers/Node/Objects/NodeTypes/Verisium',{'Targetable','MinimapIcon'},('settlers','Verisium Outcrop')),
    ('Metadata/Terrain/Leagues/Settlers/Node/Objects/NodeTypes/CrimsonIron',{'Targetable'},('settlers','Crimson Iron Deposit')),
    ('Metadata/Terrain/Leagues/Settlers/Node/Objects/NodeTypes/PetrifiedWood',{'MinimapIcon'},('settlers','Petrified Amber Deposit')),
    ('Metadata/Chests/LeagueDeepwater/BrinerotStoresChestEncounter',{'Chest'},('allflame','Brinerot Plunder')),
    ('Metadata/Terrain/Leagues/Deepwater/Objects/BrinerotStoresChestEncounterSpawner',{'Targetable'},('allflame','Brinerot Plunder')),
    ('Metadata/Chests/LeagueDeepwater/CursedTreasureChestEncounter',{'Chest'},('allflame','Cursed Treasure')),
    ('Metadata/MiscellaneousObjects/PrimordialBosses/TangleAltar',{'Targetable','MinimapIcon'},('eldritch','Eater of Worlds Altar')),
    ('Metadata/MiscellaneousObjects/PrimordialBosses/CleansingFireAltar',{'Targetable'},('eldritch','Searing Exarch Altar')),
    ('Metadata/MiscellaneousObjects/Affliction/AfflictionInitiator',{'MinimapIcon'},('delirium','Delirium Mirror')),
    ('Metadata/Chests/LeagueHeist/HeistSmugglersCoinCache',{'Chest'},('heist',"Smuggler's Cache")),
    ('Metadata/Chests/StrongBoxes/StrongboxDivination',{'Chest'},('strongbox',"Diviner's Strongbox")),
    ('Metadata/Chests/StrongBoxes/StrongboxScarab',{'Chest'},('strongbox',"Operative's Strongbox")),
    ('Metadata/Chests/StrongBoxes/Arcanist',{'Chest'},('strongbox',"Arcanist's Strongbox")),
    ('Metadata/QuestObjects/Labyrinth/LabyrinthTrialPortal',{'AreaTransition'},('trial','Labyrinth Trial')),
])
def test_named_objects_precede_generic_encounters_or_ordinary_chests(path,components,expected):
    assert classify_object(path,components)==expected
    assert classify_object(path+'@83',components)==expected


@pytest.mark.parametrize('suffix',[
    'MineralClaimedMarker','VerisiumObjects/scorch_decal_set.ao','CrimsonIronObjects/SmallGrowth',
    'DemonCopperObjects/CopperSpawner1','PetrifiedWoodObjects/FungalSpawner1','Verisium.ot.tok',
])
def test_ore_decorations_and_spawners_are_not_deposits(suffix):
    path='Metadata/Terrain/Leagues/Settlers/Node/Objects/NodeTypes/'+suffix
    assert classify_object(path,{'Targetable','MinimapIcon'})is None


def test_allflame_marker_is_independent_of_hidden_ordinary_chests_and_supports_settings():
    p=radar();assert not p.settings['show_chest']
    s=sample();s.entities=[dict(kind='valuable',category='allflame',name='Brinerot Plunder',grid=(10,10),used=False)]
    p.settings.update(size_allflame=9,color_allflame='#123456')
    marks=p.tick(s,object());assert len(marks)==1
    assert marks[0].text=='Brinerot Plunder'and marks[0].size==9 and marks[0].color=='#123456'
    s.entities[0]['used']=True;assert not p.tick(s,object())
    s.entities[0]['used']=False;p.settings['show_allflame']=False;assert not p.tick(s,object())


def test_native_generic_names_do_not_erase_specific_fallback_and_unknowns_keep_type():
    assert preferred_object_name('Encounter','Verisium Outcrop')=='Verisium Outcrop'
    assert preferred_object_name('','Verisium Outcrop')=='Verisium Outcrop'
    assert preferred_object_name('Some real unique name','Strongbox')=='Some real unique name'
    assert classify_object('Metadata/Terrain/Leagues/Future/Objects/CuriousAltar',{'Targetable','MinimapIcon'})==('encounter','Curious Altar')


def test_mechanic_actors_do_not_need_enemy_health_and_do_not_capture_projectiles():
    assert classify_actor('Metadata/Monsters/Avatar/Avatar',{'Positioned'})==('harbinger','Harbinger')
    assert classify_actor('Metadata/Monsters/Avatar/AvatarProjectile',{'Positioned'})is None
    assert classify_actor('Metadata/Monsters/Masters/Einhar',{'Positioned'})==('masters','Einhar, Beastmaster')
    assert classify_actor('Metadata/Monsters/DeepwaterLeague/BrinerotSpearmanEncounter',{'Positioned','Monster'})is None


def test_reader_classifies_harbinger_anchor_and_still_hides_its_dead_actor():
    r,m=scene_reader();r.path=lambda address:'Metadata/Monsters/Avatar/Avatar'
    args=(0x10000,[bytes([1]*20)]*20,[0.]*16,(1920,1080))
    entry=r.scene_entity(*args)
    assert entry['kind']=='valuable'and entry['category']=='harbinger'
    struct.pack_into('<i',m.regions[0x40000],0x178+0x30,0)
    assert r.scene_entity(*args)is None


def test_object_settings_hide_opened_chests_and_allow_custom_waypoint_style():
    p=radar()
    s=sample()
    s.entities=[dict(kind='valuable',category='waypoint',grid=(10,10),name='Waypoint')]
    p.settings.update(size_waypoint=10,color_waypoint='#abcdef')
    assert p.tick(s,object())[0].size==10
    assert p.tick(s,object())[0].color=='#abcdef'
    s.entities=[dict(kind='valuable',category='strongbox',grid=(10,10),used=True)]
    assert not p.tick(s,object())
    p.settings['hide_used']=False
    assert p.tick(s,object())


class SceneMemory:
    def __init__(self): self.regions={}
    def read(self,address,count):
        for start,data in self.regions.items():
            if start<=address and address+count<=start+len(data):
                return bytes(data[address-start:address-start+count])
        raise OSError('Missing test allocation')


def scene_reader():
    import json
    profile=json.loads((ROOT/'profiles/steam-25113903.read-only.json').read_text())
    r,m=Reader(profile),SceneMemory()
    entity=0x10000
    data=bytearray(0x90)
    struct.pack_into('<QQQ',data,0x10,0x20000,0x20018,0x20018)
    struct.pack_into('<i',data,0x88,42)
    m.regions[entity]=data
    m.regions[0x20000]=bytearray(struct.pack('<QQQ',0x30000,0x40000,0x50000))
    for pointer,vtable,size in ((0x30000,1,0x300),(0x40000,2,0x200),(0x50000,3,0x180)):
        data=bytearray(size)
        struct.pack_into('<QQ',data,0,vtable,entity)
        m.regions[pointer]=data
    struct.pack_into('<ii',m.regions[0x30000],0x294,10,10)
    struct.pack_into('<ii',m.regions[0x40000],0x178+0x2c,100,100)
    struct.pack_into('<i',m.regions[0x50000],0x144,2)
    r.memory=m
    r.path=lambda address:'Metadata/Monsters/Test'
    r.component_name=lambda table:{1:'Positioned',2:'Life',3:'ObjectMagicProperties'}[table]
    return r,m


def test_fallback_refreshes_life_and_rejects_reused_entity_identity():
    r,m=scene_reader()
    args=(0x10000,[bytes([1]*20)]*20,[0.]*16,(1920,1080))
    alive=r.scene_entity(*args)
    assert alive['alive'] and alive['rarity']==2 and alive['hostile']
    struct.pack_into('<i',m.regions[0x40000],0x178+0x30,0)
    dead=r.scene_entity(*args,recovered=True)
    assert dead['life']==0 and not dead['alive']
    struct.pack_into('<i',m.regions[0x10000],0x88,43)
    assert r.scene_entity(*args,recovered=True) is None


def test_component_replacement_and_owner_changes_do_not_reuse_old_life():
    r,m=scene_reader()
    args=(0x10000,[bytes([1]*20)]*20,[0.]*16,(1920,1080))
    assert r.scene_entity(*args)['life']==100
    m.regions[0x60000]=bytearray(m.regions[0x40000])
    struct.pack_into('<i',m.regions[0x60000],0x178+0x30,0)
    struct.pack_into('<Q',m.regions[0x20000],8,0x60000)
    assert r.scene_entity(*args)['life']==0
    struct.pack_into('<Q',m.regions[0x30000],8,0x99999)
    with pytest.raises(ValueError,match='owner changed'):
        r.scene_entity(*args)


def test_changing_entity_tree_retries_then_uses_bounded_same_instance_candidates():
    r=Reader({'offsets':{}})
    attempts=iter([ValueError('mutating'),[100],ValueError('mutating'),ValueError('mutating')])
    def scan(_session):
        result=next(attempts)
        if isinstance(result,Exception):raise result
        return result
    r.entity_addresses=scan
    assert r.scene_addresses(10,('instance',1),{})==([100],False)
    diagnostics={}
    assert r.scene_addresses(10,('instance',1),diagnostics)==([100],True)
    assert 'entity_scan' in diagnostics and 'entities' not in diagnostics
    r.entity_addresses=lambda _session:(_ for _ in ()).throw(ValueError('mutating'))
    with pytest.raises(ValueError):
        r.scene_addresses(10,('new instance',2),{})


def test_entity_motion_smooths_positions_but_removes_death_and_missing_entities_immediately():
    motion=EntityMotion(delay=.05)
    grid=[[1]]
    def snap(at,x,**updates):
        e=dict(id=42,address=0x10000,kind='monster',grid=(10,10),map_grid=(x,0),screen=(x*10,100),
               life=100,max_life=100,alive=True)
        e.update(updates)
        return Snapshot(source='live',captured_at=at,area='Forest',grid=grid,in_game=True,loading=False,entities=[e])
    output=[]
    for frame in range(31):
        now=10+frame*.005
        at=10+(frame//4)*.02
        source=snap(at,(at-10)*100)
        e=motion.sample(source,now=now)[0]
        assert source.entities[0]['map_grid']==((at-10)*100,0)
        assert e['grid']==(10,10) and e['life']==100
        output.append(e['map_grid'][0])
    assert all(abs((b-a)-.5)<1e-8 for a,b in zip(output[12:],output[13:]))
    dead=motion.sample(snap(10.16,16,life=0,alive=False),now=10.16)[0]
    assert dead['life']==0 and dead['alive'] is False and not motion.histories
    assert motion.sample(snap(10.18,1),now=10.18)[0]['map_grid']==(1,0)
    missing=snap(10.2,2);missing.entities=[]
    assert not motion.sample(missing,now=10.2) and not motion.histories


def test_entity_motion_handles_leaving_and_reentering_the_viewport():
    motion=EntityMotion()
    s=sample();s.source='live';s.grid=[[1]];s.in_game=True;s.loading=False
    s.entities[0].update(address=100,map_grid=(10,10))
    motion.sample(s,now=s.captured_at)
    s.captured_at+=.01;s.entities[0]['screen']=None
    assert motion.sample(s,now=s.captured_at)[0]['screen'] is None
    s.captured_at+=.01;s.entities[0]['screen']=(400,300)
    assert motion.sample(s,now=s.captured_at)[0]['screen'] is not None


def test_health_bar_smooths_world_position_without_delaying_camera_motion():
    motion=EntityMotion(delay=.033)
    identity=tuple(1. if i%5==0 else 0. for i in range(16))
    s=sample();s.source='live';s.in_game=True;s.loading=False;s.grid=[[1]];s.captured_at=10
    s.entities[0].update(address=100,map_grid=(0,0),health_world=(0,0,0),health_camera=(identity,(1000,1000)))
    motion.sample(s,now=10)
    camera=list(identity);camera[12]=.5
    s.captured_at=10.02
    s.entities[0].update(map_grid=(.2,0),health_world=(.2,0,0),health_camera=(camera,(1000,1000)))
    result=motion.sample(s,now=10.02)[0]
    # Default 8 ms actor smoothing gives x=.12. The camera's newest .5 offset
    # is applied in full, rather than dragging it through the 33 ms map delay.
    assert abs(result['screen'][0]-810)<1e-8
    assert result['life']==100 and s.entities[0]['health_world']==(.2,0,0)
    motion.health_delay=0
    assert abs(motion.sample(s,now=10.02)[0]['screen'][0]-850)<1e-8


def test_shrine_state_hides_used_shrine_and_does_not_depend_on_targetability():
    r,m=scene_reader()
    r.path=lambda address:'Metadata/Shrines/Shrine'
    previous_name=r.component_name
    r.component_name=lambda table:'Shrine' if table==4 else previous_name(table)
    shrine=bytearray(0x40);struct.pack_into('<QQ',shrine,0,4,0x10000)
    m.regions[0x70000]=shrine
    m.regions[0x20000]+=struct.pack('<Q',0x70000)
    struct.pack_into('<QQQ',m.regions[0x10000],0x10,0x20000,0x20020,0x20020)
    args=(0x10000,[bytes([1]*20)]*20,[0.]*16,(1920,1080))
    unused=r.scene_entity(*args)
    assert unused['category']=='shrine' and unused['used'] is False
    shrine[0x24]=1
    used=r.scene_entity(*args)
    assert used['used'] is True
    p=radar();s=sample();s.entities=[used]
    assert not p.tick(s,object())
    p.settings['hide_used']=False
    assert p.tick(s,object())


def test_object_use_transition_is_debounced_and_never_assumed_on_first_load():
    r=Reader({'offsets':{}})
    assert not r.observe_object_availability(100,1,False,10)
    assert not r.observe_object_availability(100,1,False,20)
    assert not r.observe_object_availability(100,1,True,21)
    assert not r.observe_object_availability(100,1,False,21.1)
    assert not r.observe_object_availability(100,1,False,21.2)
    assert r.observe_object_availability(100,1,False,21.7)
    assert not r.observe_object_availability(100,1,True,22)
    assert not r.observe_object_availability(100,2,False,23)  # reused address

def test_encounter_marker_clutter_filters():
    from exile.radar import classify_object
    components={'Targetable':1,'MinimapIcon':2}
    assert classify_object('Metadata/Terrain/Leagues/Expedition/Objects/ExpeditionDetonator',components)==('expedition','Expedition')
    assert classify_object('Metadata/Terrain/Leagues/Expedition/Objects/ExpeditionRemnant',components)is None
    assert classify_object('Metadata/Chests/Expedition/ExpeditionChest',{'Chest':1})is None
    assert classify_object('Metadata/Terrain/Leagues/Breach/Objects/BreachHand',components)==('breach','Breach')

def test_expedition_aliases_cannot_fall_back_to_ordinary_chests():
    for prefix in ('Metadata/Chests/LeaguesExpedition/','Metadata/Chests/LeagueExpedition/','Metadata/Terrain/Leagues/Expedition/Objects/'):
        for leaf in ('ExpeditionChest','ExpeditionRunicMarker','ExpeditionRemnant'):
            assert classify_object(prefix+leaf,{'Chest':1,'Targetable':2,'MinimapIcon':3})is None


def test_campaign_only_recipes_and_clicked_altars():
    p=radar();s=sample();s.source='live';s.town=False;s.map_transform=dict(player=(10,10),center=(400,300),basis_x=1,basis_y=1)
    recipe=dict(kind='valuable',category='recipe',grid=(11,11),available=True)
    s.entities=[recipe];s.area_id='MapWorldsStrand'
    assert not p.tick(s,object())
    s.area_id='1_3_1';assert any(m.kind=='dot'for m in p.tick(s,object()))
    recipe['available']=False;assert not p.tick(s,object())
    s.entities=[dict(kind='valuable',category='eldritch',grid=(11,11),available=False)]
    assert not p.tick(s,object())
    s.entities[0]['available']=True;assert any(m.kind=='dot'for m in p.tick(s,object()))


def test_native_breach_icon_fallback_validates_name_and_owner():
    from exile.reader import Reader
    r=Reader({'offsets':dict(minimap_icon_definition=32,minimap_icon_name=0)})
    calls=[];raw=bytearray(40);struct.pack_into('<Q',raw,32,1234)
    def owned(component,owner,size):calls.append((component,owner,size));return bytes(raw)
    r.owned_component=owned;r.q=lambda address:address;r.utf16=lambda *args,**kwargs:'Breach'
    assert r.native_icon_name(100,200)=='Breach'
    assert len(calls)==2 and calls[-1]==(100,200,16)
    r.utf16=lambda *args,**kwargs:'Invalid Name!'
    assert r.native_icon_name(100,200)==''
