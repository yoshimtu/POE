# Third-party components and reference material

This project's application and plugin logic is newly written. No ExileAPI, Radar, Awakened PoE Trade, Sidekick, or Path of Building source code is copied into the runtime. Reference DLLs and inspection tools live only in ignored `.reference` research files and are excluded from the application package. No redistribution permission is inferred for unlicensed upstream repositories.

The runtime uses dynamically linked PySide6 Essentials / Qt and Shiboken, available under LGPLv3/GPL/commercial licensing as applicable. The bundled Python runtime uses the Python Software Foundation license. PyInstaller's bootloader has its distribution exception. Keep the dynamically linked libraries replaceable. Package metadata/licenses remain available from the matching upstream distributions; review licensing before public redistribution.

- Qt for Python: https://doc.qt.io/qtforpython-6/licenses.html
- PySide6 Essentials distributions/source links: https://pypi.org/project/PySide6-Essentials/
- Shiboken: https://pypi.org/project/shiboken6/
- Python: https://docs.python.org/3/license.html
- PyInstaller: https://pyinstaller.org/en/stable/license.html

poe.ninja supplies market estimates and is not affiliated with this app. Path of Exile and associated game names are Grinding Gear Games' property. No publisher approval is claimed.

Independent layout research also consulted TehCheat/PoEHUD, Qvin0000/ExileApi and NelleYn/PoeAPI. The latter supplied measured-layout documentation; no upstream runtime code or assemblies are bundled.

Automatic route destination data in `plugins/routes/destinations.json` records factual game area identifiers, terrain asset markers and destination names, using [exApiTools/Radar's target table](https://github.com/exApiTools/Radar/blob/master/targets.json) as reference. Resolution, clustering, route search and presentation are independently implemented. Unsupported markers receive conservative generic labels rather than guessed named destinations. The small native route library is this project's own C source in `native/route_search.c`; its build uses the [Zig compiler distribution](https://github.com/ziglang/zig-pypi). The compiler is a development tool and is not bundled. The library uses Windows system CRT components.

The preload catalogue records factual resource identifiers and game-content names, referencing [TehCheat/PreloadAlert](https://github.com/TehCheat/PreloadAlert/blob/master/PreloadAlert.cs) and [PoEHelper's resource mapping table](https://github.com/TehCheat/PoEHelper/blob/master/config/preload_alerts.txt). No upstream runtime implementation is copied. Resource detections are possibilities; loaded entities provide separate Seen evidence. The references include older aliases and do not certify current-league coverage.

Map height processing and native-line masking use NumPy (BSD-3-Clause), OpenCV headless (Apache-2.0; bundled component notices apply), and Windows Capture (MIT). Sources: https://numpy.org/ , https://opencv.org/license/ , https://github.com/NiiightmareXD/windows-capture . Only the game window is captured; this does not inject or load code into PoE.


Bundled minimap artwork is sourced from the PoEDB and PoE2DB icon catalogs requested by the user: https://poedb.tw/us/MinimapIcons and https://poe2db.tw/us/MinimapIcons. Original Path of Exile / Path of Exile 2 artwork belongs to Grinding Gear Games. Asset source URLs are recorded individually in `plugins/radar/icon_catalog.json`; no ownership of this artwork is claimed.
