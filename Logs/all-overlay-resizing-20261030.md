# Free resizing with fixed fonts

- Value summaries now retain their configured font size at every box size. Removed automatic shrinking and the minimum content height. Interactive minimum is 60 × 32 logical pixels so the resize handle remains accessible. Small boxes may clip or overlap content as requested.
- Routes now supports the same bottom-right resize interaction, with saved `legend_size` and its existing position/lock settings.
- Encounter alerts now have an independent floating panel; buff uptime is also a movable/resizable floating box. Their `overlay_size` and `overlay_position` save per plugin. Lock switches make the panels click-through and prevent movement and resizing. Labels, evidence changes and buff duration updates still repaint normally.
- The pinned Alt+F assessment has a bottom-right size grip and saves its expanded size. The small hover-following assessment remains click-through; open Alt+F to interact with its window.
- World/map anchored terrain, routes, monster markers, health bars and item badges retain their game alignment; this change applies to informational overlay boxes.
- 219 tests passed, including tiny sizes, fixed fonts, restore, inventory-close visibility and existing mouse/keyboard interactions. In-game resize and focus behavior still needs normal user playtesting.
