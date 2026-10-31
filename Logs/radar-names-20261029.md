# Named objects and mechanic anchors

The user reported Verisium labelled Encounter and a missing Brinerot encounter. Read-only captures in Cells found the exact Verisium world entity and an unclassified Tangle altar. A complete world-list capture contained 723 successfully decoded entities, including eight separate MineralClaimedMarker decorations; the active radar snapshot contained 292 classified entities. No Brinerot world entity was present in that capture. The user had previously been near it but was no longer there.

A full current-generation preload scan identified these exact Allflame instance assets: `Metadata/Chests/LeagueDeepwater/BrinerotStoresChestEncounter`, `Metadata/Chests/LeagueDeepwater/CursedTreasureChestEncounter`, and their corresponding `Metadata/Terrain/Leagues/Deepwater/Objects/...Spawner` assets. Previously the actual chest matched the ordinary-chest category, which starts hidden. Resource presence is not treated as a map coordinate or proof that a chest remains unopened.

## Changes

- Named Settlers deposits get their own category, including Verisium Outcrop. Claimed markers, ore growths, sub-spawners and decorative assets are excluded. The prototype DemonCopper alias uses the conservative Ore Deposit fallback until its display identity is validated; it is not guessed to be another named ore.
- Brinerot Plunder and Cursed Treasure use a dedicated Allflame category, independent of ordinary chests. Known encounter spawners and actual chests both match before generic rules.
- Eldritch altars now have named Eater of Worlds / Searing Exarch mappings. The loaded Tangle altar and Verisium both decoded correctly in a subsequent live read.
- Delirium mirrors, Smuggler's Caches, Sacred Grove entrances, Blight pumps, Abyssal Troves/entrances, named strongbox types, Incursion portals, Syndicate supplies and Labyrinth trials have specific mappings where the asset is known.
- Harbinger controllers and known league NPCs are treated as mechanic anchors rather than requiring ordinary enemy-health data. Ordinary enemies retain their rarity/death behavior, and dead mechanic actors with positive max life are excluded. Availability changes do not falsely consume persistent NPCs.
- New category rows expose show/color/radius/label controls in the existing Encounters settings tab. Existing settings migrate through the normal defaults mechanism; modules remain off at startup.
- Generic or empty Render names do not overwrite specific fallback labels. Remaining unknown interactive encounters retain a readable type name instead of the single word Encounter. Effects and decoration paths remain excluded.

## Verification

172 tests pass, including specific names, level suffix normalization, ore/decorative exclusions, Brinerot visibility with ordinary chests hidden, per-category styling, used-object filtering, preserved specific names, actor classification and removal of dead anchors. Existing reader, prices, route and health-bar tests also pass.

`.reference/radar-names-validation-20261029.json` records a live Verisium Outcrop and Eater of Worlds Altar, both unused, under the revised categories. Brinerot asset matching is covered by the captured current-generation paths and regression tests; a live positioned Brinerot marker still requires user visual confirmation near that encounter. No map marker is fabricated from preload-only data.

Release `releases/20261029-085115/ObsidianExile/ObsidianExile.exe` passed the package check with no errors and all eight modules off by default. The previous release was closed normally and the updated application opened. The user can re-enable Monster & object radar and review the new Encounters controls.

Follow-up: the user clarified that the encounter was Cursed Treasure and returned nearby. A live read identified `Metadata/Chests/LeagueDeepwater/CursedTreasureChestEncounter` at grid (451,986), classified as Allflame / Cursed Treasure with `used=false` and `available=true`. Four function-only spawners and a decorative lamp were excluded. Capture: `.reference/cursed-treasure-live-20261029.json`. This validates the actual previously missed encounter without additional code changes; Brinerot remains a separately matched asset rather than the confirmed live example.
