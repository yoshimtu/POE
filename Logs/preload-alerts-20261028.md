# Instance preload presets — 2026-10-28

The previous module only supported an empty custom-substring list. It now ships 58 named detections under 37 preset switches, with Mechanics, Strongboxes and Notables tabs, plus Display and Custom. The module itself still starts disabled. Existing custom patterns and display limits migrate without automatic activation.

## Coverage

- Mechanics: Breach, Abyss, Legion, Blight/Cassia, Delirium mirrors, Harvest, Expedition, Ritual, essence monoliths, Heist caches, Harbingers, Einhar, Alva, Niko/sulphite, Betrayal and Beyond. Tormented spirits are available but start off.
- Valuable strongboxes: Arcanist's, Diviner's, Cartographer's, Operative's, Gemcutter's, Jeweller's and Artisan's. Ordinary, Large, Ornate, Armourer's and Blacksmith's boxes start off. The user clarified that "higher rarity" meant these valuable types, rather than white/blue/yellow rarity; no loot-rarity prediction was added.
- Unique-specific asset detections share one switch and include Strange Barrel, Kaom's Cache, Empyrean Apparatus, Ashes of the Condemned, Deshret's Storm, Perandus Bank, Weylam's War Chest and four warband caches.
- Notables: special essences, five Legion generals, Abyssal Depths/liches, Chayula, Labyrinth trials and Vaal side areas.

The factual resource-name associations are editable in `plugins/preload/catalog.json`, using [PreloadAlert's predefined mappings](https://github.com/TehCheat/PreloadAlert/blob/master/PreloadAlert.cs) and [PoEHelper's resource table](https://github.com/TehCheat/PoEHelper/blob/master/config/preload_alerts.txt) as references. The matching and presentation code is independent. Aliases remain patch-dependent; inclusion is not a claim that every detection has been visually validated in the current league.

## Evidence and presentation

One compact colored row represents each named detection, rather than one row per resource file. Unique/notable and valuable-box rows have priority when the display limit is reached. The panel shows an overflow count, configurable position, width, text size and opacity, and hides in town/hideout by default. It stays click-through with the rest of the world overlay.

`Preload` means a matching current-generation resource was reported by the reader. It suggests possible content, not a guaranteed encounter, reward or unopened box. `Seen` means a matching entity was observed during this activation in the instance. That evidence is retained after leaving the entity and does not claim it remains available. No encounter counts or item rarity are inferred from file counts. Detections reset when the instance generation changes or the module stops.

Built-in rules use scoped metadata prefixes. Item/scarab names and generic particle names do not imply mechanics; shared `.ot`/`.ot.tok` templates are excluded. Custom substrings remain available for additional cases and can intentionally match those resources.

## Validation

The supplied nearby unopened white box in Cells decoded as `Metadata/Chests/StrongBoxes/Strongbox`. It is hidden by default, and its separate Ordinary strongbox option produces Seen evidence. Valuable/unique-box coverage is exercised with resource fixtures; those types still need ordinary live user review as encountered, without visiting every zone for setup.

All 111 tests pass, covering strongbox type defaults, resource aliases, common false positives, unique/special priority, evidence, instance-generation resets, custom-rule migration and incremental matching. UI checks/rendering cover the new settings tabs and panel; preview artifacts are `preview-preload-panel.png` and `preview-preload-settings.png`.

On 8,140 current-generation Cells resource names, initial matching took 13.79 ms. Rechecking the unchanged resource set took 0.216 ms median and 0.486 ms p95 over 100 samples. Resource scanning is capped at four times per second, independent of drawing FPS, and each raw resource is normalized/matched only once per activation/instance. The reader and memory offsets were not changed for this feature. Raw reports live in ignored `.reference/preload-*.json` files.

Release `releases/20261028-163807/ObsidianExile/ObsidianExile.exe` passes packaged module discovery with no errors; all nine modules start off, and the preload module produces its panel in the synthetic smoke check. The bundled catalogue hash matches the tested source file. The previous application was closed normally and the new build opened.
