# Waymark



A standalone Windows desktop app for Path of Exile 1, with a dark-and-gold interface and individually removable modules. This is a development build with an independent read-only memory reader for Steam build `25113903`, selected by exact executable hash. Hideout data has been checked live; combat, visual alignment, loading and process-restart checks remain incomplete.



## What works now



- Module discovery, enable checkboxes, individual settings dialogs, search and refresh.

- Known modules restore their enabled state and settings across restarts and upgrades. Newly added modules start off.

- English copied-item parsing and explainable rare-equipment ratings. Unsupported or unknown modifiers remain explicitly unknown. Ratings are approximate quality/synergy assessments, not learned prices, exact affix-tier assessments, or PoB calculations.

- Current economy league discovery and unique estimates from poe.ninja, with disk caching, ETags and request backoff. Link counts, corruption and same-name variants are kept separate. Missing total prices display as blank.

- An explicit synthetic preview for rendering map terrain, routes, radar, health bars, hazard rings, buffs and stash labels. It cannot send gameplay inputs.

- A transparent, noninteractive game overlay window and read-only Windows process-access boundary, ready for a validated data adapter.

- Local rare-assessment feedback: Up = higher, Down = lower, Right = looks right. Assessment history saves the full example and explanation for later review.



## Live implementation status



| Module | Implemented logic | Remaining live integration |

| --- | --- | --- |

| Full map reveal | Loaded terrain projected onto the visible native map/minimap | Combat/transition checks; does not patch native map discovery; elevation alignment remains unverified |

| Route overlay | Automatic terrain destinations, ground-projected walkable paths, draggable legend, stable colors, isolated native search and stability controls | Latest stability tuning and sustained zone/encounter QA |

| Monster/object radar + health bars | Rarity colors, per-category circles, life/death and ally filtering, world/map bars, waypoint and encounter rules | Encounter-specific coverage and sustained combat QA |

| Preload alerts | 58 grouped detections for mechanics, valuable/unique boxes and notables; per-preset switches, custom patterns and compact panel | Current-generation resources suggest possibilities; Seen records an observed entity; asset aliases remain patch-dependent |



| Hazard highlighting | Volatile-core metadata matching and projected rings | Live lifetime/state and alignment |

| Buff/flask/defense uptime | Buff identifiers and durations | Friendly-name coverage and combat checks |

| Item prices/ratings | Copied-item workshop, ground/inventory stack-price badges, draggable container-worth/top-three summaries, unique reference ranges and rare ratings | Unknown items remain unpriced; rare live mod acquisition is incomplete |

| Personal/guild stash | Loaded-tab item decoding, searchable table, UI layout, currency stack totals and unique estimate ranges | In-game label alignment; unopened tabs unavailable; rare stash mods not decoded |





The independent reader uses patch-dependent values from `profiles/steam-25113903.read-only.json`. The live hideout checks matched life 2802, total mana 700, usable mana 39, collision terrain, entity/buff records, current-generation resource names, 37 stash tab records and 75 items across two loaded tabs. These counts describe the test session. Only loaded tabs expose contents. A user-controlled town/hideout trip changed the area generation; sampling during transitions is still pending.



Reference DLLs were used only in development to cross-check factual layouts. They are not loaded by the app or included in the release. A repository update date alone does not establish compatibility. The app contains no gameplay input sender.



## Run



With `uv` installed, right-click `Start.ps1` and run with PowerShell, or run:



```powershell

.\Start.ps1

```



The launcher installs the minimal Qt Essentials dependency into `.venv-runtime`. For a packaged build, run `Build.ps1`; its output identifies a timestamped folder under `releases`. Keep the complete application directory together; the executable needs its `_internal` folder.



1. Open **Modules** and switch on **Items & stash**.

2. Open **Item workshop**. Hover an item in PoE and press Ctrl+C, then use **Paste clipboard**.

3. For rares, press **Assess item**. Use the module's cog to choose a build preference.

4. For uniques, load/select the economy league and use Automatic category detection. Exact matches and reference-only variants are clearly distinguished.

5. Enable **Items & stash**, then open **Stash search**. Open tabs in game to load their items. Choose a league in Item workshop before loading unique/currency estimates (prices load automatically when Items & stash is enabled); unread corruption/roll variants remain ranges. Chaos labels use whole numbers; stacks above ten divines switch to divine values with up to two decimals.

6. Hold **Alt** to reveal overlay edit handles. Drag to move or use the bottom-right corner to resize. Release Alt for click-through display.



F9 stops all modules. Flask automation, its input sender and F8 arming have been removed. Windowed or borderless play is required for the external overlay. In-game DPI/multiple-monitor behavior has not been verified.



## Plug and play modules



