# App settings and shared economy league

- Added a permanent Settings navigation tab. It contains the league selector/refresh/apply controls, PoE installation folder/browse/recheck controls, a remembered window size/position option and access to settings/logs.
- Removed league selection from the workshop. Compatibility retains diagnostics; installation selection now lives in Settings.
- Economy callers use one committed league ID: ground, inventory, personal/guild stash pricing, divine conversion, unique workshop lookups and feedback metadata. Typed league edits commit on Apply/finishing editing; changing displayed list names cannot accidentally reuse a stale item ID.
- League changes save immediately, clear in-memory estimates and enriched item prices, reset price-refresh backoff, hide obsolete value boxes and reject late quote responses from the previous league. Provider disk caches remain scoped by their existing league-aware query keys.
- Existing saved league values migrate in place. League display name and provider ID are retained separately when supplied by the provider. Settings works while workshop is disabled.
- Window geometry is restored within the primary screen bounds when enabled.
- 227 tests passed. Added shared-league persistence, typing/commit, stale callback, all-container invalidation and workshop-disabled pricing checks. Actual Settings widgets were visually inspected at `.reference/waymark-global-settings.png`.
