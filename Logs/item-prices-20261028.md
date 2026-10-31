# Ground/inventory prices and container worth — 2026-10-28

Item assessment & prices now adds top-right, in-box price badges for visible ground labels and backpack item slots. Existing copied-item assessment remains available. Price labels use the shared rules: integer chaos values, divine formatting only above ten divine-equivalent chaos, no approximation prefix. Stack labels show the value of the whole stack.

## Data and valuation

The independent reader identifies the main carried inventory by native inventory type 0 and slots 0/84 (main backpack and an optional extra carried compartment). Equipped gear, flasks, cursor items, crafting and other containers are excluded. The current test exposed 54 items in the 12×5 backpack and an empty extra compartment. Inventory contents refresh at most every 0.5 seconds while the pricing module is enabled. Stash decoding remains shared with the existing module.

Ground labels follow the native UI list, validate WorldItem ownership and decode its actual item entity. Bounds, visibility, viewport containment and label identity are checked; hidden/removed labels do not receive a badge. The live dropped stack decoded as exactly 10 Vaal Orbs with a 160.65×38.475 pixel label. Inventory-open layout moved its label as expected. All 54 backpack item rectangles aligned through the inventory UI hierarchy. Patch-dependent addresses are in the matching external profile; reference assemblies are used only in ignored development research, never at runtime.

All three locations share the selected league's cached poe.ninja currency/category feeds and numeric unique reference ranges. The new numeric quote data avoids parsing display strings or summing rounded prices. Corruption/roll uncertainty remains a range. Stack quantities do not trigger separate network requests. Quotes from an obsolete league response are discarded, and current-label enrichment clears values when the selected league no longer matches.

Only known bulk-item values and unique reference estimates are included. Rares, maps/charts or other unsupported variants can remain unpriced. A name collision cannot give rare equipment a currency price. Summary totals explicitly report the unpriced item count; an entirely unpriced container displays Unknown, not zero. A known empty inventory can display 0c. Rare equipment ratings remain in Item workshop and are not invented numeric market prices.

## Container summaries

Inventory, current personal stash tab and current guild stash tab have separate compact summaries, each with its top three priced entries. Matching stackable items are consolidated before ranking, with quantities and numeric totals summed across all their stacks. Nonstackable rare/unique pieces are not assumed interchangeable. Physical entity IDs are deduplicated within each summary. Ground items are not included in owned net worth.

Personal/guild totals are scoped to the currently visible tab, including its decoded items beyond the overlay/query subset. Search filtering does not change total worth. Loaded items from other tabs are not added to the active tab. If no single active tab can be established from the current UI items (including an empty/not-yet-loaded tab), the panel says Reading tab rather than claiming a value for a guessed tab. Only loaded tab contents are available.

Each summary is an independent non-activating draggable window. Its movement consumes the click, while item badges remain click-through. Releasing saves a normalized top-left position immediately under `pricing.settings.summary_positions`, with separate `inventory`, `personal` and `guild` keys. These preferences survive hiding/reopening game panels and application restarts. Positions remain stable when row counts change, and clamp to the game client. Lock summary positions makes the windows click-through. Net worth settings also provide Reset saved positions, applied only on Save; cancelling leaves preferences intact. All modules still start off.

## Validation

The user confirmed that ground/inventory badges, inventory worth and stash values worked in the source test build, then requested movable boxes. The live calculation merged 11 Chaos Orb stacks into one 220-orb, 220c entry. The 10 Vaal Orbs were 3.213c before formatting, displayed as 3c. Inventory priced worth was approximately 23.4d with 18 items explicitly unpriced; subsequent live inventory changes altered those sample values normally.

All 119 tests pass, including aggregation before ranking, duplicate identity protection, unknown values, numeric unique ranges, separate inventory/personal/guild totals, scope selection, equipment exclusion, ground-label replacement/list bounds and stale snapshots. UI tests simulate dragging, saving JSON, reloading a new plugin/window, changing row counts, locking and foreground hiding.

Timing capture `.reference/item-prices-timing.json` recorded Qt tick work at 0.958 ms median / 1.585 ms p95. Reader work was 41.96 ms median / 104.91 ms p95 while both inventory and ground reading were active; these are whole-reader timings, not isolated feature costs. The initial renderer drew all badge text each frame. A bounded 128-entry raster cache now reuses unchanged badge images; a later 38-badge drawing check measured 0.519 ms median / 0.785 ms p95. Summary windows redraw when their values/settings change. No gameplay inputs were sent. Preview artifact: `preview-item-prices.png`.

Packaged release: `releases/20261028-180156/ObsidianExile/ObsidianExile.exe`. Its package check exited successfully with no errors and all nine modules defaulting off. The previous source diagnostic app was closed normally and the packaged application opened for the user. Persistence and dragging were verified by UI tests; the user has not yet confirmed dragging in this packaged build.
