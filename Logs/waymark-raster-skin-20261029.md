# Waymark visual rebuild

Implemented the user's requested image-based interpretation of concept B. Replaced the banner and sparse flat layout with a compact custom title bar, narrow navigation, close-set module ledger and settings inspector. The application's images are functional control skins, with text and values rendered live.

## Artwork and rendering

- Built-in imagegen produced the textured panel, normal/hover/pressed control atlas and twelve matching brass navigation/module icons. Originals and exact prompts are in `assets/skin/`.
- Runtime PNGs are extracted by `tools/prepare_skin.py`; the build copies only those runtime images, not the source atlases.
- Textures tile without stretching grain. Nine-slice frames retain corner detail. Controls retain a one-to-one border slice so thin raster edges do not vanish when reduced.
- Shared panel painting applies to routes, net worth, preload alerts and rare hover assessment. This changes presentation rather than reader or routing behavior.
- Background images are cached by size, with a bounded 24-entry cache. A synthetic three-panel draw measured 25.767 ms cold (including image loads), then 0.031 ms median / 0.033 ms p95 over 500 cached draws. These are background-paint timings, not live game frame timings.

## Interaction and persistence

- Checkboxes, buttons, tabs, dropdowns and numeric fields remain actual keyboard/mouse-accessible controls under the image skins.
- Map settings are grouped into Appearance, Alignment and Performance; sliders and numeric values are linked. All original setting keys and save/cancel behavior remain.
- Title bar supports dragging, double-click maximize/restore, minimize and close; outer margins support system resizing.
- Existing data directory, settings, assessment history, hotkeys and saved overlay positions are retained. Modules still start off.

## Validation

- Full suite: 216 passed, exit 0.
- After final raster border and sidebar label adjustments: eight UI tests passed, exit 0.
- Packaged application checks verify all seven plugins, 305 map icons and 30 UI skin images, with no errors.
- Actual packaged Windows screenshot inspected, in addition to isolated actual-widget previews for map, radar, pricing, routes and workshop. Overlay preview uses sample data, not a live game capture.
- No game input or gameplay action was performed for this visual rebuild.

Previews: `preview-waymark-installed.png` and `preview-waymark-skinned-overlays.png`.
