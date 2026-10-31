from pathlib import Path
import time

from exile.model import Snapshot
from exile.plugins import PluginManager
from exile.valuation import enrich_items,summarize,quote_key


def currency(entity,name,quantity=1,scope='inventory',**extra):
    return dict(entity=entity,name=name,base=name,metadata='Metadata/Items/Currency/'+name,
                rarity=0,links=0,corrupted=None,quantity=quantity,stackable=True,scope=scope,**extra)


def plugin():
    manager=PluginManager(Path(__file__).parents[1]/'plugins');manager.discover()
    return next(p for p in manager.plugins if p.id=='pricing')


def test_stack_totals_and_top_three_merge_before_ranking_and_count_each_entity_once():
    items=[currency(1,'Chaos Orb',20),currency(2,'Chaos Orb',20),currency(3,'Chaos Orb',20),
           currency(4,'Vaal Orb',10),currency(5,'Divine Orb',20),
           dict(entity=6,name='Unknown rare',rarity=2,quantity=1)]
    enrich_items(items,{'chaos orb':1,'vaal orb':.3213,'divine orb':339},{})
    report=summarize(items+[items[0]],339)
    assert report['total_low']==6780+60+3.213
    assert report['unknown']==1 and report['priced']==5
    assert [r['name']for r in report['top']]==['Divine Orb','Chaos Orb','Vaal Orb']
    assert report['top'][1]['quantity']==60 and report['top'][1]['stacks']==3
    assert items[3]['price_label']=='3c'


def test_unique_ranges_are_numeric_and_nonstackable_variants_are_not_merged():
    items=[dict(entity=i,name='Example unique',base='Ring',rarity=3,links=0,quantity=1,corrupted=None)for i in (1,2)]
    quotes={quote_key(items[0]):dict(low=100,high=200)}
    enrich_items(items,{},quotes);report=summarize(items)
    assert report['total_low']==200 and report['total_high']==400
    assert report['total_label']=='200c–400c'and len(report['top'])==2


def test_missing_and_removed_quotes_do_not_become_zero_value_items():
    items=[currency(1,'Vaal Orb',10)]
    enrich_items(items,{'vaal orb':.3},{})
    assert items[0]['price_label']=='3c'
    enrich_items(items,{},{})
    assert 'price_label'not in items[0]
    assert summarize(items)['total_label']==''
    assert summarize([])['total_label']=='0c'
    rare=dict(name='Chaos Orb',base='Ring',metadata='Metadata/Items/Rings/Ring1',rarity=2,quantity=1)
    enrich_items([rare],{'chaos orb':1},{})
    assert 'price_label'not in rare  # a name collision cannot price rare equipment


def test_inventory_and_tab_summaries_are_separate_and_stash_search_does_not_change_totals():
    p=plugin()
    p.settings.update(stash_query='no matches',stash_scope='Guild')
    backpack=[currency(1,'Chaos Orb',20),currency(2,'Chaos Orb',20)]
    stash=[currency(3,'Chaos Orb',30,'personal',tab='Currency',tab_index=2,visible=True),
           currency(4,'Chaos Orb',40,'personal',tab='Currency',tab_index=2),
           currency(5,'Chaos Orb',999,'personal',tab='Other',tab_index=3),
           currency(6,'Chaos Orb',100,'guild',tab='Shared',tab_index=2)]
    enrich_items(backpack+stash,{'chaos orb':1},{})
    s=Snapshot(source='preview',inventory=backpack,inventory_loaded=True,stash=stash,
               item_panels=[dict(scope='inventory'),dict(scope='personal')])
    sections=p.tick(s,object())[-1].payload['sections']
    assert [r['total_label']for r in sections]==['40c','70c']
    assert sections[1]['top'][0]['quantity']==70
    s.item_panels=[dict(scope='guild')];stash[-1]['visible']=True
    sections=p.tick(s,object())[-1].payload['sections']
    assert sections[-1]['total_label']=='100c'


def test_price_labels_follow_only_visible_ground_boxes_and_inventory_slots():
    p=plugin();ground=[currency(1,'Vaal Orb',10,visible=True,rect=(100,100,160,38)),
                      currency(2,'Chaos Orb',1,visible=False,rect=(200,200,50,20))]
    inventory=[currency(3,'Chaos Orb',20,visible=True,rect=(400,300,40,40))]
    enrich_items(ground+inventory,{'chaos orb':1,'vaal orb':.3},{})
    s=Snapshot(source='preview',ground_items=ground,inventory=inventory,inventory_loaded=True,item_panels=[dict(scope='inventory')])
    badges=[m for m in p.tick(s,object())if m.kind=='item_price']
    assert [(m.text,m.x,m.y)for m in badges]==[('3c',100,100),('20c',400,300)]
    s.source='live';s.in_game=True;s.loading=False;s.captured_at=time.monotonic()-1
    assert not p.tick(s,object())


