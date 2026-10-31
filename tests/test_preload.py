from pathlib import Path

from exile.model import Snapshot
from exile.plugins import PluginManager

ROOT=Path(__file__).parents[1]


def plugin(saved=None):
    manager=PluginManager(ROOT/'plugins',saved);manager.discover()
    return next(p for p in manager.plugins if p.id=='preload')


def snapshot(*resources):
    return Snapshot(source='preview',area='Map',area_id='MapTest',town=False,preloads=list(resources))


def test_valuable_box_types_default_on_and_aliases_group_into_one_alert():
    p=plugin();s=snapshot('Metadata/Chests/StrongBoxes/Arcanist',
        'Metadata/Chests/StrongBoxes/Diviner','Metadata/Chests/StrongBoxes/StrongboxDivination',
        'Metadata/Chests/StrongBoxes/Cartographer','Metadata/Chests/StrongBoxes/StrongboxScarab',
        'Metadata/Chests/StrongBoxes/Strongbox')
    p.scan(s,1.)
    assert {r['id']for r in p.alert_rows()}=={'arcanist','diviner','cartographer','operative'}
    assert len(next(r for r in p.alert_rows()if r['id']=='diviner')['resources'])==2
    assert not p.enabled and p.settings['show_unique_boxes'] and not p.settings['show_ordinary']
    p.settings['show_ordinary']=True
    assert len(p.alert_rows())==5  # not an extra generic alert for each typed box


def test_inventory_items_generic_particles_and_templates_do_not_imply_mechanics():
    p=plugin();p.scan(snapshot('Metadata/Items/Scarabs/ScarabBreachNew1',
        'Metadata/Items/Currency/CurrencyEssenceHorror',
        'Metadata/Effects/Spells/League_Ritual/ritual_rune.epk',
        'Metadata/Chests/Abyss/AbyssFinalChestBase.ot.tok'),1.)
    # The generic base template also shares a name prefix with a real chest.
    assert not p.alert_rows()


def test_case_version_and_slash_aliases_keep_one_mechanic_row():
    p=plugin();p.scan(snapshot('Metadata/Monsters/LegionLeague/LegionKaruiGeneral@83',
        'metadata\\monsters\\legionleague\\legionkaruigeneral@84',
        'Metadata/Terrain/Leagues/Legion/Objects/LegionInitiator'),1.)
    rows=p.alert_rows()
    assert {r['id']for r in rows}=={'legion','hyrri'}
    assert all(r['evidence']=='Preload'for r in rows)


def test_seen_evidence_survives_leaving_object_but_clears_for_new_instance():
    p=plugin();s=snapshot('Metadata/Chests/StrongBoxes/Arcanist')
    s.visual_context=dict(key=(1,2,3,4,5,6,100))
    s.entities=[dict(metadata=s.preloads[0],used=False)]
    p.scan(s,1.)
    assert p.alert_rows()[0]['evidence']=='Seen'
    s.entities=[];p.scan(s,1.5)
    assert p.alert_rows()[0]['evidence']=='Seen'
    s.preloads=[];s.visual_context=dict(key=(1,2,3,4,7,8,100));p.scan(s,1.6)
    assert not p.alert_rows()


def test_known_unique_boxes_and_special_essences_take_priority_and_respect_toggles():
    p=plugin();p.settings['limit']=1
    s=snapshot('Metadata/Monsters/Daemon/ChestDaemonSummonKaomTotems',
        'Metadata/Monsters/Daemon/EssenceDaemonHorror1','Metadata/Chests/StrongBoxes/Arcanist')
    marks=p.tick(s,object());panel=marks[0].payload
    assert panel['rows'][0]['id']=='kaoms_cache' and panel['overflow']==3
    p.settings['show_unique_boxes']=False
    assert 'kaoms_cache' not in {r['id']for r in p.alert_rows()}
    p.settings['show_special_essences']=False
    assert 'horror' not in {r['id']for r in p.alert_rows()}


def test_custom_rules_migrate_and_reprocess_when_changed_without_auto_enabling():
    p=plugin({'preload':{'settings':dict(patterns='Special/Resource',limit=3)}})
    s=snapshot('Special/ResourceOne','Different/ResourceTwo');p.scan(s,1.)
    assert not p.enabled and p.settings['limit']==3
    assert [r['label']for r in p.alert_rows()]==['ResourceOne']
    p.settings['patterns']='Different/'
    p.scan(s,1.01)
    assert [r['label']for r in p.alert_rows()]==['ResourceTwo']


def test_resource_matching_is_incremental_and_throttled_between_drawing_frames():
    p=plugin();calls=[];match=p.matching_rules
    def count(resource):calls.append(resource);return match(resource)
    p.matching_rules=count
    s=snapshot('Metadata/Chests/StrongBoxes/Arcanist');p.scan(s,1.)
    assert len(calls)==1
    s.preloads.append('Metadata/Chests/StrongBoxes/Diviner');p.scan(s,1.1)
    assert len(calls)==1
    p.scan(s,1.3)
    assert len(calls)==2 and len(p.alert_rows())==2
    p.scan(s,1.6)
    assert len(calls)==2


def test_towns_hide_the_panel_and_module_stop_discards_previous_detections():
    p=plugin();s=snapshot('Metadata/Chests/StrongBoxes/Diviner');s.town=True
    assert not p.tick(s,object())
    p.settings['show_in_town']=True
    assert p.tick(s,object())[0].kind=='preload_panel'
    p.stop()
    assert not p.alert_rows()
