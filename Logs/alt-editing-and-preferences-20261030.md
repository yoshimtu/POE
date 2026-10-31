# Overlay cleanup, Alt editing and saved module states

- Removed the priced-total/unpriced-items footer from value summaries. Missing total estimates and missing Stash search estimates now display blank.
- Floating route, wealth, alert and uptime panels are click-through by default. Holding Alt reveals edit handles and permits moving/resizing, subject to their lock setting. Releasing Alt ends editing and saves an in-progress adjustment. The assessment resize grip is also Alt-only.
- Alt reveals a clickable × beside each displayed buff. Clicking adds its name to Buff uptime's Exclusions field; matching is case-insensitive. Removing an entry restores the buff. Exclusions save with the other settings.
- Plugin settings now serialize enabled state. Known plugin IDs restore it even if their code digest changes. Newly discovered modules remain disabled. Toggling saves immediately; shutdown preserves enabled states before stopping readers/overlays, then writes the preserved preferences. Module refresh retains states.
- Removed Overlay preview from the five-page navigation. Synthetic rendering helpers remain available to development tests.
- Existing shared local data directory remains unchanged across release folders.
- 221 tests passed, including Alt click-through/edit transitions, buff exclusion/restoration, saved enabled-state behavior on close/reopen and changed digests, and the revised navigation. Existing inventory-close and resizing tests also pass.

Live playtest: hold/release Alt over value/route/alert boxes; Alt-click a buff × then remove its exclusion; close/reopen Waymark with selected modules enabled.
