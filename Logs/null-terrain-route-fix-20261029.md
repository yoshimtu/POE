# Missing route ground lines: null tile sources

Strand diagnosis: Arena destination resolved and native A* returned a ready 2171-cell path, but snapshot terrain_heights was None with diagnostic Invalid memory read range. Inspecting the tile records found 2499 null source pointers. The height decoder attempted to read a vector header at address zero and abandoned the whole height grid. Route rendering correctly refused to project the path without decoded heights.

A null tile source now supplies the existing empty height payload representation (zero local samples plus the tile's own base height), without any null memory read. Non-null invalid sources still fail. Rotation/base validation is unchanged. This is shared terrain decoding, applying to all maps with empty source tiles, not a Strand-specific rendering fallback.

Live validation after fix: Strand has decoded heights, no height diagnostic, and the sampled player floor agrees with the decoded cell floor (0). Native search returns ready, 2171 cells and one visible projected ground segment. Other disconnected destinations are still excluded by normal region filtering. Tests: 202 passed, exit 0; regression confirms null sources do not invoke memory reads and preserve base height. User reports previous overlay flickering resolved.
Release 20261029-165856: package checks passed (seven modules, no errors); previous owned app/worker closed and new build launched.
