import json
from pathlib import Path
import time
import struct

import pytest
from PySide6.QtWidgets import QApplication

from exile.hover_assessment import HoverAssessment,assess_data,hotkey_parts,panel_position
from exile.items import Item,parse_item,rate_rare,item_from_hover
from exile.model import Snapshot
from exile.platform import GameWindow
from exile.plugins import PluginManager
from exile.reader import Reader


def sample():
    data=json.loads((Path(__file__).parent/'fixtures/brood_ward_hover.json').read_text())
    data.update(entity=100,tooltip_rect=(1200,300,400,350))
    return data


def test_native_advanced_tooltip_keeps_six_links_tiers_hybrid_rolls_and_ignores_properties():
    item=item_from_hover(sample())
    assert item.links==6 and item.sockets==6 and item.item_class=='Body Armours'
    assert len(item.mods)==6 and not any('Armour:'in m for m in item.mods)
    assert item.mod_info['+46% to Fire Resistance']['tier']==1
    assert item.mod_info['+46% to Fire Resistance']['roll_position']==0
    rating=rate_rare(item)
    assert rating['links']==6 and rating['link_notes']
    assert rating['score']==round(min(10,rating['affix_score']+rating['crafting']['bonus']),1)
    item.links=0;item.sockets=0
    assert rate_rare(item)['score']==rating['score']  # socket utility never inflates affix quality
    assert any(r['impact']=='No score increase'for r in rating['evaluated']if 'Stun'in r['mod'])


def test_strong_coherent_affixes_and_slot_references_outscore_weak_high_tier_filler():
    good=Item('Rare','Good','Ring','Rings',mods=['Minions deal 42% increased Damage',
        'Minions have 16% increased Attack and Cast Speed','+89 to maximum Life','+46% to Fire Resistance'])
    weak=Item('Rare','Weak','Ring','Rings',mods=['+10 to maximum Life','+8% to Fire Resistance',
        '24% increased Stun and Block Recovery','15% increased Light Radius'])
    assert rate_rare(good)['score']>7
    assert rate_rare(good)['score']>rate_rare(weak)['score']+4
    assert any('minion'in reason for reason in rate_rare(good)['reasons']if reason.startswith('Synergy:'))
    flat=Item('Rare','Flat','Ring','Rings',mods=['Adds 6 to 12 Physical Damage','16% increased Attack Speed'])
    assert rate_rare(flat)['evaluated'][0]['strength']==1
    es=Item('Rare','ES','Ring','Rings',mods=['+51 to maximum Energy Shield'])
    assert rate_rare(es)['evaluated'][0]['strength']==1


def test_socket_count_is_not_link_count_and_unknown_mods_remain_reviewable():
    text='Item Class: Body Armours\nRarity: Rare\nExample\nPlate\n--------\nSockets: R-R-R-R-R-R\n--------\n+1 to mysterious powerful effect'
    item=parse_item(text);rating=rate_rare(item)
    assert item.sockets==6 and item.links==6
    assert rating['score']is None and rating['unknown']and rating['link_notes']
    item=parse_item(text.replace('R-R-R-R-R-R','R-R-R R-R-R'))
    assert item.sockets==6 and item.links==3
    assert 'not six-linked'in rate_rare(item)['link_notes'][0]


def test_shortcut_validation_and_placement():
    assert hotkey_parts('Alt+F')==(0x4001,ord('F'))
    assert hotkey_parts('Ctrl+Shift+F6')==(0x4006,0x75)
    for invalid in ('F','Alt+','Meta+F','Ctrl+Delete'):
        with pytest.raises(ValueError):hotkey_parts(invalid)
    from PySide6.QtCore import QRect
    assert panel_position(QRect(0,0,1920,1080),(1200,300,400,350),460,580)==(730,300)


def test_jewel_affixes_use_jewel_references_and_minion_combinations():
    item=Item('Rare','Jewel','Ghastly Eye Jewel','Abyss Jewels',mods=['+40 to maximum Life',
        'Minions deal 20% increased Damage', 'Minions have 8% increased Attack and Cast Speed',
        'Minions deal 20 to 30 additional Physical Damage'])
    result=rate_rare(item)
    assert not result['unknown']and result['score']>=7
    assert all(row['strength']==1 for row in result['evaluated'])


def test_native_reader_falls_back_to_styled_text_without_plain_cache():
    class StyledReader(Reader):
        def __init__(self):
            super().__init__({'offsets':dict(state_item_hover=8,ui_item=16,ui_tooltip_holder=24,
                ui_text_plain=32,ui_text_styled=48,ui_children=40)})
        def q(self,addr):return {108:200,216:300,224:400,400:500}.get(addr,0)
        def item_summary(self,entity):return dict(entity=entity,name='Rare',rarity=2,metadata='Metadata/Items/Armours/BodyArmours/Test',components={})
        def element_rect(self,*args):return(100,100,400,300)
        def native_string(self,address,maximum,**kwargs):
            return '<augmented>{+100 to maximum Life}\n<crafted>{+42% to Fire Resistance}'if address==548 else''
        def vector(self,*args,**kwargs):return b''
    data=StyledReader().hovered_item(100,(1920,1080))
    assert data['tooltip_rows']==['+100 to maximum Life\n+42% to Fire Resistance']


def test_real_string_decoder_allows_multiline_tooltips_without_loosening_other_reads():
    text='+100 to maximum Life\n+42% to Fire Resistance'
    class Memory:
        def read(self,address,count):
            if address==100:return struct.pack('<QQQQ',200,0,len(text),len(text)+1)
            assert address==200 and count==len(text)*2
            return text.encode('utf-16-le')
    reader=Reader({'offsets':{}});reader.memory=Memory()
    with pytest.raises(ValueError,match='characters'):reader.native_string(100)
    assert reader.native_string(100,multiline=True)==text


