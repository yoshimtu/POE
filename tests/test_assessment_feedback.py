import json
import os
from copy import deepcopy
from pathlib import Path

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from exile.feedback import FeedbackHistory
from exile.items import parse_item, rate_rare


def example():
    item = parse_item((Path(__file__).parent / 'fixtures/onslaught_ring.txt').read_text(encoding='utf-8'))
    return dict(item=item, rating=rate_rare(item), preference='General',
                metadata='Metadata/Items/Rings/Test', tooltip_rows=['Tier: 1', '+42% minion damage'])


def test_feedback_roundtrip_preserves_displayed_evidence_without_retuning(tmp_path):
    context = example(); before = deepcopy(context['rating'])
    history = FeedbackHistory(tmp_path / 'feedback.json')
    entry = history.record(context, 'higher', 'Allflame', 'The Riverways')
    history.set_note(entry['id'], 'Strong coherent minion rolls')
    history.record(context, 'correct', 'Allflame', 'The Riverways')
    loaded = FeedbackHistory(history.path)
    assert len(loaded.examples) == 1
    saved = json.loads(loaded.export())['examples'][0]
    assert saved['feedback'] == 'correct'
    assert saved['note'] == 'Strong coherent minion rolls'
    assert saved['rating'] == before
    assert saved['item']['mod_details'] and saved['tooltip_rows'] == context['tooltip_rows']
    assert saved['scorer_version'] and saved['model_signature']
    assert rate_rare(context['item']) == before
    context['rating']['score'] = 0
    assert saved['rating']['score'] != 0  # captured evidence is independent of live objects
    context = example(); context['preference'] = 'Minion'
    other = history.record(context, 'lower', 'Allflame')
    assert len(history.examples) == 2
    assert [e['id'] for e in json.loads(history.export([other['id']]))['examples']] == [other['id']]


def test_feedback_failed_save_does_not_publish_vote_or_note(tmp_path, monkeypatch):
    import exile.feedback as feedback
    history = FeedbackHistory(tmp_path / 'feedback.json'); context = example()
    entry = history.record(context, 'higher')
    def fail(*args): raise OSError('Disk unavailable')
    monkeypatch.setattr(feedback, 'write_json', fail)
    with pytest.raises(OSError): history.record(context, 'lower')
    assert history.examples[0]['feedback'] == 'higher'
    with pytest.raises(OSError): history.set_note(entry['id'], 'lost note')
    assert history.examples[0]['note'] == ''


def test_unrated_and_six_link_evidence_and_model_revisions_are_retained(tmp_path, monkeypatch):
    import exile.feedback as feedback
    context = example(); context['item'].links = 6; context['item'].sockets = 6
    context['rating'] = dict(score=None, unknown=['Unrecognized special modifier'])
    history = FeedbackHistory(tmp_path / 'feedback.json')
    first = history.record(context, 'higher')
    assert first['item']['links'] == 6 and first['rating']['score'] is None
    assert first['rating']['unknown'] == context['rating']['unknown']
    monkeypatch.setattr(feedback, 'SCORER_VERSION', 'future-revision')
    second = history.record(context, 'correct')
    assert second['id'] != first['id'] and len(history.examples) == 2


def test_feedback_history_selection_copy_and_notes(tmp_path):
    from exile.feedback_view import FeedbackView
    app = QApplication.instance() or QApplication([])
    history = FeedbackHistory(tmp_path / 'feedback.json'); context = example()
    first = history.record(context, 'higher')
    context['preference'] = 'Minion'; history.record(context, 'correct')
    copies = []; notices = []; view = FeedbackView(history, copies.append, notices.append)
    try:
        assert not copies
        view.refresh(first['id']); assert view.selected_ids() == [first['id']]
        view.note.setText('Please review synergy'); view.save_note()
        view.copy(True); selected = json.loads(copies[-1])['examples']
        assert len(selected) == 1 and selected[0]['note'] == 'Please review synergy'
        view.copy(False); assert len(json.loads(copies[-1])['examples']) == 2
    finally: view.close()


def test_only_active_assessments_accept_feedback(tmp_path, monkeypatch):
    import time
    import exile.app as ui
    from exile.model import Snapshot
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(ui, 'data_root', lambda: tmp_path)
    monkeypatch.setattr(ui, 'window_is_foreground', lambda hwnd: True)
    window = ui.MainWindow(); window.timer.stop()
    try:
        pricing = next(p for p in window.manager.plugins if p.id == 'pricing')
        context = example(); window.hover_assessment.feedback_context = context
        window.snapshot = Snapshot(source='live', in_game=True, loading=False, captured_at=time.monotonic())
        window.hover_assessment.show(); app.processEvents()
        assert window.active_feedback_context() is None  # module off
        pricing.enabled = True
        assert window.active_feedback_context() is context
        assert window.record_assessment_feedback('higher')
        assert window.feedback_history.examples[-1]['rating'] == context['rating']
        pricing.settings['rare_feedback'] = False
        assert window.active_feedback_context() is None
        pricing.settings['rare_feedback'] = True
        window.snapshot.loading = True
        assert window.active_feedback_context() is None
        window.snapshot.loading = False; window.snapshot.captured_at = 0
        assert window.active_feedback_context() is None
        window.hover_assessment.dismiss()
        assert window.hover_assessment.feedback_context is None
        window.toggle(next(p for p in window.manager.plugins if p.id=='workshop'),True)
        window.navigate(1); window.result.show_rare(context['item'], context['rating'], 'General')
        monkeypatch.setattr(window, 'isActiveWindow', lambda: True)
        monkeypatch.setattr(QApplication, 'focusWidget', lambda: window.result.table)
        assert window.active_feedback_context() is window.result.feedback_context
        monkeypatch.setattr(QApplication, 'focusWidget', lambda: window.feedback_view.note)
        assert window.active_feedback_context() is None  # typing keeps arrow controls
        assert window.record_assessment_feedback('correct', workshop=True)
        window.navigate(4)
        assert window.active_feedback_context() is None
        window.panic(); assert not window.feedback_hotkeys
        assert not hasattr(window, 'armed') and not hasattr(window, 'key')
        assert all(p.id != 'auto_flask' for p in window.manager.plugins)
    finally: window.close(); app.processEvents()


def test_release_staging_excludes_removed_modules_and_bytecode(tmp_path):
    from tools.stage_plugins import stage_plugins
    source = tmp_path / 'plugins'
    for name in ('removed/__pycache__/plugin.pyc', 'active/plugin.py', 'active/catalog.json', 'active/__pycache__/plugin.pyc'):
        path = source / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('test')
    staged = tmp_path / 'staged'; stage_plugins(source, staged)
    assert sorted(str(p.relative_to(staged)).replace('\\', '/') for p in staged.rglob('*') if p.is_file()) == ['active/catalog.json', 'active/plugin.py']
