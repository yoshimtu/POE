from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import re
import time
import logging

from exile.model import Snapshot
from exile.platform import ReadMemory, game_window, process_path
from exile.storage import read_json


def installation_info(directory: Path) -> dict:
    executable = directory / "PathOfExileSteam.exe"
    manifest = directory.parent.parent / "appmanifest_238960.acf"
    build = "unknown"
    if manifest.exists():
        match = re.search(r'"buildid"\s+"(\d+)"', manifest.read_text(encoding="utf-8"))
        if match:
            build = match[1]
    digest = ""
    if executable.is_file():
        with executable.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"exists": executable.is_file(), "steam_build": build,
            "exe": str(executable), "sha256": digest}


class Backend:
    def __init__(self, profile_dir: Path, install: Path):
        self.profile_dir = profile_dir
        self.install = install
        self.info = installation_info(install)
        self.profile = None
        self.adapter = None
        self.visual_adapter = None
        self.status = "No validated memory profile for this build"
        self.item_prices_enabled = False
        self.item_link_enabled = False
        self.item_assessment_archetype = 'General'
        self.inventory_assessment_enabled = False
        self.window = game_window()
        self.scan_profiles()

    def scan_profiles(self):
        self.profile = self.adapter = self.visual_adapter = None
        self.status = "No validated memory profile for this build"
        for path in sorted(self.profile_dir.glob("*.json")):
            profile = read_json(path, {})
            # A candidate/library update is NOT a verified client profile.
            if not profile.get("validated") or not self.info["sha256"]:
                continue
            if profile.get("exe_sha256", "").lower() != self.info["sha256"].lower():
                continue
            if str(profile.get("steam_build")) != self.info["steam_build"]:
                continue
            try:
                adapter_path = (path.parent / profile["adapter"]).resolve()
                if not adapter_path.is_relative_to(path.parent.resolve()):
                    raise ValueError("Adapter must be inside the profiles directory")
                spec = importlib.util.spec_from_file_location("exile_live_adapter", adapter_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                self.adapter = module.create_adapter(profile)
                if callable(getattr(self.adapter, 'read_visual', None)):
                    self.visual_adapter = module.create_adapter(profile)
                self.profile = profile
                self.status = "Validated profile loaded · waiting for game"
                return
            except Exception as exc:
                self.status = f"Profile failed: {exc}"

    def poll(self) -> Snapshot:
        self.window = game_window()
        if not self.window.pid:
            self.status = "Waiting for Path of Exile" if self.adapter else "Memory profile unverified · game closed"
            return Snapshot()

        if not self.adapter:
            self.status = "Game found · memory profile unverified"
            return Snapshot()
        try:
            if Path(process_path(self.window.pid)).resolve() != Path(self.info["exe"]).resolve():
                raise ValueError("Game process does not match the configured executable")
            with ReadMemory(self.window.pid) as memory:
                self.adapter.read_item_overlays=self.item_prices_enabled
                self.adapter.read_all_hover=self.item_link_enabled
                self.adapter.assessment_archetype=self.item_assessment_archetype
                self.adapter.inventory_assessment_enabled=self.inventory_assessment_enabled
                snapshot = self.adapter.read(memory, self.window)
            if not isinstance(snapshot, Snapshot) or snapshot.source != "live":
                raise ValueError("Adapter did not return a live Snapshot")
            if not snapshot.fresh():
                raise ValueError("Adapter returned stale data")
            if snapshot.max_life < 0 or snapshot.life < 0 or snapshot.life > snapshot.max_life:
                raise ValueError("Invalid player life data")
            snapshot.capabilities &= set(self.profile.get("capabilities", []))
            self.status = "Live (read-only) · " + snapshot.area
            partial = getattr(snapshot, 'diagnostics', {})
            if partial:
                self.status += ' · Partial: ' + ', '.join(sorted(partial))
            self.last_error = None
            return snapshot
        except Exception as exc:
            self.status = f"Memory unavailable: {exc}"
            if getattr(self, 'last_error', None) != str(exc):
                logging.warning('Live reader unavailable: %s', exc)
                self.last_error = str(exc)
            return Snapshot()

    def poll_visual(self, snapshot):
        adapter = self.visual_adapter
        window = self.window
        if adapter is None or not window.foreground or not 0<=time.monotonic()-snapshot.captured_at<=2:
            return None
        try:
            with ReadMemory(window.pid) as memory:
                result=adapter.read_visual(memory, window, snapshot)
                if result is None and getattr(adapter,'visual_invalidated',False):
                    return dict(key=snapshot.visual_context['key'],captured_at=time.monotonic(),invalidated=True,actors={})
                return result
        except (OSError,ValueError,UnicodeError):
            return None
