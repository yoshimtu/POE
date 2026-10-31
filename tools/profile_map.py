"""Developer-only, read-only live map timing capture. Never sends game input."""
import argparse
import json
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from exile.app import MainWindow
from exile.backend import Backend
from exile.mapview import MapMotion
from exile.native_map import NativeMapOverlap
from exile.overlay import Overlay


def stats(values):
    ordered = sorted(values)
    if not ordered:
        return {}
    return dict(n=len(ordered), median=statistics.median(ordered),
                p95=ordered[int((len(ordered) - 1) * .95)], max=max(ordered))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=120)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--no-mask', action='store_true')
    parser.add_argument('--keep-open', action='store_true', help='Finish capture without closing the app')
    parser.add_argument('--modules', default='map_reveal', help='Explicit modules to enable for this diagnostic session')
    parser.add_argument('--health', action='store_true', help='Enable custom radar health bars for diagnosis')
    args = parser.parse_args()
    stop_file = args.output.with_suffix('.stop')
    stop_file.unlink(missing_ok=True)
    origin = time.monotonic()
    records = {key: [] for key in ('tick', 'read', 'paint', 'mask', 'motion', 'plugin', 'read_meta', 'visual')}
    saved = False

    def wrap(cls, name, key):
        original = getattr(cls, name)
        def timed(self, *a, **kw):
            if saved:
                return original(self, *a, **kw)
            start = time.monotonic()
            try:
                result = original(self, *a, **kw)
                if key == 'read':
                    records['read_meta'].append(dict(t=start-origin, area=result.area,
                        source=result.source, status=self.status, diagnostics=getattr(result, 'diagnostics', {}),
                        entities=len(result.entities),
                        hovered_item=(dict(name=result.hovered_item.get('name'),links=result.hovered_item.get('links'),
                            sockets=result.hovered_item.get('sockets'),rows=result.hovered_item.get('tooltip_rows'),
                            tooltip_rect=result.hovered_item.get('tooltip_rect'))if result.hovered_item else None),
                        living=sum(e.get('alive') is True and e.get('hostile') is not False for e in result.entities),
                        dead=sum(e.get('alive') is False for e in result.entities),
                        rare=[dict(id=e.get('id'), life=e.get('life'), hostile=e.get('hostile'))
                              for e in result.entities if e.get('rarity') in (2,3)]))
                return result
            finally:
                records[key].append((start - origin, (time.monotonic() - start) * 1000))
        setattr(cls, name, timed)

    wrap(MainWindow, 'tick', 'tick')
    wrap(Backend, 'poll', 'read')
    wrap(Backend, 'poll_visual', 'visual')
    wrap(Overlay, 'paintEvent', 'paint')
    wrap(NativeMapOverlap, '_frame', 'mask')
    sample = MapMotion.sample
    def motion(self, snapshot, now=None):
        result = sample(self, snapshot, now)
        if saved:
            return result
        at = time.monotonic()
        raw = snapshot.map_transform
        map_at=getattr(snapshot,'map_captured_at',snapshot.captured_at)
        records['motion'].append(dict(t=at-origin, age=at-map_at,core_age=at-snapshot.captured_at,
            captured=map_at-origin, area=snapshot.area, grid=id(snapshot.grid),
            raw=raw, visual=result, foreground=window.backend.window.foreground))
        return result
    MapMotion.sample = motion
    app = QApplication(sys.argv[:1])
    app.setStyle('Fusion')
    window = MainWindow()
    original_settings = {p.id: dict(p.settings) for p in window.manager.plugins}
    from exile.app import STYLE
    app.setStyleSheet(STYLE)
    for plugin in window.manager.plugins:
        plugin.enabled = plugin.id in args.modules.split(',')
        if plugin.enabled:
            if plugin.id == 'radar' and args.health:
                plugin.settings['health_bars'] = True
            if args.no_mask:
                plugin.settings['hide_native'] = False
            original = plugin.tick
            def plugin_tick(*a, _tick=original, **kw):
                if saved:
                    return _tick(*a, **kw)
                start = time.monotonic()
                try:
                    return _tick(*a, **kw)
                finally:
                    records['plugin'].append((start-origin, (time.monotonic()-start)*1000))
            plugin.tick = plugin_tick
    window.update_module_states()
    window.show()
    def save():
        nonlocal saved
        if saved:
            return
        saved = True
        summary = {}
        for key in ('tick', 'read', 'paint', 'mask', 'plugin', 'visual'):
            rows = records[key]
            warm = [row for row in rows if row[0] > 5]
            summary[key + '_ms'] = stats([row[1] for row in warm])
            summary[key + '_interval_ms'] = stats([(b[0]-a[0])*1000 for a,b in zip(warm, warm[1:])])
        summary['source'] = window.backend.status
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(dict(summary=summary, records=records)))
        print(json.dumps(summary, indent=2), flush=True)
        if args.no_mask:
            for plugin in window.manager.plugins:
                if plugin.id == 'map_reveal':
                    plugin.settings['hide_native'] = original_settings[plugin.id]['hide_native']
        stopper.stop()
        if not args.keep_open:
            window.close()
    QTimer.singleShot(args.seconds * 1000, save)
    stopper = QTimer(window)
    stopper.timeout.connect(lambda: save() if stop_file.exists() else None)
    stopper.start(250)
    capture_file = args.output.with_suffix('.capture')
    capture_file.unlink(missing_ok=True)
    def capture_overlay():
        if not capture_file.exists():
            return
        capture_file.unlink(missing_ok=True)
        window.overlay.grab().save(str(args.output.with_suffix('.overlay.png')))
        marks = [dict(kind=m.kind, x=m.x, y=m.y, color=m.color, size=m.size, value=m.value,
                      text=m.text, payload=m.payload if isinstance(m.payload, dict) else None)
                 for m in window.overlay.marks if m.kind != 'terrain']
        args.output.with_suffix('.overlay.json').write_text(json.dumps(dict(
            marks=marks, entities=window.snapshot.entities, status=window.backend.status,
            enabled=[p.id for p in window.manager.plugins if p.enabled],
            plugins=[dict(id=p.id, settings=p.settings) for p in window.manager.plugins if p.enabled]),default=str))
        print('OVERLAY_CAPTURED', flush=True)
    capture_timer = QTimer(window)
    capture_timer.timeout.connect(capture_overlay)
    capture_timer.start(250)
    print('CAPTURE_READY', flush=True)
    app.exec()


if __name__ == '__main__':
    main()
