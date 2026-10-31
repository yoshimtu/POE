from types import SimpleNamespace
from PySide6.QtCore import QPoint
from exile.hover_tracker import HoverTracker

def snap(when,item=None,area=1):
    return SimpleNamespace(area_id=area,instance_key='instance',source='live',loading=False,captured_at=when,hovered_item=item)

def test_stationary_hover_reuses_recent_read_but_rejects_pointer_moves_and_old_data():
    t=HoverTracker();pos=QPoint(100,100)
    t.sample(pos,10.,snap(9.9,{'hover_captured_at':9.9}),True)
    assert t.current(pos,10.,snap(10.)) is None
    t.sample(pos,10.1,snap(10.1,{'hover_captured_at':10.1,'name':'Item'}),True)
    assert t.current(pos,10.2,snap(10.2))['name']=='Item'
    t.sample(pos,10.21,snap(10.21),True,preserve_missing=True)
    assert t.current(pos,10.3,snap(10.3))['name']=='Item'
    assert t.current(QPoint(120,100),10.2,snap(10.2)) is None
    assert t.current(pos,11.7,snap(11.7)) is None
    assert t.current(pos,10.2,snap(10.2,area=2)) is None
    t.sample(pos,10.2,snap(10.2),False);assert t.current(pos,10.2,snap(10.2)) is None