def test_hover_panel_modes_pinning_hide_and_zone_clear():
    app=QApplication.instance()or QApplication([])
    manager=PluginManager(Path(__file__).parents[1]/'plugins');manager.discover()
    p=next(p for p in manager.plugins if p.id=='pricing');p.enabled=True
    data=sample();s=Snapshot(source='live',in_game=True,loading=False,captured_at=time.monotonic(),hovered_item=data,area_id='zone')
    window=GameWindow(width=1920,height=1080,foreground=True);panel=HoverAssessment()
    try:
        panel.present(window,s,p);app.processEvents()
        assert panel.isVisible()and 'Brood'in panel.title.text()
        p.settings['rare_mode']='Hotkey only';panel.present(window,s,p);assert not panel.isVisible()
        panel.expand(dict(data,_area=('zone',None)),p.settings);panel.present(window,s,p)
        assert panel.isVisible()and not panel.close_button.isVisible()
        assert 'T1'in panel.body.text()and 'Six linked'in panel.body.text()
        panel.dismiss();panel.expand(dict(data,_area=('zone',None)),p.settings);panel.present(window,s,p)
        assert panel.isVisible()and panel.expanded  # same item can reopen after ×
        s.hovered_item=None;panel.present(window,s,p);assert panel.isVisible()
        window.foreground=False;panel.present(window,s,p);assert not panel.isVisible()
        window.foreground=True;s.area_id='next';panel.present(window,s,p)
        assert not panel.isVisible()and panel.pinned is None
        s.area_id='zone';s.hovered_item=data;p.settings['rare_mode']='Always on'
        panel.present(window,s,p);assert panel.isVisible()
        p.enabled=False;panel.present(window,s,p);assert not panel.isVisible()
    finally:panel.close()


def test_reader_only_reads_an_item_owned_tooltip_and_rejects_changed_hover():
    class HoverReader(Reader):
        def __init__(self):
            super().__init__({'offsets':dict(state_item_hover=8,ui_item=16,ui_tooltip_holder=24,ui_text_plain=32,ui_children=40)})
            self.calls=0;self.changed=False;self.rarity=2
        def q(self,addr):
            if addr==108:
                self.calls+=1
                return 999 if self.changed and self.calls>1 else 200
            return {216:300,224:400,400:500}.get(addr,0)
        def item_summary(self,entity):
            assert entity==300
            return dict(entity=entity,name='Example',base='Plate',rarity=self.rarity,metadata='Metadata/Items/Armours/BodyArmours/Test',components={})
        def element_rect(self,*args):return(100,100,400,300)
        def native_string(self,address,maximum,**kwargs):
            if address==532:raise ValueError('Container has no text')
            assert address==632
            return '+100 to maximum Life'
        def vector(self,address,**kwargs):return struct.pack('<Q',600)if address==540 else b''
    reader=HoverReader();data=reader.hovered_item(100,(1920,1080))
    assert data['tooltip_rows']==['+100 to maximum Life']and 'components'not in data
    reader.calls=0;reader.changed=True
    assert reader.hovered_item(100,(1920,1080))is None
    reader.changed=False;reader.rarity=0
    assert reader.hovered_item(100,(1920,1080)) is None
    reader.read_all_hover=True
    assert reader.hovered_item(100,(1920,1080))['assessment_supported'] is False


def test_release_closes_unpinned_but_not_clicked_panel(monkeypatch):
    import exile.hover_assessment as module
    from PySide6.QtCore import Qt,QPointF
    from PySide6.QtGui import QMouseEvent
    app=QApplication.instance() or QApplication([])
    panel=HoverAssessment();panel.edit_timer.stop()
    try:
        panel.expanded=True;panel.locked=False;panel.pinned={'name':'x'}
        monkeypatch.setattr(module,'alt_down',lambda:False)
        panel.update_pin_state();assert not panel.expanded
        panel.expanded=True;panel.locked=False;panel.pinned={'name':'x'}
        event=QMouseEvent(QMouseEvent.Type.MouseButtonPress,QPointF(2,2),Qt.MouseButton.LeftButton,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        panel.eventFilter(panel.body,event);panel.update_pin_state()
        assert panel.expanded and panel.locked
        panel.dismiss();assert not panel.expanded and not panel.locked
    finally:panel.close()


def test_simple_details_hide_category_and_keep_build_menu_open(monkeypatch):
    app=QApplication.instance() or QApplication([])
    manager=PluginManager(Path(__file__).parents[1]/'plugins');manager.discover()
    plugin=next(p for p in manager.plugins if p.id=='pricing');plugin.enabled=True;plugin.settings['assessment_detail']='Simple'
    snapshot=Snapshot(source='live',in_game=True,loading=False,captured_at=time.monotonic(),hovered_item=sample(),area_id='zone')
    panel=HoverAssessment();panel.edit_timer.stop()
    try:
        panel.expand(dict(sample(),_area=('zone',None)),plugin.settings);panel.locked=True
        panel.present(GameWindow(width=1920,height=1080,foreground=False),snapshot,plugin)
        text=panel.body.text()
        assert panel.isVisible() and '<hr' in text and 'of reference' not in text and 'roll range' not in text
        assert ' points' in text and 'align="right"' in text
        plugin.settings['assessment_detail']='Detailed';panel.present(GameWindow(width=1920,height=1080,foreground=True),snapshot,plugin)
        assert 'of reference' in panel.body.text()
    finally:panel.close()