Development modules live at `plugins/<module>/plugin.py`. Packaged modules live at `_internal/plugins/<module>/plugin.py` next to the executable. Add or remove a complete module folder and click **Refresh modules**. Refresh stops all modules. A broken plugin is reported independently. Modules are executable local code and are not isolated from the app.



`plugin.py` exports `create_plugin()` returning an `exile.model.Plugin`. Each module defines its metadata, required data capabilities, settings schema, and `tick(snapshot, context)` renderer/action logic. A module must not acquire its own game connection or bypass the central input context. `stop()` clears module state.



Offsets and decoding belong in `profiles`, separate from feature modules. See [profiles/README.md](profiles/README.md) for the adapter contract and exact-build validation requirements. The program does not silently fetch, execute, or mark upstream updates trusted.



Settings, economy cache and logs are in `%LOCALAPPDATA%\ObsidianExile`. No PoE credentials or session cookies are requested. The application does not launch the game, inject code or write game memory.



## Validation



```powershell

$env:UV_PROJECT_ENVIRONMENT = '.venv-runtime'

uv run --group dev pytest -q

```



Tests cover plugin removal/error isolation, defaults, pathfinding, item parsing, unknown modifiers, unique variants, synthetic rendering, flask rejection conditions, throttling, unverified-profile rejection and settings. Desktop launch/render and live poe.ninja requests were checked separately. Hideout memory data has been checked read-only; no gameplay inputs were sent. No ban-risk claim is made. Live QA is still required for every memory-dependent module, with special attention to stale data, loading, chat, process restart, projection and flask behavior.



## References



- https://github.com/exApiTools/ExileApi-Compiled â€” memory-reader and feature reference; upstream binaries stay in ignored research files and are not distributed.

- https://github.com/exApiTools/Radar â€” routing/radar reference.

- https://github.com/SnosMe/awakened-poe-trade â€” copied-item workflow reference.

- https://github.com/Sidekick-Poe/Sidekick â€” companion-app reference.

- https://github.com/PathOfBuildingCommunity/PathOfBuilding â€” reference for the distinction between heuristic ratings and build simulation.

- https://poe.ninja/docs/api â€” public economy endpoints and caching guidance. This personal build caches requests; public distribution should use a shared caching proxy and an app/contact User-Agent as the provider recommends.

- https://www.pathofexile.com/forum/view-forum/patch-notes â€” official patch reference; 3.29.3b was the latest numbered patch listed when checked.



Offset maintenance: `tools/check_profile.py` generates an offline hash/signature report without changing the active profile. It currently checks the file-registry and area-counter roots; other roots and all native field layouts still require review and live validation.



2026-10-26 feedback fixes: inline short item names, advanced-copy roll annotations, automatic unique-category fallback, broader exchange currency/card prices, automatic stash price loading, non-elided compact labels, and a shared native map projection for terrain/routes/radar. Map scale was checked against the reference reader at native zoom 0.5 and synthetic read-only zoom inputs 0.25/1.0. Large-map anchor was checked live; visual user review, elevation, other resolutions and specialized stash types still need QA.



2026-10-26 second feedback update: personal stash inventory IDs now resolve from each tab record rather than its position. Terrain supports dimensions up to 8192 per axis with a 32-million-cell allocation cap; The Beacon (3726 x 1656) was checked live. Terrain image construction uses a palette conversion instead of Python per-pixel RGBA writes. The item workshop uses a summary card, modifier/reference table, tier labels, synergy summary and separate implicit/enchant context; unique variants use a market table. Minion damage/speed, rarity, elemental/chaos resistance, recovery and other modifier families were added. Neutral modifiers contribute zero. A Minion build preference is available directly in the workshop.



2026-10-26 map stability update: a walking trace captured 347 discarded frames due to unknown buff identifiers. Buff-record failures now remove only the buff capability; optional preload/stash failures are isolated as well. Map rendering uses transparent-interior outlines, selectable muted gold/soft grey, and adjustable line width. A single background memory reader feeds a 16 ms UI render timer; map positions are interpolated for drawing only. Old jobs are rejected after reader resets, and stale snapshots still hide the overlay. Input data is never interpolated.



2026-10-26 alignment/overlap update: terrain tile heights are decoded independently (palette and raw samples, eight orientations) and projected with the playerâ€™s unclamped ground height. All 6,170,256 Beacon height samples matched the development reference exactly. The optional native-overlap filter uses Windows Graphics Capture targeted to the exact PoE window, detects its default lavender map lines, and clears nearby added lines. It does not read the native fog-of-war mask and does not claim that every explored interior is hidden. Detection is color-based; other native-map colors or unsupported capture/window modes may require disabling it. Frames stay in memory and are not saved or uploaded. Capture runs only while the map module and overlap filter are enabled. New dependencies are NumPy, headless OpenCV and Windows Capture; the packaged app includes their runtimes.



