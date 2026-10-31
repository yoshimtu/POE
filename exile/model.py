from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
import time


@dataclass
class Mark:
    kind: str
    x: float
    y: float
    text: str = ""
    color: str = "#e4bc76"
    size: float = 6
    value: float = 1
    points: list[tuple[float, float]] = field(default_factory=list)
    clip: tuple[float, float, float, float] | None = None
    payload: Any = None
    exclusion: Any = None


@dataclass
class Snapshot:
    """Coordinates are client pixels; grid coordinates are walkable terrain cells.

    Providers must set captured_at from the local monotonic clock at read time,
    never from file modification times or the wall clock.
    """
    source: str = "disconnected"
    captured_at: float = 0
    area: str = ""
    area_id: str = ""
    in_game: bool = False
    loading: bool = True
    town: bool = True
    life: float = 0
    max_life: float = 0
    mana: float = 0
    max_mana: float = 0
    player_grid: tuple[int, int] | None = None
    grid: list[list[int]] = field(default_factory=list)
    map_origin: tuple[float, float] = (70, 130)
    map_scale: float = 5
    map_transform: dict | None = None
    terrain_heights: Any = None
    walkable_regions: Any = None
    camera: dict | None = None
    player_world: tuple[float, float, float] | None = None
    entities: list[dict[str, Any]] = field(default_factory=list)
    landmarks: list[dict[str, Any]] = field(default_factory=list)
    hazards: list[dict[str, Any]] = field(default_factory=list)
    buffs: list[dict[str, Any]] = field(default_factory=list)
    preloads: list[str] = field(default_factory=list)
    stash: list[dict[str, Any]] = field(default_factory=list)
    inventory: list[dict[str, Any]] = field(default_factory=list)
    inventory_loaded: bool = False
    ground_items: list[dict[str, Any]] = field(default_factory=list)
    item_panels: list[dict[str, Any]] = field(default_factory=list)
    viewport: tuple[int,int] = (1920,1080)
    hovered_item: dict | None = None
    capabilities: set[str] = field(default_factory=set)

    def fresh(self, max_age: float = .3) -> bool:
        age = time.monotonic() - self.captured_at
        return 0 <= age <= max_age

    def visual_fresh(self):
        now=time.monotonic()
        return (self.source=='live'and self.in_game and not self.loading and
                0<=now-self.captured_at<=2 and 0<=now-getattr(self,'visual_captured_at',0)<=.1)


class Context(Protocol):
    def note(self, text: str) -> None: ...


class Plugin:
    id = ""
    name = ""
    category = ""
    description = ""
    requires: set[str] = set()
    defaults: dict[str, Any] = {}
    # key -> (label, kind, options or numeric min/max)
    fields: dict[str, tuple] = {}

    def __init__(self):
        self.settings = dict(self.defaults)
        self.enabled = False
        self.error = ""

    def tick(self, snapshot: Snapshot, ctx: Context) -> list[Mark]:
        return []

    def stop(self) -> None:
        pass