def test_combined_module_migrates_stash_preferences_without_overwriting_new_settings():
    saved={'stash':{'settings':dict(query='Chaos',scope='Guild',prices=False,names=True)},
           'pricing':{'settings':dict(stash_scope='Personal',summary_positions={'inventory':[.2,.3]})}}
    manager=PluginManager(Path(__file__).parents[1]/'plugins',saved);manager.discover()
    assert not manager.errors and len(manager.plugins)==8
    assert not any(p.id=='stash'or p.enabled for p in manager.plugins)
    p=next(p for p in manager.plugins if p.id=='pricing')
    assert p.settings['stash_query']=='Chaos'and p.settings['stash_scope']=='Personal'
    assert p.settings['stash_prices']is False and p.settings['stash_names']is True
    assert p.settings['summary_positions']=={'inventory':[.2,.3]}
    restored=PluginManager(manager.directory,manager.serialize());restored.discover()
    assert next(p for p in restored.plugins if p.id=='pricing').settings==p.settings


def test_combined_stash_overlay_filters_only_visible_matches_and_switches_independently():
    p=plugin();p.settings.update(stash_query='Currency',stash_scope='Personal')
    items=[currency(i,'Chaos Orb',20,scope,tab='Currency',visible=visible,screen=(10,20),rect=(10,20,40,40))
           for i,scope,visible in ((1,'personal',True),(2,'guild',True),(3,'personal',False))]
    enrich_items(items,{'chaos orb':1},{})
    s=Snapshot(source='preview',stash=items,item_panels=[dict(scope='personal')])
    marks=p.tick(s,object())
    assert [m.kind for m in marks]==['slot','price','wealth_panel']
    assert marks[1].text=='20c'
    p.settings['stash_prices']=False
    assert [m.kind for m in p.tick(s,object())]==['slot','wealth_panel']
    p.settings['stash_overlay']=False
    assert [m.kind for m in p.tick(s,object())]==['wealth_panel']

def test_unidentified_unique_base_alternatives_share_all_container_prices(tmp_path):
    from exile.economy import Economy
    from exile.valuation import enrich_items,quote_key
    economy=Economy(tmp_path)
    economy.currency_prices=lambda league,category='Currency':({'chaos orb':1,'divine orb':300},123)
    economy.get=lambda path:({'lines':[
        dict(name='Unique A',baseType='Spidersilk Robe',chaosValue=2),
        dict(name='Unique B',baseType='Spidersilk Robe',chaosValue=4),
        dict(name='Wrong base',baseType='Silk Robe',chaosValue=100),
        dict(name='Six link',baseType='Spidersilk Robe',chaosValue=500,links=6)]} if 'UniqueArmour' in path else {'lines':[]},123)
    item=dict(name='Spidersilk Robe',base='Spidersilk Robe',rarity=3,links=0,quantity=1)
    result=economy.stash_prices([item],'Test league')
    enrich_items([item],result['currencies'],result['quotes'])
    assert item['price_label']=='2c / 4c'
    assert (item['value_low'],item['value_high'])==(2,4)
    identified=dict(item,name='Unique A')
    result=economy.stash_prices([identified],'Test league')
    assert 'alternatives' not in result['quotes'][quote_key(identified)]
    enrich_items([identified],result['currencies'],result['quotes'])
    assert identified['price_label']=='2c'

def test_art_filter_uses_source_asset_and_preserves_unverified_variants():
    import base64,json
    from exile.economy import matching_art
    from exile.valuation import quote_key
    def line(asset,mutated=False):
        payload=base64.urlsafe_b64encode(json.dumps([25,14,dict(f=asset,mutated=mutated)]).encode()).decode().rstrip('=')
        return dict(icon='https://web.poecdn.com/gen/image/'+payload+'/hash/image.png')
    item=dict(name='Spidersilk Robe',base='Spidersilk Robe',art='Art/2DItems/Armours/BodyArmours/SoulMantle.dds')
    assert matching_art(item,line('2DItems/Armours/BodyArmours/SoulMantle'))
    assert matching_art(item,line('2DItems/Armours/BodyArmours/SoulMantle',True))
    assert not matching_art(item,line('2DItems/Armours/BodyArmours/Embrace'))
    assert matching_art(item,dict(icon='unknown'))
    assert quote_key(item)!=quote_key(dict(item,art=''))

def test_foulborn_unknown_candidates_follow_location_without_stale_totals():
    from exile.valuation import enrich_items,quote_key
    item=dict(name='Spidersilk Robe',base='Spidersilk Robe',rarity=3,quantity=1)
    quotes={quote_key(item):dict(low=1,high=100,alternatives=[dict(name='Soul Mantle',low=1,high=1),dict(name='Foulborn Soul Mantle',low=100,high=100)])}
    for area in ('The Monastery of the Keepers','Hive Colony','The Hive Fortress'):
        enrich_items([item],{},quotes,area=area)
        assert item['price_label']=='1c / 100c' and item['value_high']==100
    for area in ('The Southern Forest','Hideout','Hive Colony Annex',''):
        enrich_items([item],{},quotes,area=area)
        assert item['price_label']=='1c' and item['value_high']==1
    assert len(quotes[quote_key(item)]['alternatives'])==2
    quotes[quote_key(item)]['alternatives']=quotes[quote_key(item)]['alternatives'][1:]
    enrich_items([item],{},quotes,area='Hideout')
    assert 'price_label' not in item and 'value_high' not in item
    known=dict(name='Foulborn Soul Mantle',base='Spidersilk Robe',rarity=3,quantity=1)
    enrich_items([known],{},{quote_key(known):dict(low=100,high=100)},area='Hideout')
    assert known['price_label']=='100c'

