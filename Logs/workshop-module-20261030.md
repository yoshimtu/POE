# Workshop module and conditional navigation

- Added the removable `plugins/workshop/plugin.py` module, with the same enable checkbox and persisted enabled state as other modules. It renders no game marks.
- Removed the workshop page's enable checkbox. Its left navigation button is visible only while the workshop module is enabled. Disabling it while viewing the page returns to Modules; direct navigation to the disabled page is also blocked.
- Refresh and panic update the navigation state. Existing `workshop_enabled` preferences migrate to the module's saved state, and the obsolete root preference is removed. Existing installations retain their previous workshop preference; fresh installations start the module disabled.
- Alt+F still captures the latest item text while the workshop is disabled; assessment resumes when enabled.
- 225 tests passed, including module checkbox/navigation behavior, return to Modules on disable, persistence after restart, old preference migration, and existing assessment/feedback flows.
