"""Stage active plugins only; obsolete bytecode must not enter a release."""
from pathlib import Path
import shutil
import sys


def stage_plugins(source, destination):
    source, destination = Path(source), Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    for entry in sorted(source.glob('*/plugin.py')):
        for path in entry.parent.rglob('*'):
            relative = path.relative_to(source)
            if not path.is_file() or '__pycache__' in relative.parts or path.suffix in ('.pyc', '.pyo'):
                continue
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


if __name__ == '__main__':
    stage_plugins(*sys.argv[1:])
