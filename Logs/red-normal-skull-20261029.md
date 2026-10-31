# Red normal monster skull

Normal monsters now reuse the RareMonsterAlive artwork with the same cached hue-only recoloring used by magic monsters. Normal hue follows the existing normal-monster color preference (#dc6464 by default). Source silhouette, saturation/shading, brightness and alpha are preserved by the shared recoloring path; original files unchanged.

Default normal size 2 uses an 8px icon minimum; magic size 3 retains 12px. Rare/unique remain 20px/24px at 100% global scale. Sizes remain adjustable in radar settings; circle-only mode still works. Normal icons now render in place of their previous circles when Use map icons is enabled.

214 tests passed, exit 0, 3.30s. Extended rarity regression covers normal red tint, 8px minimum and actual rendered size below blue magic, with preserved rare/unique native colors. preview-monster-skulls.png rendered and visually checked at actual marker sizes and enlarged detail sizes.
Release 20261029-190554: packaged checks passed (305 icons, no errors); prior owned app closed and updated build launched.
