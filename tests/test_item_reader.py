import struct

import pytest

from exile.reader import Reader


def test_carried_items_exclude_equipment_flasks_and_other_containers():
    class InventoryReader(Reader):
        def __init__(self):
            super().__init__({'offsets':dict(server_data=8,personal_inventories=16,inventory_type=0,
                inventory_slot_delta=4,main_inventory_type=0,main_inventory_slots=[0,84])})
            self.memory=self
        def q(self,address):return 100
        def inventory_holders(self,*args):return list(enumerate((1000,2000,3000,4000,5000)))
        def read(self,address,count):
            kind,slot={1000:(0,0),2000:(1,1),3000:(10,11),4000:(0,84),5000:(0,54)}[address]
            raw=bytearray(8);raw[0]=kind;raw[4]=slot;return raw
        def inventory_slots(self,inventory):return [(inventory+1,0,0,1,1)]
        def item_summary(self,entity,assessment=False):return dict(entity=entity,name='Currency',quantity=1,components={})
    reader=InventoryReader()
    items=reader.carried_items(1,'zone')
    assert [i['entity']for i in items]==[1001,4001]
    assert reader.carried_loaded and all(i['scope']=='inventory'for i in items)
    assert reader.carried_items(1,'zone')is items


def test_ground_labels_use_the_world_item_entity_and_discard_replaced_labels():
    class GroundReader(Reader):
        def __init__(self):
            super().__init__({'offsets':dict(state_ui=8,ui_ground_labels=16,ground_label_head=24,
                ground_label_next=0,ground_label_world=24,ground_label_element=16,world_item_entity=40)})
            self.memory=self;self.replaced=False;self.cycle=False
        def q(self,address):
            return {108:200,216:300,324:400,400:500,524:600,516:0 if self.replaced else 700}.get(address,0)
        def read(self,address,count):
            assert address==500 and count==40
            raw=bytearray(40)
            struct.pack_into('<Q',raw,0,500 if self.cycle else 400)
            struct.pack_into('<Q',raw,16,700);struct.pack_into('<Q',raw,24,600)
            return raw
        def element_rect(self,address,viewport):
            assert address==700
            return 100,200,160,38
        def components(self,address):
            assert address==600
            return {'WorldItem':800}
        def owned_component(self,component,owner,count):
            assert component==800 and owner==600
            raw=bytearray(count);struct.pack_into('<Q',raw,40,900);return raw
        def item_summary(self,entity):
            assert entity==900
            return dict(entity=entity,name='Vaal Orb',quantity=10,components={})
    reader=GroundReader()
    assert reader.ground_labels(100,(1920,1080))[0]['quantity']==10
    reader.replaced=True
    assert not reader.ground_labels(100,(1920,1080))
    reader.cycle=True
    with pytest.raises(ValueError,match='list'):reader.ground_labels(100,(1920,1080))
