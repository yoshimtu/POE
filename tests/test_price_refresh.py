from types import SimpleNamespace

from exile.app import MainWindow
from exile.model import Snapshot
from exile.valuation import quote_key,enrich_items


def unique(name='Aegis Aurora',links=3,corrupted=None):
    return dict(name=name,base='Champion Kite Shield',rarity=3,links=links,corrupted=corrupted,
                quantity=1,metadata='Metadata/Items/Armours/Shields/ShieldStrInt11')


def fake_app():
    class Fake:
        def economy_league(self):return self.league.currentData()
        item_price_signature=staticmethod(MainWindow.item_price_signature)
        def __init__(self):
            self.preview=False;self.stash_pricing_pending=False;self.stash_price_retry=101
            self.stash_price_refresh_at=1000;self.stash_price_signature=None
            self.currency_estimates={'chaos orb':1};self.requests=0
            self.manager=SimpleNamespace(plugins=[SimpleNamespace(id='pricing',enabled=True)])
            self.league=SimpleNamespace(currentData=lambda:'League',currentText=lambda:'League')
            self.snapshot=Snapshot()
        def price_stash(self):self.requests+=1;self.stash_pricing_pending=True
    return Fake()


def test_new_ground_unique_schedules_after_short_coalescing_not_a_minute():
    app=fake_app();app.stash_price_signature=app.item_price_signature([], 'League')
    app.snapshot.ground_items=[unique()]
    MainWindow.maybe_price_items(app,100.5);assert app.requests==0
    MainWindow.maybe_price_items(app,101);assert app.requests==1
    MainWindow.maybe_price_items(app,102);assert app.requests==1  # only one in flight


def test_stack_quantity_relocations_and_unpriceable_rares_do_not_change_request_identity():
    items=[unique(),dict(name='Chaos Orb',base='Chaos Orb',stackable=True,quantity=1)]
    signature=MainWindow.item_price_signature(items,'League')
    items[0]['links']=4;items[1]['quantity']=20
    items.append(dict(name='New rare drop',rarity=2,metadata='Metadata/Items/Rings/Ring1'))
    assert MainWindow.item_price_signature(items,'League')==signature
    assert MainWindow.item_price_signature(items,'Other league')!=signature


def test_unchanged_items_refresh_at_provider_ttl_but_respect_failure_backoff():
    app=fake_app();app.snapshot.ground_items=[unique()]
    app.stash_price_signature=app.item_price_signature(app.snapshot.ground_items,'League')
    MainWindow.maybe_price_items(app,999);assert app.requests==0
    MainWindow.maybe_price_items(app,1000);assert app.requests==1
    app.stash_pricing_pending=False;app.stash_price_retry=1100
    app.snapshot.ground_items=[unique('Another unique')]
    MainWindow.maybe_price_items(app,1099);assert app.requests==1


def test_quotes_reuse_under_five_links_without_crossing_link_or_corruption_variants():
    items=[unique(links=n)for n in (0,3,4,5,6)]+[unique(corrupted=True)]
    enrich_items(items,{}, {quote_key(unique()):dict(low=110,high=110)})
    assert [i.get('price_label')for i in items]==['110c','110c','110c',None,None,None]


def test_quote_response_preserves_other_seen_items_but_invalidates_requested_missing_quotes():
    app=fake_app();old=quote_key(unique('Old unique'));new=quote_key(unique())
    app.prices_league='League';app.unique_quotes={old:dict(low=5,high=5)};app.stash_estimates={}
    app.note=lambda *args:None;app.enrich_stash=lambda:None;app.refresh_stash=lambda:None
    response=dict(league='League',estimates={},quotes={new:dict(low=110,high=110)},currencies={},requested_keys=[new])
    MainWindow.show_stash_prices(app,response)
    assert set(app.unique_quotes)=={old,new}
    response.update(quotes={},requested_keys=[new]);MainWindow.show_stash_prices(app,response)
    assert set(app.unique_quotes)=={old}
    response.update(league='Other league');app.league.currentData=lambda:'Other league'
    MainWindow.show_stash_prices(app,response);assert not app.unique_quotes
