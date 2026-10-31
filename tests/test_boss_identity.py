import struct

import pytest

from exile.reader import Reader


class BossReader(Reader):
    def __init__(self,names):
        super().__init__({'offsets':dict(monster_mod_vectors=[0x150,0x168],monster_mod_record_size=56,
                                       monster_mod_definition=40,monster_mod_id=0),
                          'map_boss_modifiers':['MonsterMapBoss']})
        self.names=names;self.ownership=[];self.changed=False;self.memory=self
    def owned_component(self,component,owner,size):
        assert component==0x1000 and owner==0x2000
        self.ownership.append(size)
        return bytes(size)
    def vector(self,address,stride,limit):
        assert stride==56 and limit==256
        ids=list(self.names) if address==0x1168 else []
        raw=bytearray(len(ids)*56)
        for index,pointer in enumerate(ids):struct.pack_into('<Q',raw,index*56+40,pointer)
        return raw
    def q(self,address):return address
    def utf16(self,address,length=None,maximum=256):return self.names[address]
    def read(self,address,size):return bytes([1])*size if self.changed else bytes(size)


def test_map_boss_modifier_is_required_and_checked_by_exact_identifier():
    boss=BossReader({0x3000:'ShavronneTornadoDaemon',0x4000:'MonsterMapBoss',0x5000:'StunRepeatImmunityMapBoss_'})
    assert boss.monster_boss(0x1000,0x2000) is True
    assert boss.ownership==[0x180,16]
    for mods in ({0x3000:'MonsterUnique1'},{0x3000:'MonsterMapBossUnderling'},{}):
        assert BossReader(mods).monster_boss(0x1000,0x2000) is False
    boss.changed=True
    with pytest.raises(ValueError,match='changed'):boss.monster_boss(0x1000,0x2000)


def test_unverified_layout_does_not_claim_boss_identity():
    reader=Reader({'offsets':{}})
    assert reader.monster_boss(0x1000,0x2000) is None
