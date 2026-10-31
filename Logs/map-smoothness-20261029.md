# Map motion and raster timing

The user reported whole-map jitter and confirmed that it affected the entire outline rather than isolated native-line-hiding patches. A read-only timing session ran with map reveal, radar, routes and item prices enabled. The baseline moved between Cells and The Southern Forest; the improved capture remained in The Southern Forest. These are user-driven live captures, not identical controlled benchmarks.

Baseline core/map samples had a 21.1 ms median interval and 82.8 ms p95. During moving samples, the newest pose was 34.4 ms old at the median and 102.1 ms at p95. The replay analysis counted 241 held moving UI poses out of 746 (32.3%). Whole-overlay paint time was 11.22 ms median / 23.63 ms p95. The native-line mask worker was also active and remains unchanged.

## Changes

The existing bounded fast visual reader now reads the player's native-map position, native pan/zoom/visibility and height correction. Map reveal can activate this reader independently of health bars or routes, including with no monster actors present. Instance/player/component validation stays in place. A separate map capture timestamp feeds the existing interpolation history; core life, input guards, collision data and inventory timestamps are untouched. A newly hidden native map can hide the overlay immediately rather than waiting for the full scene read. Existing interpolation delay is retained; no extrapolation or velocity prediction is introduced.

Terrain rasterization now uses a bounded asynchronous cache. Rotation/scaling is prepared off the UI thread, with direct rendering until a matching patch is ready. Moving frames reuse the prepared terrain patch. The cache is tied to the source image and affine basis, prefetches before the viewport reaches its border, rejects old generations, and falls back to direct rendering for large requests. Ready and in-flight rasters are bounded to eight million pixels each, at most about 64 MB combined in premultiplied ARGB32. The patch is modestly supersampled to preserve fractional-pixel positioning; a faster 1:1 prototype failed alignment tests because Qt rounded its translated image position and was not shipped.

The aligned raster benchmark on the same captured projection measured 4.95 ms median / 5.77 ms p95 for direct drawing versus 1.48 ms / 2.50 ms for the final cache. The earlier 0.65 ms prototype result is not representative of the final subpixel-accurate implementation. Qt's [QPainter documentation](https://doc.qt.io/qt-6/qpainter.html) discusses format-dependent raster performance and caching expensive drawing; actual choices here were tested locally.

Map reveal also exposes Drawing rate choices of 60/90/120/144 fps, defaulting to 120, and participates in the existing UI/visual-reader rate selection. These are requested rates, not promises of actual presented frame rates.

## Live comparison and validation

The user repeated walking, stopping and changing direction and reported that the comparison build was much better. The improved fast-reader work measured 3.46 ms median / 9.28 ms p95, with a 9.02 ms median active-reader interval. Moving map pose age fell to 8.04 ms median. The analysis counted 158 held moving poses out of 970 (16.3%). Whole-overlay paint time was 7.24 ms median / 19.13 ms p95. Stop settling relative to observed stopped samples remained about 42 ms median (baseline about 41 ms); sample counts are small, so these do not establish input latency. The improved capture did not contain a zone change; generation/zoom/closed-map transitions are covered by automated checks.

Trace analysis now separates map modes, clipping and affine bases so a mode/zoom switch cannot be treated as ordinary movement. Logs: `.reference/map-jitter-baseline-20261029.json`, `.reference/map-jitter-improved-20261029.json`, and `.reference/map-raster-subpixel-benchmark-20261029.json`.

## Town and hideout follow-up

At the user's request, live object radar markers and the route lines/Routes box are hidden in safe hubs. Route planning is stopped while hidden and restarts on return to a combat zone. Monster/health-bar preferences, map reveal, item prices and stash summaries are preserved. Shared safe-area detection handles hideout IDs, town IDs and known hub names, while avoiding false positives from combat map IDs containing Town. Synthetic preview remains available.

188 tests pass. Added tests exercise fast-map timestamp advancement, height-corrected position parity, stale-instance/closed-map handling, subpixel raster alignment, zoom/new-image invalidation, bounded raster allocation, safe-area object filtering, route/legend suppression and resumption, and combat-map Town-name exclusions. Existing route, health-bar, item and radar tests also pass.

Release `releases/20261029-152836/ObsidianExile/ObsidianExile.exe` passed its package check with all eight modules defaulting off and no errors. Archive inspection confirmed inclusion of the new safe-area and terrain-raster modules. The diagnostic app was closed normally and the packaged build opened for the user. The smoother movement has user confirmation; town/hideout visibility has automated coverage and remains available for normal in-game user QA.
