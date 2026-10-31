import os
import pytest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import exile.app as ui
from exile.app import MainWindow, SettingsDialog
from exile.items import parse_item, rate_rare
from exile.overlay import Overlay
from exile.model import Mark
from exile.route_legend import RouteLegend
from exile.wealth_panel import WealthWindow
from exile.platform import GameWindow
from PySide6.QtCore import QEvent,QPoint,QPointF,Qt
from PySide6.QtGui import QMouseEvent
from pathlib import Path

@pytest.fixture(autouse=True)
def alt_held_for_existing_drag_tests(monkeypatch):
    monkeypatch.setattr('exile.route_legend.alt_down',lambda:True)


def test_wealth_panels_drag_save_per_scope_and_restore_after_reopening(tmp_path):
    from exile.plugins import PluginManager
    from exile.storage import write_json,read_json
    app=QApplication.instance()or QApplication([])
    manager=PluginManager(Path(__file__).parents[1]/'plugins');manager.discover()
    pricing=next(p for p in manager.plugins if p.id=='pricing')
    box=WealthWindow('inventory');saved=[]
    def moved(x,y):
        positions=dict(pricing.settings['summary_positions']);positions['inventory']=[x,y]
        pricing.settings['summary_positions']=positions;saved.append((x,y))
        write_json(tmp_path/'settings.json',{'plugins':manager.serialize()})
    box.moved.connect(moved)
    window=GameWindow(width=1000,height=800,foreground=True)
    section=dict(scope='inventory',title='Inventory',total_label='220c',unknown=0,priced=2,top=[])
    try:
        box.present_summary(window,section,dict(pricing.settings),26);app.processEvents()
        initial=box.pos()
        def event(kind,point):
            return QMouseEvent(kind,QPointF(10,10),QPointF(point),Qt.MouseButton.LeftButton,
                               Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        box.mousePressEvent(event(QEvent.Type.MouseButtonPress,initial+QPoint(10,10)))
        box.mouseMoveEvent(event(QEvent.Type.MouseMove,QPoint(130,170)))
        box.mouseReleaseEvent(event(QEvent.Type.MouseButtonRelease,QPoint(130,170)))
        expected=box.pos();assert saved and expected==QPoint(120,160)
        box.hide();box.present_summary(window,section,dict(pricing.settings),26)
        assert box.pos()==expected
        # Restoring a new application/plugin/widget preserves hidden positions.
        restored=PluginManager(Path(__file__).parents[1]/'plugins',read_json(tmp_path/'settings.json',{})['plugins'])
        restored.discover();again=next(p for p in restored.plugins if p.id=='pricing')
        other=WealthWindow('inventory')
        try:
            larger=dict(section,top=[dict(name='Chaos Orb',quantity=220,price_label='220c')]*3)
            other.present_summary(window,larger,dict(again.settings),26)
            assert other.pos()==expected  # row counts must not shift a saved origin
            assert not again.enabled and 'personal'not in again.settings['summary_positions']
            settings=dict(again.settings,summary_locked=True)
            other.present_summary(window,larger,settings,26)
            other.mousePressEvent(event(QEvent.Type.MouseButtonPress,QPoint(130,170)))
            assert not other.dragging
            window.foreground=False;other.present_summary(window,larger,settings,26)
            assert not other.isVisible()
        finally:other.close()
    finally:box.close()


def test_overlay_clears_pixels_from_a_removed_health_bar():
    app = QApplication.instance() or QApplication([])
    overlay = Overlay()
    try:
        overlay.resize(320,240)
        overlay.marks = [Mark('bar',100,100,color='#ff0000',size=60,value=1)]
        overlay.show()
        app.processEvents()
        assert overlay.grab().toImage().pixelColor(100,102).alpha()>0
        overlay.marks=[]
        overlay.update()
        app.processEvents()
        assert overlay.grab().toImage().pixelColor(100,102).alpha()==0
    finally:
        overlay.close()


def test_route_legend_drags_within_game_bounds_and_saves_normalized_position():
    app=QApplication.instance() or QApplication([])
    from exile.plugins import PluginManager
    manager=PluginManager(Path(__file__).parents[1]/'plugins');manager.discover()
    plugin=next(p for p in manager.plugins if p.id=='routes')
    legend=RouteLegend();saved=[];legend.moved.connect(lambda x,y:saved.append((x,y)))
    window=GameWindow(width=800,height=600,foreground=True)
    mark=Mark('route_legend',0,0,payload=dict(settings=dict(plugin.settings),rows=[dict(name='Exit',color='#68b4ff',status='')]))
    try:
        legend.present(window,mark);app.processEvents()
        initial=legend.pos()
        def event(kind,global_point,buttons):
            return QMouseEvent(kind,QPointF(10,10),QPointF(global_point),Qt.MouseButton.LeftButton,buttons,Qt.KeyboardModifier.NoModifier)
        legend.mousePressEvent(event(QEvent.Type.MouseButtonPress,initial+QPoint(10,10),Qt.MouseButton.LeftButton))
        target=initial+QPoint(-60,40)
        legend.mouseMoveEvent(event(QEvent.Type.MouseMove,target+QPoint(10,10),Qt.MouseButton.LeftButton))
        legend.mouseReleaseEvent(event(QEvent.Type.MouseButtonRelease,target,Qt.MouseButton.NoButton))
        assert len(saved)==1 and all(0<=value<=1 for value in saved[0])
        assert legend.pos()!=initial
        mark.payload['settings'].update(legend_anchor='Custom position',legend_position=list(saved[0]))
        position=legend.pos();legend.present(window,mark)
        assert legend.pos()==position
        mark.payload['settings']['legend_locked']=True;legend.present(window,mark)
        legend.mousePressEvent(event(QEvent.Type.MouseButtonPress,target,Qt.MouseButton.LeftButton))
        assert not legend.dragging
        window.foreground=False;legend.present(window,mark)
        assert not legend.isVisible()
    finally:legend.close()


def test_desktop_settings_preview_and_panic(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(ui.STYLE)
    monkeypatch.setattr(ui, "data_root", lambda: tmp_path)
    window = MainWindow()
    try:
        assert len(window.cards) == 8
        assert not any(p.enabled for p in window.manager.plugins)
        ring = parse_item((Path(__file__).parent / 'fixtures/onslaught_ring.txt').read_text())
        window.result.show_rare(ring, rate_rare(ring, 'Minion'))
        assert window.result.table.rowCount() == 8
        assert '6/6' in window.result.message.text()
        window.result.show_unique(dict(league='Example league', fetched=1700000000,
                                      message='Matching variants', candidates=[dict(name='Aegis Aurora', chaosValue=100, divineValue=.3)]))
        assert window.result.table.rowCount() == 1
        for plugin in window.manager.plugins:
            dialog = SettingsDialog(plugin, window)
            assert dialog.values() == {k:v for k,v in plugin.defaults.items() if k in plugin.fields}
            dialog.close()
        window.set_preview(True)
        for plugin in window.manager.plugins:
            window.toggle(plugin, True)
        window.tick()
        assert window.canvas.marks
        window.panic()
        assert not any(p.enabled for p in window.manager.plugins)
        window.save()
        assert (tmp_path / "settings.json").is_file()
    finally:
        window.close()
        app.processEvents()

def test_dot_batch_preserves_style_boundaries_and_mark_data():
    from exile.overlay import batch_dots
    from exile.model import Mark
    dots=[Mark('dot',x,10,color='#dc6464',size=2,value=.8,payload=dict(filled=True,width=1))for x in (10,20)]
    label=Mark('dot',30,10,text='Rare',payload=dict(filled=True))
    hollow=Mark('dot',40,10,payload=dict(filled=False))
    result=list(batch_dots(dots+[label,hollow]))
    assert len(result)==3 and result[0].kind=='dot_batch'
    assert result[0].points==[(10,10),(20,10)]
    assert result[1]is label and result[2]is hollow
    assert all(dot.kind=='dot'and not dot.points for dot in dots)


def test_batched_circles_keep_subpixel_bounds_opacity_and_clipping(monkeypatch):
    import numpy as np
    from PySide6.QtGui import QImage,QPainter
    import exile.overlay as drawing
    app=QApplication.instance()or QApplication([])
    dots=[Mark('dot',x,20.75,color='#dc6464',size=2,value=.8,clip=(0,0,42,50),payload=dict(filled=True,width=1))for x in (20.25,40.25)]
    arrays=[];batch=drawing.batch_dots
    for fn in (lambda marks:iter(marks),batch):
        monkeypatch.setattr(drawing,'batch_dots',fn)
        img=QImage(60,50,QImage.Format.Format_ARGB32_Premultiplied);img.fill(0)
        painter=QPainter(img);drawing.paint_marks(painter,dots);painter.end()
        arrays.append(np.frombuffer(img.bits(),dtype=np.uint8).reshape(50,60,4).copy())
    for pixels in arrays:
        assert pixels[20,20,3]in range(202,206)
        assert not pixels[:,42:,3].any()
    for pixels in arrays:
        ys,xs=np.nonzero(pixels[:,:,3]);assert (xs.min(),xs.max(),ys.min(),ys.max())==(17,41,18,23)

def test_waymark_inline_settings_save_cancel_and_module_switch(tmp_path,monkeypatch):
    from exile.storage import read_json
    app=QApplication.instance()or QApplication([])
    monkeypatch.setattr(ui,'data_root',lambda:tmp_path)
    window=MainWindow();window.timer.stop()
    try:
        assert window.windowTitle()=='Waymark' and not window.windowIcon().isNull()
        plugin=next(p for p in window.manager.plugins if p.id=='map_reveal')
        panel=window.inspector.widget()
        panel.controls['opacity'].setValue(67);panel.accept()
        assert plugin.settings['opacity']==67
        assert read_json(tmp_path/'settings.json',{})['plugins']['map_reveal']['settings']['opacity']==67
        panel.controls['opacity'].setValue(81)
        pricing=next(p for p in window.manager.plugins if p.id=='pricing')
        window.select_module(pricing)
        assert plugin.settings['opacity']==81
        assert read_json(tmp_path/'settings.json',{})['plugins']['map_reveal']['settings']['opacity']==81
        assert window.inspector.widget().plugin is pricing
        assert all(not p.enabled for p in window.manager.plugins)
        assert list(window.cards)==['map_reveal','routes','radar','preload','pricing','workshop','hazards','uptime']
    finally:window.close();app.processEvents()


def test_image_skin_keeps_mouse_keyboard_and_window_controls(tmp_path,monkeypatch):
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QSlider
    from exile.theme import TitleBar,skin_image,panel_image
    app=QApplication.instance()or QApplication([]);app.setStyleSheet(ui.STYLE)
    monkeypatch.setattr(ui,'data_root',lambda:tmp_path)
    window=MainWindow();window.timer.stop();window.show();app.processEvents()
    try:
        checkbox=window.cards['map_reveal'][1]
        QTest.mouseClick(checkbox,Qt.MouseButton.LeftButton)
        assert next(p for p in window.manager.plugins if p.id=='map_reveal').enabled
        panel=window.inspector.widget();slider=panel.findChildren(QSlider)[0]
        before=panel.controls['opacity'].value();slider.setFocus()
        QTest.keyClick(slider,Qt.Key.Key_Right)
        assert panel.controls['opacity'].value()==before+1
        panel.controls['opacity'].setValue(before+2);assert slider.value()==before+2
        title=window.findChild(TitleBar);title.toggle_maximized();assert window.isMaximized()
        title.toggle_maximized();assert not window.isMaximized()
        image=panel_image(310,140)
        assert image.pixelColor(155,70).alpha()==255
        assert panel_image(310,140)is image
        for name in ('panel','texture','button-normal','field-normal','check-on','check-off','icon-radar'):
            assert not skin_image(name+'.png').isNull()
    finally:window.close();app.processEvents()


def test_inventory_closed_hides_cached_prices_and_summary():
    from exile.plugins import PluginManager
    from exile.model import Snapshot
    manager=PluginManager(Path(__file__).parents[1]/'plugins');manager.discover()
    plugin=next(p for p in manager.plugins if p.id=='pricing')
    plugin.settings['summary_closed']=True  # legacy saved preference must not override this
    snapshot=Snapshot(source='preview',inventory_loaded=True,inventory=[dict(name='Vaal Orb',visible=True,rect=[10,10,40,40],price_label='10c')])
    assert not plugin.tick(snapshot,None)
    snapshot.item_panels=[dict(scope='inventory')]
    marks=plugin.tick(snapshot,None)
    assert any(m.kind=='item_price'for m in marks)and any(m.kind=='wealth_panel'for m in marks)
    snapshot.item_panels=[]
    assert not plugin.tick(snapshot,None)


def test_wealth_resize_reflows_long_names_and_restores_size():
    from exile.wealth_panel import compact_height
    from exile.plugins import PluginManager
    manager=PluginManager(Path(__file__).parents[1]/'plugins');manager.discover()
    settings=dict(next(p for p in manager.plugins if p.id=='pricing').settings)
    section=dict(scope='inventory',title='Inventory',total_label='100d',unknown=0,top=[dict(name='An unusually long item name with several important words',quantity=30,price_label='100d')]*3)
    window=GameWindow(width=1200,height=900,foreground=True);box=WealthWindow('inventory')
    try:
        box.present_summary(window,section,settings,26)
        box.resize_summary(210,75)
        assert box.width()==210 and box.settings['summary_font']==settings['summary_font']
        assert box.height()==75
        box.resize_summary(60,32)
        assert box.width()==60 and box.height()==32
        settings['summary_sizes']={'inventory':[box.width(),box.height()]}
        expected=box.size();box.hide();box.present_summary(window,section,settings,26)
        assert box.size()==expected
        image=box.grab();assert not image.isNull()
    finally:box.close()


def test_route_and_alert_panels_resize_and_restore_without_changing_font():
    from exile.floating_panel import FloatingPanel
    from exile.plugins import PluginManager
    manager=PluginManager(Path(__file__).parents[1]/'plugins');manager.discover()
    window=GameWindow(width=1000,height=800,foreground=True)
    legend=RouteLegend();alerts=FloatingPanel()
    try:
        routes=next(p for p in manager.plugins if p.id=='routes')
        settings=dict(routes.settings,legend_size=[90,40])
        mark=Mark('route_legend',0,0,payload=dict(settings=settings,rows=[dict(name='Arena',color='#ffffff',status='')]))
        legend.present(window,mark)
        assert (legend.width(),legend.height())==(90,40)
        legend.resize_summary(60,32)
        assert (legend.width(),legend.height())==(60,32)
        assert legend.settings['legend_font']==routes.settings['legend_font']
        preload=next(p for p in manager.plugins if p.id=='preload')
        settings=dict(preload.settings,overlay_size=[100,45],overlay_position=[.2,.3])
        mark=Mark('preload_panel',30,110,payload=dict(settings=settings,rows=[dict(label='Breach',evidence='Seen',color='#ffffff')]))
        alerts.present(window,mark);first=alerts.pos();alerts.hide();alerts.present(window,mark)
        assert (alerts.width(),alerts.height())==(100,45)and alerts.pos()==first
        alerts.resize_summary(60,32);assert alerts.width()==60 and alerts.height()==32
        assert alerts.payload['settings']['font_size']==preload.settings['font_size']
        assert not alerts.grab().isNull()
        alerts.present(window,None);assert not alerts.isVisible()
    finally:legend.close();alerts.close()


def test_alt_controls_editing_and_buff_exclusion(monkeypatch):
    from exile.floating_panel import FloatingPanel
    from exile.plugins import PluginManager
    from exile.model import Snapshot
    held=[False];monkeypatch.setattr('exile.route_legend.alt_down',lambda:held[0])
    manager=PluginManager(Path(__file__).parents[1]/'plugins');manager.discover()
    plugin=next(p for p in manager.plugins if p.id=='uptime')
    snapshot=Snapshot(source='preview',buffs=[dict(id='determination',name='Determination',remaining=10)])
    mark=plugin.tick(snapshot,None)[0];mark.payload['uptime']=True
    box=FloatingPanel();hidden=[];box.excluded.connect(hidden.append)
    try:
        box.present(GameWindow(width=1000,height=800,foreground=True),mark)
        assert not box.editing and box.windowFlags()&Qt.WindowType.WindowTransparentForInput
        event=QMouseEvent(QEvent.Type.MouseButtonPress,QPointF(box.width()-17,35),QPointF(200,200),Qt.MouseButton.LeftButton,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        box.mousePressEvent(event);assert not hidden and not box.dragging
        held[0]=True;box.sync_edit();box.mousePressEvent(event)
        assert hidden==['Determination']
        plugin.settings['exclusions']=hidden[0]
        assert not plugin.tick(snapshot,None)
        plugin.settings['exclusions']='';assert plugin.tick(snapshot,None)
        held[0]=False;box.sync_edit()
        assert not box.editing and box.windowFlags()&Qt.WindowType.WindowTransparentForInput
    finally:box.close()


def test_enabled_state_and_settings_survive_close_and_update(tmp_path,monkeypatch):
    from exile.plugins import PluginManager
    from exile.storage import read_json
    monkeypatch.setattr(ui,'data_root',lambda:tmp_path)
    window=MainWindow();window.timer.stop()
    window.toggle(next(p for p in window.manager.plugins if p.id=='uptime'),True)
    window.exclude_buff('Determination');window.close()
    saved=read_json(tmp_path/'settings.json',{})['plugins']
    assert saved['uptime']['enabled']and saved['uptime']['settings']['exclusions']=='Determination'
    saved['uptime']['digest']='old-version'
    manager=PluginManager(Path(__file__).parents[1]/'plugins',saved);manager.discover()
    assert next(p for p in manager.plugins if p.id=='uptime').enabled
    restored=MainWindow();restored.timer.stop()
    try:
        assert next(p for p in restored.manager.plugins if p.id=='uptime').enabled
        assert len(restored.nav)==7 and restored.pages.count()==7
        assert all('preview'not in nav.toolTip().lower()for nav in restored.nav)
    finally:restored.close()


def test_inline_settings_autosave_and_column_preferences(tmp_path,monkeypatch):
    import time
    import exile.app as ui
    from PySide6.QtWidgets import QApplication
    monkeypatch.setattr(ui,'data_root',lambda:tmp_path)
    app=QApplication.instance() or QApplication([]);window=ui.MainWindow();window.timer.stop();window.connections.timer.stop()
    try:
        plugin=next(p for p in window.manager.plugins if p.id=='pricing');window.select_module(plugin)
        panel=window.inspector.widget();original=plugin.settings['inventory_prices']
        panel.controls['inventory_prices'].setChecked(not original)
        end=time.monotonic()+2
        while plugin.settings['inventory_prices']==original and time.monotonic()<end:app.processEvents();time.sleep(.01)
        assert plugin.settings['inventory_prices'] is (not original) and panel.actions.isHidden()
        window.stash_table.setColumnWidth(1,177);window.set_stash_column(1,False)
        assert window.config['stash_visible_columns'][1] is False
        assert window.config['stash_column_widths'][1]==177
    finally:window.close()
