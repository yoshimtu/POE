# Combined Items & stash plugin

Stash search and item assessment/price overlays now use one Economy module, Items & stash. Its settings have Ground & inventory, Stash, Net worth and Assessment tabs. Ground and inventory badges, stash overlay, stash prices, full names and summary boxes remain independently configurable. Stash overlay search matches names, bases, tabs and available mods; filtering never changes net-worth totals.

The stable pricing plugin ID preserves assessment preferences and independent draggable summary positions. Legacy stash query, scope, prices and name preferences migrate when a corresponding new setting is absent. New combined preferences take precedence, survive subsequent saves, and never enable the plugin automatically. The old stash plugin source is removed; eight modules remain.

All 121 tests pass, including migration precedence, serialization/reload, personal/guild visibility and filtering, independent switches, summary totals unaffected by search, and settings-dialog rendering.

Release `releases/20261028-203046/ObsidianExile/ObsidianExile.exe` passed its package check with all eight modules defaulting off and no errors. The previous build was closed normally and the new build opened for the user.
