# Remaining playtest audit and performance work

## Changes

- Breach detection now has a native MinimapIcon-name fallback (exact Breach icon), in addition to interaction asset paths. Profile-backed icon-definition pointer +0x20 and name pointer +0 were checked live on AbyssCrackActive, AbyssPitActive and BrinerotStores. Component ownership/name syntax checked; unknown/unreadable icons do not invent locations. Breach itself still needs a naturally encountered sample.
- Expedition object filtering now covers Expedition, LeagueExpedition and LeaguesExpedition namespaces. This closes the chest alias found in the upstream IconsBuilder source. Rune/remnant/chest assets cannot fall back to ordinary chests, even if the ordinary-chest category is enabled. Expedition NPC map dots are suppressed so the detonator remains the encounter marker. Settings label updated to Expedition encounter.
- Fast visual actor read failures now omit the update instead of falsely reporting death. Confirmed life=0 still removes bars immediately. Main records still expire normally; this does not extend stale snapshots.
- Fast camera polling continues when health bars are enabled but the actor list is empty, avoiding a camera refresh-rate drop after the last monster dies.
- Consecutive identical, unlabeled filled radar circles use one native drawPoints call with round caps. Labels, hollow circles, style/clip changes and bars retain order/individual rendering. Regression checks cover subpixel bounds, opacity, clipping, nonmutation and grouping boundaries.
- Overlay paint timings now log p50/p95/max every ten seconds, alongside existing update timings. Synthetic 1920x1080 stress scene, 2000 dots + 200 bars, 30 paints each: individual p50 27.16ms/p95 32.79ms; batched p50 19.43ms/p95 23.18ms. This is ~28% lower median paint time, not a promised live frame rate. The running prior build's idle 92-entity scene logged typical update p50 3.2ms, p95 5.4–6.0ms.

## Prior requested fixes retained

Crafting recipes use campaign-only IDs and hide unavailable controls (account recipe unlock state not decoded). Eater altar used-state change was live-verified by the user; Exarch shares the same targetability handling. Route destination clearance accepts 1–5; unknown maps discover dedicated transition tiles as approximate destinations; Strand Arena has a verified zone-load marker. Null source tiles no longer abandon height decoding, restoring ground paths on affected maps. User confirmed whole-overlay flickering resolved before these additional changes.

## Validation and limits

Final full suite: 208 passed, exit 0, 2.92s. Earlier test runs completed assertions but sometimes crashed during Qt interpreter teardown; test cleanup now schedules C++ widgets for deletion while QApplication and callbacks still exist. Source tests include native icon ownership/name validation, all Expedition aliases, campaign/map recipes, used altars, continuing camera polling without actors, and failed-read versus death semantics.

Still needs user playtest when convenient: one naturally encountered Breach, one Expedition encounter for single-marker confirmation, and one busy pack with usual modules enabled. Further map exceptions can be handled from captures as encountered; the shared route fixes do not require visiting every map. No gameplay input sent, no character movement, no new account unlock offsets guessed.

References checked: https://github.com/exApiTools/IconsBuilder/blob/master/ChestIcon.cs and the existing local ExileAPI layout reference. No external runtime introduced.

Evidence: .reference/away-audit-tests-final.txt; .reference/radar-stress-timing.json; .reference/radar-stress-individual.png; .reference/radar-stress-batched.png.
Release 20261029-171310: packaged module check and isolated native route-worker check both passed; previous owned app/worker closed and updated app launched.
