# Memory profiles

`steam-25113903.read-only.json` is an exact-hash independent read-only profile with bounded hideout validation. Its `validation` object lists checked and pending cases. Gameplay input sending is not part of the application. The other candidate profile is unvalidated. The app does not launch PoEHelper or load its DLLs.

Profiles are separate JSON files. Each records the exact executable SHA-256, Steam build, source commit, available capabilities, and an adapter filename relative to this folder. The adapter implements `create_adapter(profile)` and returns an object with `read(memory, window) -> exile.model.Snapshot`. `memory.read(address, count)` is bounded, read-only process access. Resolve process/module bases for the current process; absolute addresses cannot be reused across sessions. A profile must resolve all roots, decode the game's collections and components, and transform world positions into client pixels. Merely extracting field offsets from a DLL is insufficient.

Set `captured_at=time.monotonic()` at capture, `source="live"`, and only advertise capabilities actually decoded. The application only reads game data and does not send game input.

Capabilities: `terrain`, `entities`, `preloads`, `health`, `hazards`, `buffs`, `stash`. Stash snapshots include personal/guild scope and only known tabs; do not claim all-tab coverage from one open tab.

When updating, add a new profile rather than overwriting the old one. Verify on the matching game build, including area changes, logout, loading, stash screens, chat, focus loss, death and process restart. Then set `validated=true`. The UI can reload profiles without losing module settings. Adapters and feature plugins execute local Python code: install only code you trust.
