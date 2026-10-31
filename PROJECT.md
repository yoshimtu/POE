# Waymark project guide

Source inspection and test baseline: October 31, 2026. This guide describes the local source, not a guarantee that a game patch or hosted service is compatible today.

## Purpose

Waymark is a Windows desktop companion for Path of Exile 1. It combines a PySide6/Qt interface, external overlays, removable feature modules, item assessment and economy estimates, and opt-in group sharing. Game access is read-only: the app does not move characters, send gameplay inputs, inject code, or write game memory.

The old ObsidianExile name remains in storage and older build artifacts for compatibility. The current package name is `waymark`; `Build.ps1` produces `Waymark.exe`.

## Source map

| Location | Responsibility |
| --- | --- |
| `main.py` | Multiprocessing-safe entry point; dispatches desktop, standalone sharing server, and discovery/routing worker checks. |
| `exile/app.py` | Main Qt window, settings inspector, navigation, feature coordination, timers, economy jobs, and overlay composition. |
| `exile/model.py` | Shared `Snapshot`, `Mark`, `Plugin`, and context contracts. |
| `exile/platform.py` | Windows game-window detection, bounded read-only process memory, and hotkey/window boundary. |
| `exile/backend.py`, `profiles/steam_reader.py`, `exile/reader.py` | Exact-build profile selection, adapter construction, process checks, and native data decoding. |
| `exile/reader_process.py`, `exile/visual.py` | Isolated scene discovery and fast bounded actor/camera/map refresh. |
| `exile/plugins.py`, `plugins/*/plugin.py` | Dynamic feature discovery, saved preferences, per-plugin failures, and feature rendering. |
| `exile/terrain.py`, `terrain_raster.py`, `native_map.py`, `mapview.py`, `projection.py` | Terrain/height decoding, asynchronous raster work, native-map overlap filtering, motion, and projection. |
| `exile/navigation.py`, `routing.py`, `native_route.py`, `destinations.py`, `native/route_search.c` | Grid paths, background planning, C acceleration, destination resolution, and projection of routes. |
| `exile/items.py`, `rare_scoring.py`, `rare_inventory.py`, `assessment.py`, `hover_assessment.py` | Copied/hovered/native item interpretation, heuristic ratings, crafting potential, and assessment UI. |
| `exile/economy.py`, `valuation.py`, `prices.py` | poe.ninja queries/cache, item enrichment, quote matching, totals, and price formatting. |
| `exile/feedback.py`, `feedback_view.py`, `assessment_controls.py` | Local assessment feedback/history and controls. Votes do not automatically retrain scores. |
| `exile/overlay.py`, `presentation.py`, `floating_panel.py`, `wealth_panel.py`, `route_legend.py`, `preload_panel.py`, `theme.py` | Drawing, bounded presentation continuity, floating panels, and shared visual styling. |
| `exile/connections.py`, `sharing.py`, `sharing_server.py`, `firebase_auth.py`, `firebase_sharing.py`, `internet_host.py` | Group UI, HTTP client/server, SQLite persistence, Firebase authentication/storage, and optional tunnel helper. |
| `profiles/` | Exact-build JSON layout/capability data and adapter; includes validated read-only and unvalidated candidate profiles. |
| `assets/` | App artwork, runtime skin PNGs, provenance, and compressed rare-modifier catalog. |
| `tests/` | pytest coverage and captured/synthetic item fixtures. |
| `tools/` | Packaging helpers, profile diagnostics, live research, timing tools, and visual previews. Inspect a tool before running it; some access the game or external services. |
| `Logs/`, `designs/`, `exports/` | Historical validation/design records and exported artifacts; not the active implementation. |
| `.reference/`, `.venv*`, `build/`, `dist/`, `releases/`, `__pycache__/` | Research, environments, generated packaging output, or caches; do not treat these as application source. |

Additional references: `README.md` (user workflows/history), `profiles/README.md` (adapter validation), `MULTIPLAYER.md` (sharing), `THIRD_PARTY.md` (dependencies/assets), and `assets/skin/README.md` (skin preparation). External links in those files were not revalidated for this documentation task.

## How the systems interact

