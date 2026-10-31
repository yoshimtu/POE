# Waymark raster skin

The panel, control-state atlas, and icon atlas were created with the built-in imagegen tool from the user's chosen concept B. Exact prompts and reference provenance are recorded in `prompts.json`. Original generated artwork is preserved as `*-source.png`.

Run `.venv-runtime/Scripts/python.exe tools/prepare_skin.py` to extract the runtime sprites. The extraction bounds follow the actual atlas frames rather than relying on generated gutter spacing. Small checkbox ticks and disclosure arrows are drawn deterministically for readability.

`exile/theme.py` renders cached textured panel backgrounds and nine-slice frames. Qt controls use the raster skins while retaining live labels, keyboard focus, mouse hit targets, accessibility names, and value bindings. Images do not contain settings labels or numbers. Color-picker swatches retain their actual configured color.

The Windows build includes the runtime PNGs; source atlases and generation notes remain in the project. Legacy data paths and saved module settings are unchanged.

`tools/preview_skin.py` renders the actual widgets with temporary settings and sample overlay data, without polling the game or sending input.
