from __future__ import annotations

import base64
import re
import hashlib
import json
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from exile.unique_identities import VISUAL_IDENTITY_NAMES
from exile.items import Item
from exile.prices import format_range
from exile.valuation import quote_key
from exile.storage import read_json, write_json

API = "https://poe.ninja"
CATEGORIES = ["UniqueWeapon", "UniqueArmour", "UniqueAccessory", "UniqueFlask", "UniqueJewel", "UniqueMap", "UniqueTincture", "UniqueRelic", "ForbiddenJewel", "ShrineBelt"]


def icon_art(icon):
    """Extract the provider's source asset, never guess from a thumbnail hash."""
    try:
        encoded=icon.split('/gen/image/',1)[1].split('/',1)[0]
        payload=json.loads(base64.urlsafe_b64decode(encoded+'='*(-len(encoded)%4)))
        asset=payload[2]['f']
        return ('Art/'+asset).casefold() if asset.startswith('2DItems/') else ''
    except (ValueError,IndexError,KeyError,TypeError):return ''


def matching_art(item,line):
    art=item.get('art','');candidate=icon_art(line.get('icon',''))
    # Missing provider art cannot establish a mismatch.
    return not art or not candidate or re.sub(r'\.(dds|png)$','',art.casefold())==re.sub(r'\.(dds|png)$','',candidate)


