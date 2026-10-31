# Blue magic monster skull

User confirmed blue magic monsters, yellow rares, orange uniques. Magic markers now reuse the exact RareMonsterAlive source image with a cached runtime HSV hue change. The image silhouette/alpha and brightness are unchanged; saturation/shading remain from the source. Native yellow rare and orange unique images remain untinted. The original asset files are not modified.

Magic hue follows the existing magic-monster color setting. Existing category size settings and global icon scale remain available. User's current sizes 3/5/6 yield 12px/20px/24px icon bounding boxes at 100% scale, so magic skulls are smaller. Normal monster circles unchanged. Original/recolored/scaled image caches remain bounded; recoloring occurs once per color, not per paint.

213-test full suite passed with exit 0 before adding the plugin-level rarity-size regression; focused icon tests after that addition passed. Tests verify exact alpha, exact brightness maxima, blue hue, source image nonmutation via separate cached images, retained native rare/unique colors and size ordering. Preview rendered/visually inspected in preview-blue-magic-skull.png.
Release 20261029-190222: packaged check passed with all 305 icons, seven modules and no errors; prior owned app/worker closed and updated app launched.
