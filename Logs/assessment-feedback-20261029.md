# Assessment feedback and automation removal

Release: `releases/20261029-155257/ObsidianExile/ObsidianExile.exe`.

Removed the auto-flask module, F8 arming/button/state, game-input sender, flask charge acquisition/offsets and automation profile flags. Passive flask buff uptime and flask item pricing remain. Builds now stage only plugins with a source entry point and exclude stale bytecode, so removed modules cannot return through cached files.

Rare-assessment feedback uses Up (higher), Down (lower), Right (looks right). Shortcuts register only for a visible live assessment while PoE has focus, or an active workshop outside text controls. They unregister when unavailable, on panic and close, and can be disabled under Items & stash → Assessment. Workshop feedback buttons are also available. No game inputs are sent.

Assessment history stores the complete item, modifier/tier/roll evidence, links/sockets, displayed rating and contributions, build preference, scoring version/signature, feedback, optional note, league and area. Data is saved locally and only copied on explicit Copy selected/all. Re-voting the same item/profile/league/model updates its vote. Saving must succeed before success is shown. Feedback does not change the scoring algorithm or weights.

Validation: 192 tests passed (exit 0), including save/reload, repeated votes, note persistence, deep-copied evidence, selected exports, failed-write rollback, unknown modifiers/six links, model revision identity, active/stale/disabled assessment gating, typing controls and release staging. History and compact acknowledgement rendered and visually checked. Packaged check exited 0 with seven modules, all default-off and no errors; plugin directory contains no obsolete auto-flask module or bytecode. New packaged UI launched after normally closing the previous owned app. Live arrow-key interaction remains for the user's brief check; no test votes were placed in the user's history.

Evidence: `.reference/assessment-feedback-tests.txt`, `.reference/assessment-feedback-package.json`, `.reference/assessment-history-qa.png`, `.reference/assessment-vote-qa.png`.