class Economy:
    def __init__(self, cache: Path):
        self.cache = cache
        self.backoff_until = 0.

    def get(self, endpoint: str, ttl: int = 900):
        key = hashlib.sha256(endpoint.encode()).hexdigest()
        path = self.cache / f"{key}.json"
        cached = read_json(path, {})
        if cached and time.time() - cached.get("fetched", 0) < ttl:
            return cached["body"], cached["fetched"]
        if time.time() < self.backoff_until:
            raise ValueError("Pricing service requested a pause. Try again later.")
        headers = {"User-Agent": "Waymark/0.1 (personal desktop companion)", "Accept": "application/json"}
        if cached.get("etag"):
            headers["If-None-Match"] = cached["etag"]
        try:
            with urlopen(Request(API + endpoint, headers=headers), timeout=20) as response:
                body = json.loads(response.read(20_000_000))
                fetched = time.time()
                entry = {"body": body, "fetched": fetched, "etag": response.headers.get("ETag", "")}
                write_json(path, entry)
                return body, fetched
        except HTTPError as exc:
            if exc.code == 304 and cached:
                cached["fetched"] = time.time()
                write_json(path, cached)
                return cached["body"], cached["fetched"]
            if exc.code == 429:
                try:
                    wait = max(60, int(exc.headers.get("Retry-After", "300")))
                except ValueError:
                    wait = 300
                self.backoff_until = time.time() + wait
            raise ValueError(f"poe.ninja HTTP {exc.code}; no price substituted.") from exc

    def leagues(self) -> list[dict]:
        body, _ = self.get("/poe1/api/economy/leagues", ttl=3600)
        if not isinstance(body, list) or not body:
            raise ValueError("No economy leagues returned.")
        return body

    def unique(self, item: Item, league: str, category: str) -> dict:
        if item.rarity != "Unique":
            raise ValueError("poe.ninja unique estimates require a unique item.")
        if category not in ["Automatic", *CATEGORIES]:
            raise ValueError("Unsupported economy category.")
        if not league.strip():
            raise ValueError("Choose an economy league first.")
        categories = CATEGORIES if category == "Automatic" else [category] + [c for c in CATEGORIES if c != category]
        lines, fetched = [], time.time()
        for candidate_category in categories:
            query = urlencode({"league": league, "type": candidate_category})
            body, fetched = self.get("/poe1/api/economy/stash/current/item/overview?" + query)
            found = [line for line in body.get("lines", []) if line.get("name", "").casefold() == item.name.casefold()]
            if found:
                lines = found
                break
        # Keep all roll variants separate; never pick the cheapest same-name line.
        candidates = [line for line in lines
                      if line.get("name", "").casefold() == item.name.casefold()
                      and (not line.get("baseType") or line["baseType"].casefold() == item.base.casefold())
                      and bool(line.get("corrupted", False)) == item.corrupted
                      and int(line.get("links", 0)) == (item.links if item.links >= 5 else 0)]
        message = "Market estimates. Check rolls and variants."
        if not candidates and lines:
            candidates = lines
            message = "Reference variants only: no exact base/link/corruption match. These are not an estimate for your exact item."
        return {"league": league, "fetched": fetched, "candidates": candidates, "message": message}

    def currency_prices(self, league, category='Currency'):
        body, fetched = self.get('/poe1/api/economy/exchange/current/overview?' + urlencode({'league': league, 'type': category}))
        core = body.get('core', {})
        if core.get('primary') != 'chaos':
            raise ValueError('Exchange reference currency changed; prices require review.')
        names = {entry['id']: entry['name'] for entry in body.get('items', []) + core.get('items', [])}
        prices = {'chaos orb': 1.}
        for line in body.get('lines', []):
            name, price = names.get(line.get('id')), line.get('primaryValue')
            if name and isinstance(price, (int, float)) and price > 0:
                prices[name.casefold()] = float(price)
        if 'divine orb' not in prices:
            rate = core.get('rates', {}).get('divine')
            if isinstance(rate, (int, float)) and rate > 0:
                prices['divine orb'] = 1 / rate
        return prices, fetched

    def stash_prices(self, items: list[dict], league: str) -> dict:
        """Bulk cached estimates; preserve uncertainty about unread roll/corruption fields."""
        if not league.strip():
            raise ValueError("Select a league in Settings first.")
        lines, fetched = [], []
        currencies, currency_stamp = self.currency_prices(league)
        fetched.append(currency_stamp)
        divine = currencies.get('divine orb')
        categories = {category for needle, category in (
            ('/DivinationCards/', 'DivinationCard'), ('Scarab', 'Scarab'), ('Essence', 'Essence'),
            ('Fossil', 'Fossil'), ('Resonator', 'Resonator'), ('Oil', 'Oil'),
            ('DeliriumOrb', 'DeliriumOrb'), ('/MapFragments/', 'Fragment'))
            if any(needle in item.get('metadata', '') for item in items)}
        for category in sorted(categories):
            quotes, stamp = self.currency_prices(league, category)
            # Keep the base Currency feed's divine quote for consistent display.
            quotes.pop('divine orb', None)
            currencies.update(quotes)
            fetched.append(stamp)
        if any(item.get("rarity") == 3 for item in items):
            for category in CATEGORIES:
                body, stamp = self.get("/poe1/api/economy/stash/current/item/overview?" +
                                       urlencode({"league": league, "type": category}))
                lines.extend(body.get("lines", []))
                fetched.append(stamp)
        estimates,quotes = {},{}
        for item in items:
            if item.get("rarity") != 3:
                continue
            unidentified = item.get('identified') is False or not item.get('name') or item['name'].casefold() == item['base'].casefold()
            expected_name=item['name']
            if item.get('foulborn')is True and not expected_name.casefold().startswith('foulborn '):expected_name='Foulborn '+expected_name
            matches = [line for line in lines if (unidentified or line.get("name", "").casefold() == expected_name.casefold())
                       and (item.get('foulborn')is None or line.get('name','').casefold().startswith('foulborn ')==item['foulborn'])
                       and (not unidentified or line.get('baseType','').casefold() == item['base'].casefold())
                       and (not line.get("baseType") or line["baseType"].casefold() == item["base"].casefold())
                       and int(line.get("links", 0)) == (item["links"] if item["links"] >= 5 else 0)
                       and (item.get("corrupted") is None or bool(line.get("corrupted", False)) == item["corrupted"])]
            if unidentified and item.get('art'):
                matches=[line for line in matches if matching_art(item,line)]
            if unidentified:
                identity_names=VISUAL_IDENTITY_NAMES.get(item.get('visual_identity',''))
                if identity_names:
                    allowed={name.casefold() for name in identity_names}
                    matches=[line for line in matches if line.get('name','').casefold() in allowed or
                             (line.get('name','').casefold().startswith('foulborn ') and
                              line['name'].casefold().removeprefix('foulborn ') in allowed)]
            values = [float(line["chaosValue"]) for line in matches
                      if isinstance(line.get("chaosValue"), (int, float)) and line["chaosValue"] > 0]
            if values:
                low, high = min(values), max(values)
                # Unknown corruption and rolls prevent claiming one exact matching variant.
                estimates[(item["name"], item["base"], item["links"], item.get("corrupted"))] = format_range(low, high, divine)
                quotes[quote_key(item)]=dict(low=low,high=high)
                if unidentified:
                    candidates={}
                    for line in matches:
                        value=line.get('chaosValue')
                        if isinstance(value,(int,float)) and value>0:
                            candidates.setdefault(line['name'],[]).append(float(value))
                    quotes[quote_key(item)]['alternatives']=[dict(name=name,low=min(prices),high=max(prices))
                        for name,prices in sorted(candidates.items(),key=lambda entry:min(entry[1]))]
        return {"league": league, "fetched": min(fetched, default=time.time()),
                "estimates": estimates, "quotes":quotes, "currencies": currencies,
                "requested_keys":[quote_key(item)for item in items if item.get('rarity')==3]}
