# Self-hosted private groups

Implemented Connections with create/join invite groups, reconnect/disconnect/leave, member presence, explicit loaded personal/guild tab sharing, optional shared-tab updates, item sharing from Alt+F or a copied tooltip, shared-data search, detail browsing and owned withdrawal. Group membership and shares are scoped by authenticated sessions. Leaving deletes the member's publications; disconnected/offline publications retain upload timestamps.

The server is available inside the UI or through `main.py --sharing-server`. SQLite stores groups and snapshots; invite/session secrets are hashed. Protocol v1 uses bounded HTTP/JSON payloads and connections, group/member/publication limits and join throttling. Clients sanitize item fields and reject redirects. Networking uses a separate worker from the game reader; game input and trade actions are never sent.

Self-hosted private groups were explicitly selected by the user. Built-in hosting starts only when clicked, listens on port 8765 and displays LAN addresses. Remote access needs a reachable host/VPN and HTTPS termination when appropriate; no public service, router or firewall configuration was deployed. Setup and limits are documented in `MULTIPLAYER.md`, also included in the Windows package.

231 full-suite tests passed. Four sharing tests passed again after the final connection-state changes. Tests include real loopback HTTP requests, two desktop connection panels, private-group isolation, ownership, data sanitization, empty-tab replacement, invalid credentials/payloads, leave/revocation and reopening a persisted server database. Actual Connections widgets were inspected at `.reference/waymark-connections.png`. A separate packaged-server smoke check exercises two authenticated clients and two publications.

Remaining user playtest: connect a second physical PC to the host's displayed LAN address, join with the invite, and verify a real loaded stash tab/item share. Internet deployment is not claimed as tested.
