# Rare assessment: coherent affix combinations

This revision replaces generic additive scoring plus a few fixed pair bonuses with a shared build-profile model in `exile/rare_scoring.py`. It does not match item names, specific uniques/rares or this user's ring. The external patch profile and memory-reading behavior are unchanged.

General evaluates Balanced, Attack, Spell, Damage over time, Energy shield, Minion, Mana, Attribute stacking and Item find profiles. Specialized automatic candidates need at least two independent useful core affixes and an appropriate anchor. One unrelated high-tier stat cannot choose a profile. Explicit build preferences still select the requested profile; the UI distinguishes automatic best fit from a selected profile.

Modifiers contribute according to actual reference-roll magnitude, available tier information, and their role in the chosen profile. Complementary mechanisms and multiple strong T1/T2 affixes within that same combination receive bounded bonuses. Low-value filler has zero weight and cannot earn tier bonuses. Hybrid lines from a named affix share one slot for combination/tier counting, with reduced secondary contribution. Generic unnamed annotation blocks are not falsely assumed to describe one hybrid affix.

The numeric score now always represents affix quality. Six-links, five-links and socket count remain visible as separate utility notes; six-links do not raise the affix number. This supersedes the earlier utility floor described in the initial hover-assessment log.

The expanded panel shows the chosen profile, modifier contributions, combination bonus and strong-tier bonus as an additive breakdown with a ten-point cap. Its compact view ranks displayed modifiers by actual contribution, rather than raw roll percentage. Implicit/enchant context stays separate. Native advanced descriptions supply base tier/range information; the ordinary block supplies quality-adjusted displayed values. The ring's 15% base speed therefore correctly appears and is evaluated as 16% after its quality modifier. Non-numeric annotated modifiers are either supported explicitly (for example freeze immunity) or marked for review rather than silently omitted.

## Validation

143 tests pass. New tests cover seven distinct build families, unchanged scores after renaming an item, coherent versus unrelated T1 combinations, strong versus weaker tiers/rolls, zero contribution from filler, hybrid-affix independence, point reconciliation, native quality scaling, enchant classification, and separately preserving duplicate affix tiers without double-counting a combined display line. Existing item-reading, UI, prices, routes and other module checks still pass.

Captured examples under the same automatic model: Onslaught Finger is 8.8/10, Minion fit, with three complementary strong T1 minion affixes. Its raw modifier points are 6.191, synergy bonus 1.1 and coherent-tier bonus 0.5, plus the baseline 1. Brood Ward is 5.8/10, Balanced fit, with the six-link reported separately. These examples validate the model's explanation; they are not market-price calibration or safe-to-discard recommendations.

`preview-coherence-ring.png` and `preview-coherence-chest.png` were rendered, and the ring's detailed view was visually inspected. Raw comparison data is in ignored development output `.reference/rare-coherence-validation.json`.

Release `releases/20261029-080048/ObsidianExile/ObsidianExile.exe` passed its package check with eight modules defaulting off and no errors. The previous hover-assessment release was closed normally and this build opened for the user. The frozen archive includes the shared scoring and hover-assessment modules. Final in-game visual confirmation of the scoring revision remains user QA; the captured item comparisons and profile tests are complete.
