import struct

import pytest

from exile.reader import Reader, contained_rect, project, unpack_terrain, usable_vital
from exile.economy import Economy


def test_collision_nibbles_ignore_odd_row_padding():
    assert unpack_terrain(bytes([0x21, 0xf3, 0x50, 0xf4]), 3, 2, 2) == [bytes([1, 2, 3]), bytes([0, 5, 4])]
    with pytest.raises(ValueError):
        unpack_terrain(bytes([0x61]), 2, 1, 1)
    with pytest.raises(ValueError):
        unpack_terrain(bytes([0x21]), 3, 1, 2)


def test_reservation_rounding_and_invalid_data():
    assert usable_vital(700, 0, 9440) == 39
    assert usable_vital(2802, 0, 0) == 2802
    with pytest.raises(ValueError):
        usable_vital(700, 0, 10001)


def test_projection_rejects_behind_camera_and_nonfinite_values():
    matrix = [1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1.]
    assert project(matrix, (0, 0, 0), 1920, 1080) == (960, 540)
    matrix[15] = -1
    assert project(matrix, (0, 0, 0), 1920, 1080) is None
    matrix[15] = float('nan')
    assert project(matrix, (0, 0, 0), 1920, 1080) is None


def test_vector_rejects_unbounded_or_misaligned_allocations():
    class Memory:
        def read(self, address, size):
            assert size == 24  # Invalid payloads must never be fetched.
            return struct.pack('<QQQ', 0x1000, 0x1009, 0x2000)
    reader = Reader({'offsets': {}})
    reader.memory = Memory()
    with pytest.raises(ValueError):
        reader.vector(100)


def test_stash_estimates_keep_unknown_corruption_variants(tmp_path, monkeypatch):
    economy = Economy(tmp_path)
    monkeypatch.setattr(economy, 'currency_prices', lambda league: ({'divine orb': 300}, 123))
    monkeypatch.setattr(economy, 'get', lambda endpoint: ({'lines': [
        {'name': 'Example', 'baseType': 'Ring', 'chaosValue': 10, 'corrupted': False},
        {'name': 'Example', 'baseType': 'Ring', 'chaosValue': 30, 'corrupted': True},
        {'name': 'Example', 'baseType': 'Ring', 'chaosValue': 90, 'links': 6},
    ]}, 123))
    item = dict(name='Example', base='Ring', rarity=3, links=0, corrupted=None)
    result = economy.stash_prices([item], 'Example league')
    assert result['estimates'][('Example', 'Ring', 0, None)] == '10c–30c'


def test_currency_stash_anchors_to_parent_slot_and_clears_when_closed():
    class LayoutReader(Reader):
        def __init__(self):
            super().__init__({'offsets': dict(state_ui=8, ui_stash=16, ui_guild_stash=24,
                                             ui_item=32, ui_children=40, ui_parent=48,
                                             currency_inventory_type=18)})
            self.closed = False

        def q(self, address):
            return {108: 200, 216: 0, 224: 300, 332: 0, 432: 900, 448: 500}.get(address, 0)

        def vector(self, address, **kwargs):
            return struct.pack('<Q', 400) if address == 340 else b''

        def element_rect(self, address, viewport):
            return None if self.closed else {300: (0, 0, 666, 1080),
                                             400: (4372, 381, 42, 42),
                                             500: (35, 381, 42, 42)}.get(address)

    reader = LayoutReader()
    item = dict(entity=900, scope='guild', inventory_type=18)
    reader.stash_layout(100, [item], (1920, 1080))
    assert item['visible'] and item['screen'] == (35, 381)
    reader.closed = True
    reader.stash_layout(100, [item], (1920, 1080))
    assert not item['visible'] and 'screen' not in item


def test_stash_clipping_rejects_offscreen_and_partial_items():
    assert contained_rect((35, 381, 42, 42), (0, 0, 666, 1080), (1920, 1080))
    assert not contained_rect((4372, 381, 42, 42), (0, 0, 666, 1080), (1920, 1080))
    assert not contained_rect((650, 381, 42, 42), (0, 0, 666, 1080), (1920, 1080))


def test_short_item_names_use_inline_native_string():
    raw = bytearray(32)
    raw[:14] = 'Disdain'.encode('utf-16-le')
    struct.pack_into('<QQ', raw, 16, 7, 7)
    class Memory:
        def read(self, address, count):
            assert address == 100
            return bytes(raw[:count])
    reader = Reader({'offsets': {}})
    reader.memory = Memory()
    assert reader.native_string(100) == 'Disdain'


def test_personal_tab_uses_inventory_id_instead_of_tab_index():
    class PersonalReader(Reader):
        def __init__(self):
            super().__init__({'offsets': dict(server_data=1, personal_tabs=2, guild_tabs=3,
                personal_inventories=4, guild_inventories=5, stash_tab_size=104,
                stash_tab_name=8, stash_tab_inventory_id=40, inventory_type=8,
                inventory_slot_delta=4, flask_inventory_type=10, stash_inventory_slot=26)})
            self.memory = self
        def q(self, address):
            return 1000 if address == 102 else 100
        def vector(self, address, **kwargs):
            if address != 102:
                return b''
            raw = bytearray(208)
            struct.pack_into('<I', raw, 104 + 40, 158)
            return bytes(raw)
        def native_string(self, address):
            return '$' if address == 1112 else 'Shop'
        def inventory_holders(self, server, offset):
            return [(158, 200)] if offset == 4 else []
        def read(self, address, count):
            return bytes([18, 0, 0, 0, 26, 0, 0, 0])
        def inventory_slots(self, inventory):
            return [(900, 1, 2, 1, 1)]
        def item_summary(self, entity):
            return dict(name='Orb of Augmentation', components={})
    items, tabs = PersonalReader().inventories(1, 'area')
    assert len(items) == 1 and items[0]['tab'] == '$' and items[0]['tab_index'] == 1
    assert [tab['name'] for tab in tabs if tab['loaded']] == ['$']
