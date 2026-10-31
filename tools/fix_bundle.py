"""Reject an incompatible PATH ICU library accidentally collected by PyInstaller.

Qt uses the Windows ICU API on this machine. A separate installed application's
ICU can have the same filename but only version-suffixed exports. Let Windows
resolve its own system DLL when that exact collision is detected.
"""
from pathlib import Path
import os
import sys
import pefile


def fix(package: Path):
    root = package.resolve() / "_internal"
    candidate = root / "icuuc.dll"
    qt = root / "PySide6" / "Qt6Core.dll"
    system = Path(os.environ["WINDIR"]) / "System32" / "icuuc.dll"
    if not candidate.is_file() or not qt.is_file() or not system.is_file():
        return
    with pefile.PE(str(qt)) as image:
        required = {item.name for entry in image.DIRECTORY_ENTRY_IMPORT if entry.dll.lower() == b"icuuc.dll"
                    for item in entry.imports if item.name}
    if not required:
        return
    def exports(path):
        with pefile.PE(str(path)) as image:
            return {item.name for item in image.DIRECTORY_ENTRY_EXPORT.symbols if item.name}
    if not required <= exports(candidate) and required <= exports(system):
        if candidate.resolve().parent != root.resolve():
            raise ValueError("Unexpected bundle DLL path")
        candidate.unlink()
        print("Excluded incompatible PATH ICU; Qt will use Windows system ICU.")


if __name__ == "__main__":
    fix(Path(sys.argv[1]))
