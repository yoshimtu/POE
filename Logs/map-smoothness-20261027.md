# Map motion investigation — October 27, 2026

All game access was read-only. No gameplay inputs were sent.

## Findings and changes

- Full snapshot reads were dispatched by the 16 ms UI timer. A finished read could wait an additional frame before the next one started. A continuous background worker now schedules reads independently of rendering.
- On this machine `threading.Event.wait(.002)` measured approximately 15.5 ms; `time.sleep(.002)` measured approximately 2.5 ms. Short high-resolution sleeps now pace the worker, with reset/close checked at most every 5 ms.
- Map interpolation retained only two samples despite a 33.3 ms visual delay. When updates arrived faster than the delay, the buffer did not contain the correct pair. A bounded sample history now interpolates the appropriate pair. The delay, projection, terrain heights, zoom, and pan calculations are unchanged. There is no velocity extrapolation or predicted gameplay data.
- Entity-tree mutation occasionally discarded an otherwise valid map snapshot. Entity traversal failures now withhold entities/hazards independently. Final player/session/area checks still reject a genuine zone change.
- The native-line detector expanded entire viewport channels into signed arrays. It now runs the same color test in byte operations and evaluates signed background residuals only at candidate pixels. A randomized parity test verifies identical classifier pixels.
- The overlap mask now requires two observations aligned in map coordinates, with a two-pixel confirmation tolerance, before clearing added lines. This targets transient scenery mistaken for native lines. It introduces a confirmation wait for newly detected native lines, not additional map-motion delay. Full explored-area/fog detection remains unimplemented.
- Capture stops when PoE loses foreground focus, the map is unavailable, or the feature is disabled.

## Measurements

Raw traces are saved under the ignored `.reference` directory. Instrumentation records CPU time inside the paint handler; it does not measure monitor presentation latency. All samples below exclude the first five seconds. Different live passes are not controlled benchmarks of identical game load.

| Measurement | Initial walking pass | First revised walking pass | Final scheduling check |
| --- | ---: | ---: | ---: |
| Read-start interval, median / p95 | 31.9 / 48.4 ms | 30.5 / 42.5 ms | 17.1 / 20.2 ms |
| Read duration, median / p95 | 9.4 / 44.1 ms | 14.6 / 42.5 ms | 9.6 / 17.9 ms |
| Paint CPU time, median / p95 | 8.0 / 12.2 ms | 7.9 / 13.2 ms | No foreground paints |
| Native-line processing, median / p95 | 89.7 / 136.5 ms | 44.9 / 77.4 ms | 49.1 / 72.7 ms |

The final scheduling check was stationary with PoE in the background; its capture data predates the new foreground-only capture gate. It verifies reader scheduling, not movement or final foreground rendering quality.

In the walking traces, frames with a held pose during measurable movement fell from 334/1515 (22%) to 101/1603 (6%). Error relative to the recorded trajectory delayed by the existing 33.3 ms fell from 3.65 to 0.98 pixels at p95. Observed post-stop settling was approximately 51 ms initially and 37–39 ms in revised traces. These are pose-trace measurements, not independent visual alignment measurements. The user still saw occasional one- or two-frame hitches and briefly disappearing patches, then accepted the current smoothness for now.

With native-line hiding disabled, paint CPU time measured 5.7 / 8.5 ms median / p95 and held movement frames fell to 20/1568 (1.3%). This supports investigating the filter as a source of contention and intermittent suppression; the user did not explicitly confirm whether disappearing patches stopped. The subsequent temporal confirmation change awaits visual review.

## Validation and limits

44 automated tests pass. New coverage checks uniform interpolation with multiple buffered samples, stopping without overshoot, instance reset, nonblocking reads, generation rejection after reset, continuous reads without UI polling, entity failure isolation with core zone-change rejection, exact classifier parity, transient-line rejection, translated-line confirmation, and focus-loss capture shutdown.

The live traces contain only The Southern Forest. No live zone transition was recorded; live zone-change verification remains pending. Automated instance/area-change tests passed.

The reported possible monster-overlay crash coincided with the diagnostic window's 120-second timer. It exited with code 0 after saving a complete trace at 120.96 seconds, without a module exception or crash traceback. This is evidence of normal timed shutdown, not proof that an unrelated monster-triggered crash cannot occur. The replacement diagnostic session was configured to remain open after capture.

A subsequent read-only live snapshot contained 51 monsters. The radar produced and painted 51 markers, and the health module painted one eligible living enemy health bar without an exception. This was an offscreen rendering check of current data, not a sustained combat or movement test.

No painting-format or projection changes were adopted. A premultiplied-image experiment was faster but changed edge alpha values, so it was left out.

Release `releases/20261027-142235/ObsidianExile/ObsidianExile.exe` built successfully. The packaged ten-module smoke check returned no errors, with every module disabled by default. Archive inspection confirmed the final high-resolution pacing and native-line confirmation code are included. The diagnostic session was closed and replaced with this normal packaged app, with no automatic shutdown timer.
