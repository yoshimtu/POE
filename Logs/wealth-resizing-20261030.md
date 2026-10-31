# Inventory visibility and resizable value summaries

- Inventory price badges and net worth now require the live inventory panel to be open. Legacy `summary_closed` settings no longer force the inventory summary to remain visible.
- Inventory, personal-stash and guild-stash value boxes support bottom-right corner resizing while unlocked. Each scope's size is saved independently in `summary_sizes`, alongside existing saved positions.
- Smaller sizes use tighter text down to 9px and wrap the complete item names with quantities. Minimum height follows the content so the top-three entries, total and prices are retained. Boxes can be enlarged vertically and horizontally.
- The default vertical stack now uses the actual rendered height of each box. Locked boxes remain click-through and cannot move or resize.
- 218 tests passed. Includes visibility with stale cached items, long-name reflow, minimum size and restoration, plus existing drag/save/restore checks. A compact 210px-wide actual widget screenshot was inspected at `.reference/compact-wealth.png`.
- Visibility and resizing verified with synthetic snapshots; a live in-game close/open and drag check remains a user playtest.
