import importlib.util
from pathlib import Path
import time

from exile.backend import Backend
from exile.economy import Economy
from exile.items import parse_item, rate_rare
from exile.model import Snapshot
from exile.navigation import route
from exile.plugins import PluginManager
from exile.preview import preview_snapshot
from exile.storage import read_json, write_json

ROOT = Path(__file__).resolve().parents[1]

RARE = """Item Class: Boots
Rarity: Rare
Gale Road
Titan Greaves
--------
Armour: 402
--------
Requirements:
Level: 68
--------
Item Level: 85
--------
+110 to maximum Life
+44% to Fire Resistance
+42% to Cold Resistance
30% increased Movement Speed
--------
"""

UNIQUE = """Item Class: Body Armours
Rarity: Unique
Kaom's Heart
Glorious Plate
--------
Sockets: R-R-R-R-R-R
--------
+500 to maximum Life
--------
Corrupted
"""


class Context:
    def __init__(self): self.keys = []
    def key(self, key): self.keys.append(key); return True
    def note(self, text): pass


def plugins():
    manager = PluginManager(ROOT / "plugins")
    manager.discover()
    assert not manager.errors
    return {p.id: p for p in manager.plugins}


def test_parser_does_not_score_item_level_or_properties():
    item = parse_item(RARE)
    assert item.name == "Gale Road" and item.base == "Titan Greaves"
    assert len(item.mods) == 4
    assert not any("Armour:" in mod or "Item Level" in mod for mod in item.mods)
    rating = rate_rare(item)
    assert rating["score"] > 6
    assert any("Synergy" in reason for reason in rating["reasons"])


def test_unidentified_and_unsupported_are_not_bad_items():
    item = parse_item(RARE + "Unidentified\n")
    assert rate_rare(item)["score"] is None
    item = parse_item(RARE.replace("Boots", "Maps"))
    assert rate_rare(item)["score"] is None


def test_unknown_modifiers_are_disclosed():
    item = parse_item(RARE.replace("30% increased Movement Speed", "+1 to mysterious powerful effect"))
    result = rate_rare(item)
    assert result["unknown"] == ["+1 to mysterious powerful effect"]


def test_unique_preserves_variant_link_corruption(tmp_path):
    item = parse_item(UNIQUE)
    assert item.links == 6 and item.corrupted
    economy = Economy(tmp_path)
    economy.get = lambda endpoint: ({"lines": [
        {"name": item.name, "baseType": item.base, "links": 0, "corrupted": True, "chaosValue": 1},
        {"name": item.name, "baseType": item.base, "links": 6, "corrupted": False, "chaosValue": 2},
        {"name": item.name, "baseType": item.base, "links": 6, "corrupted": True, "variant": "A", "chaosValue": 3},
        {"name": item.name, "baseType": item.base, "links": 6, "corrupted": True, "variant": "B", "chaosValue": 4},
    ]}, 100)
    result = economy.unique(item, "league", "UniqueArmour")
    assert [x["chaosValue"] for x in result["candidates"]] == [3, 4]


def test_route_does_not_cut_blocked_corners():
    assert route([[1, 0], [0, 1]], (0, 0), (1, 1)) == []
    path = route([[1, 1, 1], [1, 0, 1], [1, 1, 1]], (0, 0), (2, 2))
    assert path[0] == (0, 0) and path[-1] == (2, 2)
    assert (1, 1) not in path
    assert route([[1], [1, 1]], (0, 0), (0, 1)) == []


def test_modules_default_off_and_removal_is_supported(tmp_path):
    directory = tmp_path / "plugins" / "test"
    directory.mkdir(parents=True)
    path = directory / "plugin.py"
    path.write_text("from exile.model import Plugin\nclass P(Plugin):\n id='test'\ndef create_plugin(): return P()")
    manager = PluginManager(directory.parent, {"test": {"enabled": True}})
    manager.discover()
    assert len(manager.plugins) == 1 and manager.plugins[0].enabled
    path.unlink()
    manager.discover()
    assert not manager.plugins


def test_broken_plugin_does_not_break_discovery(tmp_path):
    directory = tmp_path / "broken"
    directory.mkdir()
    (directory / "plugin.py").write_text("raise RuntimeError('broken')")
    manager = PluginManager(tmp_path)
    manager.discover()
    assert len(manager.errors) == 1 and not manager.plugins


def test_preview_visual_modules_render_without_live_input():
    s = preview_snapshot()
    ctx = Context()
    found = plugins()
    assert len(found) == 8
    assert 'health' not in found
    for plugin in found.values():
        if plugin.requires <= s.capabilities:
            marks = plugin.tick(s, ctx)
            assert isinstance(marks, list)
    assert not ctx.keys
    assert found["map_reveal"].tick(s, ctx)
    assert found["routes"].tick(s, ctx)
    assert found["hazards"].tick(s, ctx)


def test_candidate_profile_cannot_enable_live_reader(tmp_path):
    install = tmp_path / "game"
    install.mkdir()
    (install / "PathOfExileSteam.exe").write_bytes(b"test executable")
    backend = Backend(ROOT / "profiles", install)
    assert backend.adapter is None
    assert backend.poll().source == "disconnected"


def test_atomic_settings_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    write_json(path, {"value": "settings"})
    assert read_json(path, {}) == {"value": "settings"}
