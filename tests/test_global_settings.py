import exile.app as ui
from exile.model import Snapshot
from exile.storage import read_json


def test_global_league_clears_old_values_ignores_old_results_and_saves(tmp_path,monkeypatch):
    monkeypatch.setattr(ui,'data_root',lambda:tmp_path)
    w=ui.MainWindow();w.timer.stop()
    try:
        assert w.nav[5].toolTip()=='Settings'
        assert w.league.parentWidget()is not w.workshop_body
        assert not w.workshop_enabled()
        w.league.addItem('League A display','League-A');w.league.setCurrentIndex(1);w.change_economy_league()
        assert w.economy_league()=='League-A'
        item=dict(name='Chaos Orb',stackable=True,quantity=20,price_label='20c',chaos_estimate=20)
        w.snapshot=Snapshot(inventory=[dict(item)],stash=[dict(item)],ground_items=[dict(item)])
        w.currency_estimates={'chaos orb':1,'divine orb':200};w.prices_league='League-A';w.stash_price_retry=999999
        w.league.setEditText('Typed League B')
        assert w.economy_league()=='League-A'  # typing does not issue requests
        w.change_economy_league()
        assert w.economy_league()=='Typed League B'and not w.currency_estimates
        assert w.stash_price_retry==0
        assert all('price_label'not in i for i in w.snapshot.inventory+w.snapshot.stash+w.snapshot.ground_items)
        w.show_stash_prices(dict(league='League-A',estimates={},currencies={'chaos orb':9},quotes={}))
        assert not w.currency_estimates
        w.show_unique(dict(league='League-A'))  # ignored before inspecting obsolete contents
        assert read_json(tmp_path/'settings.json',{})['league']=='Typed League B'
    finally:w.close()
    restored=ui.MainWindow();restored.timer.stop()
    try:
        assert restored.economy_league()=='Typed League B'
        assert restored.league.currentText()=='Typed League B'
    finally:restored.close()


def test_economy_features_share_settings_league_with_workshop_disabled(tmp_path,monkeypatch):
    monkeypatch.setattr(ui,'data_root',lambda:tmp_path)
    w=ui.MainWindow();w.timer.stop()
    try:
        w.league.setEditText('Shared league');w.change_economy_league()
        plugin=next(p for p in w.manager.plugins if p.id=='pricing');w.toggle(plugin,True)
        w.snapshot=Snapshot(ground_items=[dict(name='Vaal Orb',stackable=True,quantity=10)])
        requests=[]
        w.economy.stash_prices=lambda items,league:requests.append(league)
        w.run_worker=lambda operation,callback:operation()
        w.price_stash();assert requests==['Shared league']
        assert not w.workshop_enabled()
        w.remember_window.setChecked(False)
        assert read_json(tmp_path/'settings.json',{})['remember_window']is False
    finally:w.close()
