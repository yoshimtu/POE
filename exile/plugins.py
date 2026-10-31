from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sys

from exile.model import Plugin


class PluginManager:
    def __init__(self, directory: Path, saved: dict | None = None):
        self.directory = directory
        self.saved = saved or {}
        self.plugins: list[Plugin] = []
        self.errors: list[str] = []

    def discover(self) -> None:
        for plugin in self.plugins:
            try:
                plugin.stop()
            except Exception:
                pass
        self.plugins = []
        self.errors = []
        ids = set()
        for path in sorted(self.directory.glob("*/plugin.py")):
            try:
                # Module identity includes the complete file digest so changed
                # code reloads while user preferences remain keyed by plugin id.
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                name = f"exile_plugin_{path.parent.name}_{digest[:12]}"
                spec = importlib.util.spec_from_file_location(name, path)
                if spec is None or spec.loader is None:
                    raise ValueError("Cannot load module")
                module = importlib.util.module_from_spec(spec)
                sys.modules[name] = module
                spec.loader.exec_module(module)
                plugin = module.create_plugin()
                if not isinstance(plugin, Plugin) or not plugin.id:
                    raise ValueError("create_plugin must return a Plugin with an id")
                if plugin.id in ids:
                    raise ValueError(f"Duplicate plugin id: {plugin.id}")
                ids.add(plugin.id)
                saved = self.saved.get(plugin.id, {})
                settings = (plugin.migrate_settings(self.saved) if hasattr(plugin, 'migrate_settings')
                            else saved.get('settings', {}))
                plugin.settings.update({k: v for k, v in settings.items()
                                        if k in plugin.defaults})
                # New plugins stay off; known plugin states survive updates.
                plugin.enabled = saved.get('enabled') is True
                plugin.digest = digest
                self.plugins.append(plugin)
            except Exception as exc:
                self.errors.append(f"{path.parent.name}: {type(exc).__name__}: {exc}")
        order = {"Navigation": 0, "Awareness": 1, "Economy": 2, "Actions": 3}
        self.plugins.sort(key=lambda plugin: (order.get(plugin.category, 9), plugin.name))

    def serialize(self) -> dict:
        return {p.id: {"settings": p.settings, "digest": p.digest,"enabled":p.enabled}
                for p in self.plugins}
