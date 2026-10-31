# Waymark: Field Kit UI and branding

User selected concept B and the name Waymark. Implemented name across the application title, wordmark, export wrapper, pricing user-agent, project metadata and packaged executable/folder. New hand-drawn compass application/window icon, drawn navigation/cog icons and existing native game artwork for relevant module entries. No generated concept image is used as a screenshot or runtime background.

Main window: square iron/brass masthead, serif ivory headings, warm neutral controls, fine rules and corner details. Compact module ledger replaces the large two-column cards; modules are ordered Map, Routes, Monsters & objects, Encounter alerts, Items & stash, Hazards, Buff uptime. Checkboxes still toggle modules independently. Module label or cog selects an inline settings inspector. Save applies validated values and persists preferences; Cancel rebuilds from saved/current module values. All modules still start off. Search, refresh, status, F9 stop, workshop/history/stash/compatibility/preview navigation retained.

Overlays: common low-cost double brass border/corner treatment for route legend, container worth summaries, preload panel and hovered rare assessment. Warm neutral text/panel palette, serif headings, readable sans-serif body. Existing positions, click-through/drag behavior, opacity, health/rarity colors and native map icon artwork retained. No scoring, prices, offsets or routes changed in this UI pass.

Compatibility: existing settings, assessment history, market cache and box positions stay in the established LOCALAPPDATA/ObsidianExile directory. Plugin IDs/source package names remain stable. No reset or destructive migration. Full directory bundles should be kept together; new binary is Waymark.exe.

Validation: 215 tests passed, exit 0, 3.00s. Includes a new inline Save/Cancel/module-switch regression and default-off checks, alongside existing positioning, state and reader tests. Main window and radar inspector rendered offscreen; initial vertical spacing and label mnemonic issues corrected; final main and overlay views visually checked. Application ICO written and bundled. Build/package/live launch status appended below.

Previews: preview-waymark-main.png; preview-waymark-overlays.png. Concept reference: designs/ui-concepts/B-wraeclast-field-kit.png.
Release 20261029-213933/Waymark: module/305-icon package check and isolated native route-worker check both passed. Waymark.exe launched; no prior app process was running.
