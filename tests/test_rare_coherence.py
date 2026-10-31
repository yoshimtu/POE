import json
from pathlib import Path

import pytest

from exile.items import Item,rate_rare,item_from_hover,parse_item


def rare(mods,item_class='Rings',tier=1):
    info={mod:dict(tier=tier,affix=f'{{ Prefix Modifier "Affix {index}" (Tier: {tier}) }}')for index,mod in enumerate(mods)}
    return Item('Rare','Anonymous','Anonymous base',item_class,mods=list(mods),mod_info=info)


@pytest.mark.parametrize('mods,slot,fit',[
    (['170% increased Physical Damage','27% increased Attack Speed','+38% to Global Critical Strike Multiplier'],'Swords','Attack'),
    (['100% increased Spell Damage','32% increased Cast Speed','+38% to Global Critical Strike Multiplier'],'Wands','Spell'),
    (['+200 to maximum Energy Shield','100% increased maximum Energy Shield'],'Body Armours','Energy shield'),
    (['Minions deal 42% increased Damage','Minions have 16% increased Attack and Cast Speed','Minions have 29% increased Movement Speed'],'Rings','Minion'),
    (['+26% to Fire Damage over Time Multiplier','+1 to Level of all Fire Skill Gems','80% increased Fire Damage'],'Amulets','Damage over time'),
    (['+55 to Strength','12% increased Strength'],'Rings','Attribute stacking'),
    (['+100 to maximum Mana','12% increased maximum Mana','70% increased Mana Regeneration Rate'],'Rings','Mana'),
])
def test_multiple_build_families_choose_coherent_profiles_without_item_name_rules(mods,slot,fit):
    item=rare(mods,slot);result=rate_rare(item)
    assert result['assessment']['best_fit']==fit
    assert result['assessment']['coherent_affixes']>=2
    assert result['assessment']['coherence_bonus']>0 and result['assessment']['tier_bonus']>0
    item.name='Some completely different item';item.base='Another base name'
    assert rate_rare(item)['score']==result['score']


def test_unrelated_t1_rolls_do_not_equal_coherent_t1s_and_filler_does_not_help():
    good=rare(['Minions deal 42% increased Damage','Minions have 16% increased Attack and Cast Speed',
               'Minions have 29% increased Movement Speed'])
    unrelated=rare(['Minions deal 42% increased Damage','100% increased Spell Damage','170% increased Physical Damage'])
    g,b=rate_rare(good),rate_rare(unrelated)
    assert g['score']>=b['score']+2
    assert g['assessment']['tier_bonus']>0 and b['assessment']['tier_bonus']==0
    before=g['score'];good.mods+=['15% increased Light Radius','24% increased Stun and Block Recovery']
    assert rate_rare(good)['score']==before


def test_tiers_and_actual_rolls_both_matter_without_promoting_low_value_t1s():
    mods=['Minions deal 42% increased Damage','Minions have 16% increased Attack and Cast Speed',
          'Minions have 29% increased Movement Speed']
    assert rate_rare(rare(mods,tier=1))['score']>rate_rare(rare(mods,tier=4))['score']
    low=rare(['Minions deal 37% increased Damage','Minions have 14% increased Attack and Cast Speed',
              'Minions have 26% increased Movement Speed'])
    assert rate_rare(rare(mods))['score']>rate_rare(low)['score']
    filler=rare(['15% increased Light Radius','24% increased Stun and Block Recovery'])
    assert rate_rare(filler)['score']==1


def test_live_ring_uses_scaled_mods_and_separate_enchant_and_outscores_chest_affixes():
    root=Path(__file__).parent/'fixtures'
    ring=item_from_hover(json.loads((root/'onslaught_hover.json').read_text()))
    chest=item_from_hover(json.loads((root/'brood_ward_hover.json').read_text()))
    r,c=rate_rare(ring),rate_rare(chest)
    assert len(ring.mods)==6 and len(ring.special_mods)==2 and not r['unknown']
    assert 'Minions have 16% increased Attack and Cast Speed'in ring.mods
    assert any(m['source']=='Enchant'for m in ring.special_mods)
    assert r['score']>=c['score']+2 and r['assessment']['best_fit']=='Minion'
    assert c['score']==round(min(10,c['affix_score']+c['crafting']['bonus']),1)and c['link_notes']


def test_hybrid_affix_cannot_claim_two_independent_t1s_and_breakdown_adds_up():
    item=rare(['Minions deal 42% increased Damage','Minions have 16% increased Attack and Cast Speed'])
    independent=rate_rare(item,'Minion')
    item.mod_info[item.mods[1]]=dict(item.mod_info[item.mods[0]])
    hybrid=rate_rare(item,'Minion')
    assert hybrid['assessment']['strong_tier_affixes']==1
    assert hybrid['score']<independent['score']
    assert sum(row['contribution']for row in hybrid['evaluated'])==pytest.approx(hybrid['assessment']['base_points'],abs=.002)


def test_non_numeric_affixes_are_evaluated_or_flagged_for_review():
    item=parse_item('''Item Class: Boots
Rarity: Rare
Example
Greaves
--------
{ Suffix Modifier "Winter" }
Cannot be Frozen
{ Prefix Modifier "Unknown" }
This unusual modifier needs investigation
''')
    result=rate_rare(item)
    assert any(r['category']=='Freeze immunity'for r in result['evaluated'])
    assert result['unknown']==['This unusual modifier needs investigation']


def test_combined_display_lines_do_not_double_two_affixes_or_lose_their_tiers():
    data=dict(name='Example',base='Plate',metadata='Metadata/Items/Armours/BodyArmours/Example',
        tooltip_rows=['+120 to maximum Life\n+42% to Fire Resistance',
            'Prefix Modifier "First" (Tier: 1)\n+60(50-60) to maximum Life',
            'Prefix Modifier "Second" (Tier: 2)\n+60(55-65) to maximum Life',
            'Suffix Modifier "Resistance" (Tier: 2)\n+42(40-45)% to Fire Resistance'])
    item=item_from_hover(data);rating=rate_rare(item)
    assert item.mods.count('+60 to maximum Life')==2
    assert '+120 to maximum Life'not in item.mods
    life=[r for r in rating['evaluated']if r['category']=='Life']
    assert [r['tier']for r in life]==[1,2]
    assert life[0]['affix']!=life[1]['affix']
