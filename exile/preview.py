"""Explicit synthetic data for UI verification. Never accepted for input."""
import time
from exile.model import Snapshot


def preview_snapshot() -> Snapshot:
    grid = [[int(2 < x < 54 and 2 < y < 34 and not (22 < x < 28 and y < 25))
             for x in range(58)] for y in range(38)]
    return Snapshot(source="preview", captured_at=time.monotonic(), area="Synthetic preview — no game data",
                    in_game=True, loading=False, town=False,
                    life=3200, max_life=4500, mana=200, max_mana=400,
                    grid=grid, player_grid=(10, 14), map_origin=(45, 135),
                    entities=[{"kind": "exit", "name": "Exit", "grid": (48, 8)},
                              {"kind": "monster", "rarity": 0, "name": "Normal monster", "grid": (15, 14),
                               "screen": (330,290), "life": 100, "max_life": 100},
                              {"kind": "monster", "rarity": 1, "name": "Magic monster", "grid": (18, 16),
                               "screen": (400,300), "life": 80, "max_life": 100},
                              {"kind": "boss", "is_map_boss": True, "name": "Boss", "grid": (44, 24),
                               "screen": (590, 270), "life": 650, "max_life": 1000},
                              {"kind": "rare", "name": "Rare monster", "grid": (17, 20),
                               "screen": (450, 350), "life": 420, "max_life": 700},
                              {"kind": "valuable", "name": "Strongbox", "grid": (37, 17)},
                              {"kind": "valuable", "category": "legion", "name": "Legion monolith", "grid": (37, 30)},
                              {"kind": "valuable", "category": "waypoint", "name": "Waypoint", "grid": (7, 28)}],
                    hazards=[{"name": "Volatile core (sample)", "screen": (610, 430),
                              "radius": 36, "active": True}],
                    buffs=[{"id": "determination", "name": "Determination", "remaining": None},
                           {"id": "granite_flask", "name": "Granite flask", "remaining": 3.2, "flask": True}],
                    preloads=['Metadata/Chests/StrongBoxes/Diviner',
                              'Metadata/Monsters/LegionLeague/LegionMarakethGeneral',
                              'Metadata/Monsters/Daemon/EssenceDaemonHorror1'],
                    stash=[{"scope": "guild", "name": "Sample unique", "visible": True,
                            "screen": (390, 540), "chaos_estimate": None}],
                    capabilities={"terrain", "entities", "health", "hazards", "buffs", "preloads", "stash"})