1. `main.py` starts `exile.app.main()`. The desktop locates resources through `storage.resource_root()` and reads user settings through `storage.data_root()`. Frozen packages use PyInstaller's `_MEIPASS` resource directory, normally `_internal`.
2. `Backend` hashes the configured `PathOfExileSteam.exe`, reads the Steam manifest build, and selects only a profile with matching hash/build and `validated=true`. It checks the running process path, snapshot type/source/freshness, and life bounds; exposed capabilities are limited by the profile. `profiles/steam_reader.py` supplies the adapter backed by `exile.reader`.
3. The active desktop imports **`ProcessLiveReader` from `reader_process.py`**, not the older threaded `LiveReader` in `live.py`. A spawned process discovers scene data; an IPC thread receives latest snapshots and reuses terrain arrays until their identity changes. Generation checks reject results after resets.
4. `VisualReader` independently refreshes bounded visual data on a worker thread. Session/actor identity and age checks govern merging. `Snapshot.fresh()` defaults to 0.3 seconds; visual continuity has separate bounded checks (including scene age up to two seconds). Do not replace these with one blanket freshness rule or renew metadata age from a visual pose.
5. The Qt tick composes camera/map/entity motion, valuation, and enabled plugins. Required capabilities and scene validity gate feature execution. Plugins return `Mark` objects; shared overlays/panels draw them. Plugin exceptions disable that module and are logged. Presentation caches bridge only bounded interruptions. Focus and safe-area rules also govern visibility/work; radar/routes suppress combat displays in towns/hideouts.
6. Route planning and terrain raster work run asynchronously. Routing workers can use the local C library through `ctypes`; Python pathfinding remains a fallback when the DLL is unavailable. The DLL receives a collision-grid copy, not access to the game process.
7. Item assessment normalizes copied text or native tooltip/mod records into explainable heuristics. Rare quality/crafting assessments are not learned sale prices or full build simulations. Economy requests use poe.ninja, disk TTL caches, ETags, and HTTP 429 backoff; unknown prices are not replaced with invented values.
8. Connections publish selected item/tab data only after opt-in. Normal Internet **Host** currently uses Firebase when no external server is entered. LAN hosting starts the local HTTP/SQLite server; an existing HTTPS server is also supported. A separate Cloudflare tunnel implementation remains available in code. Saved sessions and group snapshots can outlive a connection; disconnecting does not withdraw published tabs.

## Modules and conventions

There are eight source modules with `plugin.py`: `map_reveal`, `routes`, `radar`, `preload`, `hazards`, `uptime`, `pricing` (Items & stash), and `workshop`. Old `auto_flask`, `health`, and `stash` bytecode directories are not active source modules. `tools/stage_plugins.py` excludes bytecode and stages only directories containing `plugin.py`.

Each module exports `create_plugin()` returning a `Plugin` with a stable ID, metadata, defaults/settings fields, optional capability requirements, `tick(snapshot, context)`, and `stop()`. Discovery restores only known setting keys; migration hooks handle older module settings. New plugins default off, while known states persist. The app also explicitly migrates legacy workshop preferences. Plugins/adapters are trusted executable Python, not sandboxed extensions.

The code uses dataclasses for shared contracts, dictionaries for many decoded records/settings, monotonic timestamps for freshness, and explicit bounds/identity checks for native data. Formatting is mixed: some files use conventional spacing and annotations, others compact expressions. Match the local style rather than reformatting whole files. Layout offsets belong in profiles; editable destinations, preloads, and icons live in `plugins/routes/destinations.json`, `plugins/preload/catalog.json`, and `plugins/radar/icon_catalog.json`.

## Dependencies and local development

Use PowerShell from the project root, with `uv` installed and Python 3.12 or newer available. Windows is the actual application target. `pyproject.toml` declares:

- `PySide6-Essentials>=6.8,<7` for Qt UI/networking.
- `numpy>=2.2,<3` and `opencv-python-headless>=4.10,<5` for arrays/images.
- Windows-only `windows-capture==2.0.1` for native game-window overlap detection.
- Development group: `pytest>=8` and `pyinstaller>=6`.

`uv.lock` records resolved dependencies. The uv override suppresses the ordinary `opencv-python` dependency because the headless wheel supplies `cv2`, avoiding another GUI toolkit. Firebase/HTTP and SQLite code use the Python standard library rather than a Firebase SDK. The build-only Zig 0.13.0 compiler is fetched separately by `Build.ps1`. `tools/fix_bundle.py` uses `pefile` from the Windows packaging dependency environment.

```powershell
# Install/synchronize the locked development environment.
$env:UV_PROJECT_ENVIRONMENT = Join-Path (Get-Location) '.venv-runtime'
uv sync --locked --group dev

# Run the desktop (the launcher also selects .venv-runtime).
.\Start.ps1

# Full automated suite.
uv run --group dev pytest -q

# Example focused checks using existing test files.
uv run --group dev pytest -q tests/test_reader.py tests/test_reader_process.py tests/test_visual.py
uv run --group dev pytest -q tests/test_routes.py tests/test_native_route.py
uv run --group dev pytest -q tests/test_ui.py tests/test_global_settings.py
```

`Start.ps1` runs `uv run python main.py`. The installation path comes from saved settings, with a default of `D:\SteamLibrary\steamapps\common\Path of Exile`; configure the actual local installation for live reading. Do not assume that default exists on another machine. No game credentials/session cookie are required.

User data stays at `%LOCALAPPDATA%\ObsidianExile`: `settings.json`, `assessment-feedback.json`, `economy-cache/`, `obsidian.log`, and sharing-related local state. Settings include positions and module preferences; sharing sessions can contain sensitive tokens. `storage.write_json()` uses a temporary file and replacement, with a Windows redirected-folder fallback.

## Build and verification workflow

```powershell
.\Build.ps1
```

