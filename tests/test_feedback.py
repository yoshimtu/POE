from exile.prices import format_price
from exile.items import parse_item, rate_rare
from exile.mapview import map_point
from exile.model import Snapshot
from exile.economy import Economy
from pathlib import Path
from exile.reader import unpack_terrain


def test_price_threshold_and_no_chaos_decimals():
    assert format_price(100.4, 300) == '100c'
    assert format_price(100.5, 300) == '101c'
    assert format_price(3000, 300) == '3000c'
    assert format_price(3003, 300) == '10.01d'
    assert format_price(30000, 300) == '100d'
    assert format_price(3750, 300) == '12.5d'
    assert format_price(3200) == '3200c'


def test_advanced_copy_roll_ranges_can_be_rated():
    item = parse_item('''Item Class: Boots
Rarity: Rare
Storm Road
Titan Greaves
--------
Item Level: 85
--------
{ Prefix Modifier "Healthy" (Tier: 1) — Life }
+110(100-120) to maximum Life
{ Suffix Modifier — Resistance }
+44(42-48)% to Fire Resistance
30(25-35)% increased Movement Speed
''')
    assert item.mods == ['+110 to maximum Life', '+44% to Fire Resistance', '30% increased Movement Speed']
    assert rate_rare(item)['score'] > 5


def test_unique_category_falls_back_for_aegis(tmp_path):
    item = parse_item('''Item Class: Shields
Rarity: Unique
Aegis Aurora
Champion Kite Shield
--------
Sockets: R-W-G
''')
    economy = Economy(tmp_path)
    economy.get = lambda path: ({'lines': [{'name': 'Aegis Aurora', 'baseType': 'Champion Kite Shield', 'chaosValue': 50}]
                                if 'UniqueArmour' in path else []}, 123)
    assert economy.unique(item, 'Example league', 'UniqueWeapon')['candidates'][0]['chaosValue'] == 50


def test_native_map_hides_when_closed_and_tracks_center_zoom():
    snapshot = Snapshot(source='live')
    assert map_point(snapshot, (2, 3)) is None
    snapshot.map_transform = dict(player=(2, 3), center=(960, 520), basis_x=.6225, basis_y=-.4987)
    assert map_point(snapshot, (2, 3)) == (960, 520)
    assert map_point(snapshot, (3, 3)) == (960.6225, 519.5013)
    snapshot.map_transform['center'] = (1000, 550)
    assert map_point(snapshot, (2, 3)) == (1000, 550)


def test_reported_minion_ring_modifiers_and_context():
    item = parse_item((Path(__file__).parent / 'fixtures/onslaught_ring.txt').read_text())
    result = rate_rare(item, 'Minion')
    assert len(item.mods) == 6
    assert not result['unknown']
    assert len(item.special_mods) == 2
    evaluated = {row['category']: row for row in result['evaluated']}
    assert evaluated['Minion damage']['tier'] == 1
    assert evaluated['Minion attack & cast speed']['tier'] == 1
    assert evaluated['Minion movement speed']['impact'] == 'Contributes'
    assert 'Elemental & chaos resistance' in evaluated
    assert 'Item rarity' in evaluated
    assert any('minion damage' in x for x in result['reasons'])


def test_neutral_mod_does_not_raise_rating():
    item = parse_item('Item Class: Rings\nRarity: Rare\nExample\nIron Ring\n--------\n+100 to maximum Life')
    before = rate_rare(item)['score']
    item.mods.append('10% increased Light Radius')
    result = rate_rare(item)
    assert result['score'] == before
    assert result['evaluated'][-1]['impact'] == 'No score increase'


def test_beacon_width_is_supported_with_allocation_bounds():
    grid = unpack_terrain(bytes([0x11]) * 1863, 3726, 1, 1863)
    assert len(grid[0]) == 3726
