# Reader and presentation architecture rework

The user's busy-zone test still hitched and cut out. Its logs showed full memory reads at median 313.2ms / max 449.8ms, GUI ticks up to 456.5ms and painting up to 72.8ms with only 188 entities. Full-discovery age passing 300ms also disabled the independent visual lane and could repeatedly stop/start native map capture. Raising a display grace alone did not solve that dependency.

Rework:

- Full scene/item/terrain discovery now runs in a spawned process with its own interpreter, independent of the UI/visual reader's GIL. A background IPC receiver requests one frame at a time. Terrain/height/region/landmark fields transfer only when their identity changes; parent-side terrain objects retain stable identities between updates.
- UI polling never waits for a read, process startup or pipe deserialization. Existing profile validation and read-only adapters run inside the discovery process as well.
- Fresh pose frames independently validate state/session/player/area pointer, area hash/counter and actor ownership. They can drive world/map presentation while scene discovery is older than 300ms, bounded to a maximum two-second discovery context. This does not refresh metadata timestamps or item-assessment freshness. Explicit fast-reader session invalidation clears presentation.
- Pricing/alert/uptime display can retain a completed frame for short discovery gaps. Item prices and automatic sharing still require metadata freshness.
- Native-map capture construction and teardown are queued on a dedicated lifecycle worker, with generation checks rejecting old callbacks. A slow GPU capture stop no longer blocks the GUI.
- The previous chart filter and icon batching remain.

Validation includes a real spawned synthetic reader doing 350ms of GIL-bound work per frame. Six scene frames arrived with one stable parent terrain identity; parent event-loop interval p95 was 8.51ms and max 8.68ms in that run. This is an isolation test, not proof of game-frame pacing. The packaged worker is checked separately using `--check-discovery-worker`.

The user's live playtest remains the acceptance check. This change addresses the measured dependency and stalls; it does not claim zero latency under arbitrary load.
