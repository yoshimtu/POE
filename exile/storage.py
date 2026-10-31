from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
import sys
import tempfile


def resource_root() -> Path:
    # one-directory distributions keep plugins next to the exe for easy removal.
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def data_root() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ObsidianExile"
    root.mkdir(parents=True, exist_ok=True)
    return root


def read_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2)
        try:
            os.replace(temporary, path)
        except OSError as exc:
            # Some Windows projected/redirected folders reject same-directory
            # replace with ERROR_NOT_SAME_DEVICE. Keep saving functional there.
            if getattr(exc, "winerror", None) != 17:
                raise
            shutil.copyfile(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
