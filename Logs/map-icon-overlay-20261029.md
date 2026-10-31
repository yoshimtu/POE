# Native map icon overlay

Bundled 303 PoE 1 minimap icons and the two requested PoE 2 assets RareMonsterAlive and UniqueMonsterAlive. Source URL/provenance per asset lives in plugins/radar/icon_catalog.json; source artwork credit added to THIRD_PARTY.md. All images decode locally as WebP, including under the packaged image-format plugin check. tools/refresh_minimap_icons.py refreshes the catalogs/assets from the two public source pages.

Object selection prefers the reader's verified native MinimapIcon identifier, then a category/specific-name mapping (ore, Eater/Exarch, Cursed Treasure, Brinerot). Rare and unique hostile monsters always use their respective PoE 2 alive skull icons; existing life/death, used-state, range and safe-area filtering runs before icons are drawn. Normal/magic/friendly markers retain small circles unless an explicit supported marker is available. Unknown/missing art retains a circle rather than losing the entity.

Radar Display settings: Use map icons (default true), Icon scale 50–200%. Existing per-category size controls apply (icons use 4x size with a 12px minimum before global scale); icons keep native colors. Circle/bar color preferences remain unchanged. All modules still start off. Labels, clipping and opacity are preserved. Source/scaled QImage caches are bounded (256 originals/128 scaled); no network calls or image decoding inside the recurring paint after cache warmup. Consecutive ordinary circles retain fast batching; textured markers are excluded from that path.

Validation: 212 tests passed, exit 0 (2.86s), including all 305 image decodes, exact rare/unique art, native object priority, Eater/Exarch/ore/treasure fallbacks, safe invalid keys, cached HiDPI scaling, alpha/clipping and removal of old icon pixels. Visual gallery rendered and inspected at preview-map-icons.png. Live read-only check in Celestial Nebula Hideout matched native Portal and Waypoint identifiers to their bundled art (safe-area hiding remains enabled, so this was a reader check rather than a visible hideout overlay test). No gameplay inputs sent.

Sources: https://poedb.tw/us/MinimapIcons and https://poe2db.tw/us/MinimapIcons.
Release 20261029-185434: packaged check passed (seven modules, 305 icons decoded, no errors); old owned app closed and new build launched.
