import json
import time
from pathlib import Path
from concurrent.futures import Future
import pytest
from exile.items import equipment_metadata,item_from_hover,parse_item,rate_rare
from exile.model import Snapshot,Mark
from exile.presentation import PresentationCache

def test_non_equipment_rares_never_receive_equipment_ratings():
    for path in ('Metadata/Items/Maps/Test','Metadata/Items/Charts/Test','Metadata/Items/Atlas/Charts/Test','Metadata/Items/Contracts/Test',''):
        assert not equipment_metadata(path)
        with pytest.raises(ValueError,match='equipment only'):
            item_from_hover(dict(name='Rare chart',base='Chart',metadata=path,tooltip_rows=['+100 to maximum Life']))
    assert rate_rare(parse_item('Item Class: Charts\nRarity: Rare\nRare Chart\nChart\n--------\n+100 to maximum Life'))['score']is None
    assert equipment_metadata('Metadata/Items/Weapons/OneHandWeapons/OneHandAxes/Test')

def test_missed_read_holds_display_without_extending_data_freshness():
    cache=PresentationCache();marks=[Mark('text',10,10,'Map')]
    live=Snapshot(source='live',in_game=True,loading=False,captured_at=10)
    assert cache.resolve(live,marks,'session',True,10.1)is marks
    assert cache.resolve(Snapshot(),[],'session',True,10.4)is marks
    assert not cache.resolve(Snapshot(),[],'session',True,10.7)
    cache.resolve(live,marks,'session',True,10.1)
    assert not cache.resolve(Snapshot(),[],'different-session',True,10.4)
    cache.resolve(live,marks,'session',True,10.1)
    assert not cache.resolve(Snapshot(source='live',loading=True),[],'session',True,10.2)
    cache.resolve(live,marks,'session',True,10.1)
    assert not cache.resolve(Snapshot(),[],'session',False,10.2)
    # A valid empty result (dead pack, closed map, module off) clears immediately.
    assert cache.resolve(live,[],'session',True,10.1)==[]

def test_live_map_build_is_bounded_and_does_not_wait_for_worker():
    from exile.plugins import PluginManager
    manager=PluginManager(Path(__file__).parents[1]/'plugins');manager.discover()
    plugin=next(p for p in manager.plugins if p.id=='map_reveal')
    pending=Future()
    class Pool:
        def __init__(self):self.calls=0
        def submit(self,*args):self.calls+=1;return pending
        def shutdown(self,**kwargs):pass
    pool=Pool();plugin.pool=pool
    snapshot=Snapshot(source='live',grid=[[1]*32 for _ in range(32)],map_transform={'test':True})
    try:
        assert plugin.tick(snapshot,object())==[]
        assert plugin.tick(snapshot,object())==[]and pool.calls==1
    finally:plugin.stop()

def test_icon_batches_preserve_pixels_and_clip(monkeypatch):
    from PySide6.QtGui import QImage,QPainter
    import exile.overlay as drawing
    import numpy as np
    marks=[Mark('dot',x,40,size=5,value=.6,clip=(0,0,75,80),payload=dict(icon='poe2:RareMonsterAlive',icon_scale=100))for x in (30,35,70)]
    arrays=[];batch=drawing.batch_dots
    for fn in (lambda marks:iter(marks),batch):
        monkeypatch.setattr(drawing,'batch_dots',fn)
        image=QImage(100,80,QImage.Format.Format_ARGB32_Premultiplied);image.fill(0)
        p=QPainter(image);drawing.paint_marks(p,marks);p.end()
        arrays.append(bytes(image.constBits()))
    assert arrays[0]==arrays[1]


def test_chart_hover_is_rejected_before_tooltip_traversal():
    from exile.reader import Reader
    class ChartReader(Reader):
        def q(self,address):return {108:200,216:300}.get(address,0)
        def item_summary(self,entity):return dict(entity=entity,name='Chart',base='Chart',rarity=2,metadata='Metadata/Items/Charts/Chart1')
        def element_rect(self,*args):raise AssertionError('Should not traverse a chart tooltip')
    reader=ChartReader({'offsets':dict(state_item_hover=8,ui_item=16)})
    assert reader.hovered_item(100,(1920,1080))['assessment_supported']is False