2026-10-27 radar update: enemy health bars are part of Monster & object radar; the standalone health module has been removed (nine modules total). Its existing width/filter preferences migrate to the radar. The cog has five tabs: Monsters, Health bars, Objects, Encounters and Display. Each circle category has its own visibility, color, radius and label option. Normal monsters start smaller and red, magic blue, rare yellow, and unique orange. Allies/minions and ordinary chests start hidden. Health-bar visibility, rarity filter, world/map anchoring, dimensions, offset, names and percentages are independent options.

Current-build monster rarity, ally reaction and display-name fields were checked read-only in The Riverways; the yellow Bramble Cobra / Einhar beast agreed with the reference reader. Corpses are hidden from fresh life data. Entity discovery retries changing trees; a brief fallback refreshes known identities and current component data, never cached health. Component replacement/owner checks prevent stale component reuse. Radar visual positions use fractional coordinates and the map's existing interpolation delay; health and death are not interpolated. Display offers 60/90/120/144 fps targets (120 default); actual throughput depends on rendering cost. Overlay frames explicitly clear their old transparent contents.

Waypoint, transition, portal, shrine, strongbox, quest/recipe and common encounter categories include Legion, Essence, Breach, Abyss, Ritual, Expedition, Harvest, Blight, Delirium, Delve, Heist, Ultimatum and Sanctum. Rules require loaded recognizable metadata/components; they do not locate unloaded objects or guarantee every encounter variant. Opened-chest and used-shrine states were checked against the reference. Other consumable objects are hidden after an observed available-to-unavailable transition persists for half a second; an object first loaded as unavailable is not assumed consumed. Waypoints, portals and area transitions remain visible.

Health-bar follow-up: a separate bounded visual reader refreshes known living actors' poses and life up to 120 times per second while the radar and health bars are enabled and PoE is foreground. It rechecks actor IDs, component membership/ownership, session and area boundaries. It stops when unnecessary and never extends the full snapshot's freshness. Body positions are interpolated in world coordinates with 8 ms smoothing by default (0â€“40 ms configurable), then projected with the latest camera. Camera motion is not interpolated through the map's delay. This avoids bars trailing a moving scene. An off-screen projection edge case was fixed and tested. The read-only profile still blocks automatic flask inputs.


## Ground route controls

Enable Route overlay, then use its cogwheel. Drawing frame rate controls line/camera refresh; Path refresh rate controls background searches. Balanced stability keeps a usable route when a new path offers only a small saving, while the nearby line follows your position each frame. Choose Always shortest for more frequent route changes or Prefer existing route for stronger stability.

Drag the small Routes legend to reposition it; its position persists. Lock it to make it click-through. Each named destination has one stable color, with the shortest reachable entrance selected from observed entrances. Recognized exits, boss areas and waypoints are found from the whole zone’s terrain on entry, with no per-zone calibration. Exact nearby entities refine those terrain approaches. Unrecognized layouts may still lack a named destination. Routes clear and regenerate automatically on instance changes. No character movement is automated. See [route validation notes](Logs/routes-20261028.md) for measurements and limits.

Route destination mappings are editable in `plugins/routes/destinations.json`; memory layout values remain in the matching profile JSON. Long live searches use the project’s own small compiled route library, with the Python implementation retained as a fallback. `Build.ps1` compiles that library when needed using a pinned development compiler; the compiler is not shipped with the app.


## Instance preload alerts

Enable Instance preload alerts, then use its cogwheel to choose Mechanics, Strongboxes and Notables. Valuable box types and known unique-box assets are enabled in the presets; ordinary boxes start off. Its enabled state is saved across sessions. Existing custom resource substrings remain supported.

The panel groups duplicate files into one named alert. Preload means possible content from loaded resources; Seen means an entity was observed here, including content already visited. It does not predict box rarity, count encounters or guarantee loot. Position, size, alert limit and opacity are adjustable. The editable mappings are in `plugins/preload/catalog.json`. See [validation notes](Logs/preload-alerts-20261028.md).


## Ground/inventory prices and worth

Enable Items & stash for in-box ground/inventory stack values and container summaries. Each Inventory, personal-tab and guild-tab worth box can be dragged independently; its position saves on release and survives reopening panels and restarting the app. Use the cogwheel to lock positions, reset them on Save, or adjust labels and summaries. Equipped items are excluded. Identical stackable items are combined before selecting the top three.

Totals include known prices and retain unique reference ranges; unsupported/unpriced items are counted explicitly. Only the currently identified loaded stash tab is totalled. See [validation and limits](Logs/item-prices-20261028.md).

