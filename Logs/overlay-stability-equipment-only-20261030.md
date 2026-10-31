# Overlay performance and rare equipment filtering

Confirmed two causes in code: expired/failed reader frames became empty snapshots that removed every overlay, and terrain-outline preparation plus cold affine raster fallback could run on the GUI thread. Historical logs contained GUI tick maxima up to 754ms and paint maxima up to 342ms; those records span earlier builds and are not proof of the latest session's exact cause.

Changes:

- Off-thread bounded terrain-outline generation for live data; one pending build, outdated results rejected. Preview stays synchronous for deterministic development rendering.
- Live terrain painting defers a cold raster to its worker instead of doing the expensive affine fallback synchronously. Existing same-instance coverage can continue drawing during patch refill. New instance images do not reuse an old zone raster.
- Repeated identical monster-icon marks batch painter state/clip/image setup. Pixel-equality tests cover overlapping alpha and clipping. No icon styles or rarity ordering are changed.
- A display-only frame cache covers short disconnected/missed reads, capped at 0.6 seconds from the last valid capture. This does not extend Snapshot.fresh or feed stale data into assessment/plugin logic. Loading, logout, focus loss, session/module changes, expiry and valid empty results clear immediately. Pinned assessments can retain their completed display during the same grace.
- Inactive preview painting is removed; module-list updates are throttled to four per second. Connections tables do not rebuild for unchanged shares or while the page is hidden. Fixed Stash search refresh to its actual page index.
- Added reader timing, GUI scheduling interval timing and slow-plugin logging alongside existing tick/paint timing.
- Metadata and item classes use positive equipment filters. Charts, maps and other non-equipment rares are rejected early, before item tooltip traversal. Unsupported hover signals clear the compact assessment rather than borrowing a previous item's rating.

Validation: 242 tests passed. Added missed-read/load/session/focus/empty-result regressions, deferred-raster tests, non-blocking map build tests, chart traversal rejection and icon pixel equality. Synthetic 1920×1080 frames with 5,000 identical icon markers plus 200 bars improved from median 77.92ms / p95 84.98ms to median 19.84ms / p95 30.87ms. This is a controlled renderer comparison, not a promise of those rates in PoE or unlimited-load performance.

Live follow-up: use the large map while moving through a busy pack, stop, then change zones. Watch for whole-overlay blanks versus motion stutter, old-zone outlines, and charts opening an assessment. The instrumentation distinguishes slow reads, slow module generation, painting and late GUI scheduling.
