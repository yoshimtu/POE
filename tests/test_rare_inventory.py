from exile.rare_inventory import assessment_rows,rating_for_item

def test_exact_rolls_and_unknown_modifier_are_fail_safe():
    rows=assessment_rows([dict(id='ColdResist8',values=[47],section='explicit'),dict(id='IncreasedLife9',values=[135],section='explicit')])
    assert '+47% to Cold Resistance' in rows[0] and '+135 to maximum Life' in rows[1]
    assert assessment_rows([dict(id='ColdResist8',values=[49],section='explicit')]) is None
    assert assessment_rows([dict(id='UnknownFutureMod',values=[10],section='explicit')]) is None

def test_inventory_score_uses_actual_mods_and_rejects_unidentified_or_non_equipment():
    item=dict(name='Armageddon Shelter',base='Pig-Faced Bascinet',metadata='Metadata/Items/Armours/Helmets/HelmetStrDex9',rarity=2,identified=True,links=0,sockets=4,
              assessment_mods=[dict(id='ColdResist8',values=[47],section='explicit'),dict(id='ChaosResist5',values=[29],section='explicit'),dict(id='IncreasedLife9',values=[135],section='explicit')])
    score=rating_for_item(item,'General');assert isinstance(score,(int,float)) and score>1
    assert rating_for_item(dict(item,identified=False),'General') is None
    assert rating_for_item(dict(item,metadata='Metadata/Items/Deepwater/ChartCoralForest'),'General') is None
    assert rating_for_item(dict(item,assessment_mods=item['assessment_mods']+[dict(id='UnknownMod',values=[1],section='explicit')]),'General') is None

def test_badge_only_appears_for_visible_inventory_when_enabled():
    import importlib.util
    from pathlib import Path
    from exile.model import Snapshot
    spec=importlib.util.spec_from_file_location('test_pricing_rare',Path('plugins/pricing/plugin.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    plugin=module.create_plugin();plugin.enabled=True
    item=dict(rarity=2,identified=True,visible=True,rect=(10,20,40,40),inventory_rating=7.3)
    snapshot=Snapshot(source='preview',inventory=[item],item_panels=[dict(scope='inventory')])
    marks=plugin.tick(snapshot,None)
    assert [m.text for m in marks if m.kind=='item_price']==['7.3']
    snapshot.item_panels=[];assert not [m for m in plugin.tick(snapshot,None) if m.kind=='item_price']
    snapshot.item_panels=[dict(scope='inventory')];plugin.settings['inventory_rare_ratings']=False
    assert not [m for m in plugin.tick(snapshot,None) if m.kind=='item_price']


def test_negative_implicit_roll_translates_and_does_not_hide_rating():
    from exile.rare_inventory import assessment_rows
    mod=dict(id='WitherExpireSpeedEldritchImplicit2',values=[-14],section='implicit')
    assert 'Withered you Inflict expires 14% slower' in assessment_rows([mod])[0]

def test_inventory_tiers_match_advanced_bascinet_assessment():
    from exile.rare_inventory import modifier_tier,rating_for_item
    from exile.hover_assessment import assess_data
    metadata='Metadata/Items/Armours/Helmets/HelmetStrDex9'
    assert [modifier_tier(i,metadata) for i in ('LocalIncreasedArmourAndEvasion1','IncreasedLife9','ColdResist8','ChaosResist5')]==[7,1,1,2]
    records=[dict(id=i,values=[v],section='explicit') for i,v in [('LocalIncreasedArmourAndEvasion1',22),('IncreasedLife9',135),('ColdResist8',47),('ChaosResist5',29)]]
    base=dict(name='Example Helm',base='Pig-Faced Bascinet',metadata=metadata,rarity=2,identified=True,links=0,sockets=0,assessment_mods=records)
    hover=dict(base,tooltip_rows=['Prefix Modifier "Scrapper" (Tier: 7)\n22(15-26)% increased Armour and Evasion','Prefix Modifier "Fecund" (Tier: 1)\n+135(130-144) to maximum Life','Suffix Modifier "of Haast" (Tier: 1)\n+47(46-48)% to Cold Resistance','Suffix Modifier "of Exile" (Tier: 2)\n+29(26-30)% to Chaos Resistance'])
    assert rating_for_item(base,'General')==assess_data(hover,'General')[1]['score']==6.8


def test_eldritch_gloves_negative_roll_produces_rating():
    from exile.rare_inventory import rating_for_item
    mods=[('MinionDamageEldritchImplicit1',[16],'implicit'),('WitherExpireSpeedEldritchImplicit2',[-14],'implicit'),('ColdResist8',[47],'explicit'),('ChaosResist6',[31],'explicit'),('LightningResist7',[45],'explicit'),('IncreasedMana3',[25],'explicit'),('IncreasedLife7',[102],'explicit'),('EinharMasterMinionDamage1',[20],'explicit')]
    item=dict(name='Example Gloves',base='Legion Gloves',metadata='Metadata/Items/Armours/Gloves/GlovesStrInt7',rarity=2,identified=True,links=4,sockets=4,assessment_mods=[dict(id=i,values=v,section=s) for i,v,s in mods])
    assert rating_for_item(item,'General')==8.4