### Hovered rare assessment

In **Items & stash → Assessment**, enable hovered rare assessment and choose **Always on** or **Hotkey only**. Hover an identified rare in PoE for its compact quality/utility panel. **Alt+F** opens a larger pinned breakdown in either mode; the shortcut is configurable. Close with × and hover again to reopen. The shortcut is registered while PoE is focused and the feature is enabled. F9 stops the feature with the other modules.

The independent reader reads only the hovered item's own tooltip, including styled text and attached advanced affix descriptions; it sends no copy command or other input and does not use the clipboard for this feature. The manual workshop remains available as a fallback. Panels hide when PoE loses focus, and pinned details clear on loading/instance changes.

Ratings include slot-specific reference rolls, complementary affix combinations, tier/within-tier roll information where supplied, and separate socket/link utility. Six linked sockets receive a prominent callout; socket/link utility does not change the numeric affix rating. Six unlinked sockets are distinguished. Common regular/abyss jewels are supported; cluster jewels, maps, flasks and unidentified equipment remain review-only. Unrecognized modifiers are explicitly marked for review rather than assumed worthless. These are transparent heuristics, not sale prices or safe-to-discard recommendations.


2026-10-28: Stash search and the item price overlay are combined in **Items & stash** (eight modules total). Its cog groups Ground & inventory, Stash, Net worth and Assessment settings. Existing stash search/scope/price/name preferences migrate automatically alongside saved summary positions. Stash search in the app uses the same module switch; overlay search filters do not change net-worth totals.


2026-10-29 scoring revision: General now selects the best supported build profile using multiple independent useful affixes. The shared model rewards complementary roles, coherent T1/T2 combinations and actual roll magnitude. Named hybrid affixes count as one affix, and low-value filler cannot earn tier bonuses. The panel shows the selected fit and an additive point breakdown. Socket utility stays separate from affix quality. Native quality-adjusted values are scored while base tiers/ranges remain visible. See [coherence validation](Logs/rare-coherence-20261029.md).


2026-10-29 radar naming audit: named ore deposits, Allflame treasure (including Brinerot Plunder and Cursed Treasure), Eldritch altars, mechanic anchors and common object subtypes now have specific labels/categories. The radar cog’s Encounters tab adds visibility, color, radius and label controls for these groups. Claimed ore markers, growths and effects stay hidden. Loaded resources alone never create a positioned marker. See [capture and validation](Logs/radar-names-20261029.md).


2026-10-29 map smoothness update: native map position/visibility now refresh through the bounded fast visual reader, independently of full scene/inventory reads. Terrain uses a bounded asynchronous subpixel raster cache; the Map Reveal cog adds drawing-rate choices up to 144 fps. Live object radar markers and route lines/legend hide in towns and hideouts, with route planning suspended until returning to a combat area. Item/stash prices remain available. See [timing and validation](Logs/map-smoothness-20261029.md).


## Assessment feedback

Enable **Items & stash**, hover a rare (or pin its breakdown with Alt+F), and press **Up** if its score should be higher, **Down** if it should be lower, or **Right** if it looks right. These shortcuts are active only while a rare assessment is visible and PoE is focused, or in the active workshop outside text controls. They can be disabled in the cog’s Assessment tab. The workshop also provides feedback buttons.

Open **Assessment history** to add an optional note and **Copy selected** or **Copy all** for this chat. Examples include modifiers, tier/roll data, sockets/links, the displayed rating and contributions, build preference and scoring-model version. Re-rating the same example updates its vote. Feedback is stored locally in `%LOCALAPPDATA%\ObsidianExile\assessment-feedback.json`; nothing is uploaded, the clipboard changes only when you click Copy, and saved votes do not automatically change scores. Passive flask-effect uptime tracking is still available.


## Waymark interface

The desktop uses the selected Wraeclast Field Kit direction: an iron-and-brass masthead, drawn navigation icons, compact module ledger and inline settings inspector. Select a module or its cog, edit its settings, then Save. Cancel restores the saved values. Checkboxes still enable each module separately; known module states are restored. Route, worth, alert and rare-assessment overlays share the same fine brass frame, while map icons and rarity colors retain their meaning.

Build output is `releases/<timestamp>/Waymark/Waymark.exe`. Existing settings, feedback history, prices and positions continue to use the established `%LOCALAPPDATA%\ObsidianExile` data directory for compatibility. No migration or reset is needed.


Overlay editing requires holding Alt. In Buff uptime, Alt also reveals an × beside each buff; click it to hide that buff. The Exclusions field in the module settings lists hidden buffs; remove a line to restore one. Price summaries omit unpriced-item captions. Overlay preview has been removed from navigation.