The script selects `.venv-runtime`, compiles `native/route_search.c` to an x64 Windows DLL when missing or older than the C source, stages active plugin files and runtime skin PNGs, and invokes PyInstaller in windowed one-directory mode. It explicitly bundles profiles, the rare-mod catalog, artwork, native DLL, documentation, and worker imports. It then checks/fixes a specific incompatible ICU DLL collision with `tools/fix_bundle.py`.

Output is `releases/<timestamp>/Waymark/Waymark.exe`; build intermediates are under `build/<timestamp>/`. Keep the full application folder, including `_internal`. The root `.spec` files and old `dist/ObsidianExile` are not the entry point used by `Build.ps1`.

Source/package synthetic smoke-check support is implemented in `exile.app.main()`:

```powershell
$env:UV_PROJECT_ENVIRONMENT = Join-Path (Get-Location) '.venv-runtime'
# Use fresh temporary report paths; the command writes a JSON report.
uv run python main.py --check-package "$env:TEMP\waymark-source-check.json"
# After a build, replace <timestamp> with its actual output directory.
& '.\releases\<timestamp>\Waymark\Waymark.exe' --check-package "$env:TEMP\waymark-package-check.json"
```

Inspect the report's `errors` and process exit code. This checks module discovery/synthetic ticks and bundled map icons/skin assets; it does not prove a live reader or server works. `main.py --check-discovery-worker <report>` and `--check-routing-worker <report>` provide synthetic worker checks. `tools/check_sharing_server.py <executable> <report>` exercises a packaged server with temporary local clients/database.

For ordinary work: inspect affected contracts, make the smallest change, run focused tests, expand to the full suite for shared changes, then build/smoke-test when packaging or runtime resources are affected. UI changes also need visual review; memory changes need matching-build live QA for loading, focus, death, zone changes, and restart. Clearly separate those results.

## Verified baseline and limits

- On October 31, 2026, `uv run --group dev pytest -q` with `.venv-runtime` completed: **267 passed, 1 warning in 26.21 seconds**. The warning is a deprecated Qt `QMouseEvent` constructor in `tests/test_hover_assessment.py`. Native tests skip when the route library is absent; this run reported no skips.
- `tests/conftest.py` sets Qt to offscreen by default and manages QApplication/widget cleanup. Tests cover contracts, decoding, process isolation, map/routing, item valuation/assessment, settings/UI, and sharing. Passing offscreen/synthetic tests does not validate game visuals, production Firebase rules, or Internet availability.
- No application source was changed for this documentation task. No release build, package/worker smoke command, interactive desktop review, live game read, external economy/Firebase request, or server deployment was performed. Build/smoke commands above were checked against code, not executed here; explicit `uv sync --locked` was also not run separately.
- This workspace is **not a Git repository** (`git status` reports no repository). No CI configuration was found in the project root. `.gitignore` exists but does not itself provide version control or a recoverable history.

## Known limitations and technical debt

- The validated profile targets Steam build `25113903` and one executable hash. Other clients/patches are not implicitly supported. Its `validation.confirmed` and `validation.pending` lists contain historical live evidence and outstanding checks; `validated=true` is not blanket certification. The candidate is unvalidated. `tools/check_profile.py` only reports root/hash/signature candidates, not complete field-layout compatibility.
- Loading/restart/combat, encounter coverage, camera/elevation, DPI/multiple-monitor behavior, and specialized stash layouts still need live checks. Windowed/borderless play is required by the documented external-overlay workflow. Native-line overlap detection is color-based capture filtering, not a native fog-of-war mask.
- Only loaded stash tabs can be decoded. Shared snapshots may be stale; unknown prices and incomplete item/mod recognition limit totals and ratings. Preload resources suggest possible content; observed entities are separate evidence.
- `exile/app.py` combines substantial UI and coordination logic. Snapshot records also gain dynamic attributes outside the dataclass. Changes can cross reader, visual, plugin, and presentation boundaries; follow existing tests and trace callers before altering a record.
- Older documentation has drift: README validation prose still mentions removed flask behavior and an older background-reader design; earlier module counts differ. `MULTIPLAYER.md` includes an older sentence saying Host uses a temporary tunnel, while `Connections.start_host_group()` currently defaults to Firebase. This guide records the inspected code; preserve useful historical evidence without treating all dated statements as current behavior.
- Generated releases, old bytecode, preview images, and research files make broad searches noisy. Scope searches to source directories and exclude generated output. Build staleness checks use C-source/DLL timestamps, so native build-option changes may require an intentional rebuild.
- Hosted Firebase availability/rules, tunnel helpers, provider terms, and distribution/license completeness were not externally audited. `firebase.rules.json` is a local rules artifact, not evidence of what is deployed. Invites/session tokens and published stash data need the care described in `MULTIPLAYER.md`.

## Suggested next improvements

Initialize version control and save a reviewed baseline before further feature work. Reconcile the stale README/multiplayer passages in a separate documentation change. Add automated Windows test/build checks once Git hosting is chosen, and maintain a short repeatable live-QA checklist from the profile's pending cases. These are recommendations, not work performed here.
