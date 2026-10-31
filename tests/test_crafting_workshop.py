import json
from pathlib import Path
from copy import deepcopy
import time

from exile.items import item_from_hover,rate_rare,item_text,parse_item
from exile.feedback import FeedbackHistory

def sample():
    data=json.loads((Path(__file__).parent/'fixtures/brood_ward_hover.json').read_text())
    data.update(entity=100,tooltip_rect=(1200,300,400,350))
    return data

def test_confirmed_hybrid_slots_gain_small_bonus_and_roundtrip():
    item=item_from_hover(sample());rating=rate_rare(item)
    assert rating['crafting']['bonus']>0
    assert rating['crafting']['open_prefixes']+rating['crafting']['open_suffixes']==1
    assert rating['score']==round(rating['affix_score']+rating['crafting']['bonus'],1)
    restored=parse_item(item_text(item))
    assert restored.mods==item.mods and restored.links==6 and restored.sockets==6
    assert rate_rare(restored)['score']==rating['score']
    item.corrupted=True;assert rate_rare(item)['crafting']['bonus']==0
    item.corrupted=False;item.properties['Mirrored']='true'
    assert rate_rare(item)['crafting']['bonus']==0
    item.properties.pop('Mirrored');item.mod_details=[]
    assert rate_rare(item)['crafting']['bonus']==0

def test_history_delete_is_saved_and_keeps_other_examples(tmp_path):
    history=FeedbackHistory(tmp_path/'history.json');item=item_from_hover(sample())
    context=dict(item=item,rating=rate_rare(item),preference='General')
    first=history.record(context,'correct')
    context['preference']='Spell';second=history.record(context,'archetype')
    history.delete([first['id']])
    loaded=FeedbackHistory(history.path)
    assert [e['id']for e in loaded.examples]==[second['id']]

def test_alt_f_updates_workshop_buttons_archetype_and_disabled_state(tmp_path,monkeypatch):
    import exile.app as ui
    from exile.model import Snapshot
    from exile.platform import GameWindow
    monkeypatch.setattr(ui,'data_root',lambda:tmp_path)
    window=ui.MainWindow();window.timer.stop()
    try:
        plugin=next(p for p in window.manager.plugins if p.id=='pricing');plugin.enabled=True
        workshop=next(p for p in window.manager.plugins if p.id=='workshop');window.toggle(workshop,True)
        window.backend.window=GameWindow(width=1920,height=1080,foreground=True)
        window.snapshot=Snapshot(source='live',in_game=True,loading=False,captured_at=time.monotonic(),hovered_item=sample())
        window.expand_hovered_item(0,started=window.snapshot.captured_at)
        assert sample()['name']in window.tooltip_input.toPlainText()
        assert window.result.feedback_context['item'].links==6
        window.configure_feedback_hotkeys();assert not window.feedback_hotkeys
        window.navigate(1);window.result.feedback_buttons[2].click()
        assert window.feedback_history.examples[-1]['feedback']=='correct'
        window.choose_assessment_archetype('Spell',workshop=True)
        assert window.feedback_history.examples[-1]['build_preference']=='Spell'
        assert window.feedback_history.examples[-1]['feedback']=='archetype'
        window.feedback_view.refresh(window.feedback_history.examples[-1]['id'])
        window.feedback_view.delete_selected()
        assert all(e['build_preference']!='Spell'for e in window.feedback_history.examples)
        window.toggle(workshop,False)
        assert not window.workshop_body.isEnabled()
        window.tooltip_input.clear();window.snapshot.captured_at=time.monotonic();window.expand_hovered_item(0,started=window.snapshot.captured_at)
        assert sample()['name']in window.tooltip_input.toPlainText()
    finally:window.close()
    restored=ui.MainWindow();restored.timer.stop()
    try:assert not restored.workshop_enabled() and restored.nav[1].isHidden()
    finally:restored.close()


def test_workshop_module_controls_navigation_and_persists(tmp_path,monkeypatch):
    import exile.app as ui
    from exile.storage import read_json,write_json
    monkeypatch.setattr(ui,'data_root',lambda:tmp_path)
    window=ui.MainWindow();window.timer.stop()
    try:
        assert not hasattr(window,'workshop_toggle')
        assert window.nav[1].isHidden()
        workshop=next(p for p in window.manager.plugins if p.id=='workshop')
        window.cards['workshop'][1].setChecked(True)
        assert workshop.enabled and not window.nav[1].isHidden()
        window.navigate(1);assert window.pages.currentIndex()==1
        window.cards['workshop'][1].setChecked(False)
        assert window.pages.currentIndex()==0 and window.nav[1].isHidden()
        window.toggle(workshop,True)
    finally:window.close()
    restored=ui.MainWindow();restored.timer.stop()
    try:assert restored.workshop_enabled()and not restored.nav[1].isHidden()
    finally:restored.close()
    write_json(tmp_path/'settings.json',dict(workshop_enabled=False,plugins=dict(pricing=dict(enabled=False))))
    migrated=ui.MainWindow();migrated.timer.stop()
    try:assert not migrated.workshop_enabled()and migrated.nav[1].isHidden()
    finally:migrated.close()
    assert 'workshop_enabled'not in read_json(tmp_path/'settings.json',{})