def test_direct_foulborn_detection_uses_owned_explicit_mod_ids():
    import struct
    from exile.reader import Reader
    r=Reader({'offsets':dict(item_explicit_mods=216,item_mod_size=56,item_mod_definition=40,item_mod_id=0)})
    header=bytes(240);r.owned_component=lambda *args:header
    r.memory=type('Memory',(),{'read':lambda self,address,size:bytes(size)})()
    r.q=lambda address:address
    identifiers={100:'IncreasedCastSpeedUniqueAmulet20',200:'MutatedUniqueAmulet20CurseEffectTemporalChains'}
    r.utf16=lambda address:identifiers[address]
    def records(pointers):
        raw=bytearray(56*len(pointers))
        for index,pointer in enumerate(pointers):struct.pack_into('<Q',raw,index*56+40,pointer)
        return bytes(raw)
    r.vector=lambda *args,**kwargs:records([100,200])
    assert r.item_variant(1000,2000)==(True,list(identifiers.values()))
    r.vector=lambda *args,**kwargs:records([100])
    assert r.item_variant(1000,2000)==(False,[identifiers[100]])
    r.vector=lambda *args,**kwargs:b''
    assert r.item_variant(1000,2000)==(None,[])


def test_direct_foulborn_evidence_overrides_area_fallback_and_quote_identity(tmp_path):
    from exile.economy import Economy
    from exile.valuation import quote_key,enrich_items
    economy=Economy(tmp_path)
    economy.currency_prices=lambda *args:({'chaos orb':1},123)
    economy.get=lambda path:({'lines':[dict(name='Warped Timepiece',baseType='Turquoise Amulet',chaosValue=1),dict(name='Foulborn Warped Timepiece',baseType='Turquoise Amulet',chaosValue=100)]}if 'UniqueAccessory'in path else {'lines':[]},123)
    item=dict(name='Warped Timepiece',base='Turquoise Amulet',links=0,rarity=3,quantity=1,foulborn=True)
    result=economy.stash_prices([item],'Test')
    enrich_items([item],{},result['quotes'],area='Hideout')
    assert item['price_label']=='100c'
    normal=dict(item,foulborn=False)
    assert quote_key(normal)!=quote_key(item)
    result=economy.stash_prices([normal],'Test')
    enrich_items([normal],{},result['quotes'],area='Monastery of the Keepers')
    assert normal['price_label']=='1c'


def test_unidentified_visual_identity_distinguishes_replica_and_preserves_unknowns(tmp_path):
    from exile.economy import Economy
    from exile.valuation import quote_key,enrich_items
    economy=Economy(tmp_path)
    economy.currency_prices=lambda *args:({'chaos orb':1},123)
    economy.get=lambda path:({'lines':[dict(name="Poorjoy's Asylum",baseType='Map (Tier 16)',chaosValue=5),dict(name="Replica Poorjoy's Asylum",baseType='Map (Tier 16)',chaosValue=700)]} if 'UniqueMap' in path else {'lines':[]},123)
    base=dict(name='Map (Tier 16)',base='Map (Tier 16)',rarity=3,identified=False,links=0,quantity=1)
    regular=dict(base,visual_identity='UniqueMap5')
    replica=dict(base,visual_identity='UniqueMap5x')
    unknown=dict(base,visual_identity='not_in_dataset')
    items=[regular,replica,unknown]
    result=economy.stash_prices(items,'Test')
    enrich_items(items,result['currencies'],result['quotes'])
    assert [item['price_label'] for item in items]==['5c','700c','5c / 700c']
    assert len({quote_key(item) for item in items})==3

def test_ambiguous_visual_identity_retains_all_names(tmp_path):
    from exile.economy import Economy
    from exile.valuation import enrich_items
    economy=Economy(tmp_path)
    economy.currency_prices=lambda *args:({},123)
    economy.get=lambda path:({'lines':[dict(name='Redbeak',baseType='Sword',chaosValue=2),dict(name='Dreadbeak',baseType='Sword',chaosValue=4)]} if 'UniqueWeapon' in path else {'lines':[]},123)
    item=dict(name='Sword',base='Sword',rarity=3,identified=False,visual_identity='UniqueOneHandSword1',links=0,quantity=1)
    result=economy.stash_prices([item],'Test');enrich_items([item],{},result['quotes'])
    assert item['price_label']=='2c / 4c'
