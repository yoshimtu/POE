# Waymark connections

Connections are opt-in. Enter a display name, then choose **Host**, **Host (LAN)** or **Join**. Firebase groups use an invite code by itself. LAN and external-server invitations include an address and a code. Copy and share the entire invite privately. Existing longer codes and saved sessions continue to work.

**Host** creates a group in the Waymark Firebase Realtime Database on the free Spark plan. The group remains available when the creator closes Waymark. Firebase invitations use a long, randomly generated group capability: treat the complete invite as a secret, since anyone with it can join. To create a group on an already deployed Waymark server instead, enter its HTTPS address in the optional existing-server field. **Host (LAN)** shares a local-network address on port 8765. **Join** accepts the complete invite from the host. A saved session can be reconnected from the opening screen; Firebase group invites remain stable; temporary tunnel addresses change if restarted.

The group screen includes recent chat and activity, online status, a searchable shared-items view, and buttons to share the most recently assessed item or an item copied in PoE. The personal and guild stash switches automatically publish and update the corresponding tabs **as PoE loads them**. Open a tab in game at least once for Waymark to see it. Previously shared tab snapshots can remain available when that tab is no longer loaded. Turn a switch off while connected to withdraw its previously shared tabs; disconnecting alone keeps snapshots on the server. Do not enable guild sharing unless the group is allowed to see those items.

The reader cannot independently enumerate unopened stash contents. During a new game session, tabs are synchronized as they become available to the reader. Updates and chat appear after the next polling interval. Snapshot freshness, active league, and loaded status affect availability; offline snapshots can be stale. Group members can search and view shared data, but Waymark does not transfer items in game.

## Hosting independently

A standalone server can run on another machine with Python and this project installed:

```powershell
.\.venv-runtime\Scripts\python.exe main.py --sharing-server --bind 0.0.0.0 --port 8765 --database "D:\Waymark\groups.sqlite"
```

Create the database parent directory first. For public access, put the server behind an HTTPS reverse proxy or secure tunnel and preserve the SQLite database. The server operator can read published data. Protect the database and backups; group invites and client session tokens are secrets, and clients store their session settings locally. A six-character code is shorter than previous invites, so use private sharing and the server's join rate limit; it is not a substitute for a private network or access control at the proxy.

Existing groups, hashed invitations and session tokens remain in the database across server upgrades. Firebase invitations use 32 hexadecimal characters; new self-hosted invitations use six case-sensitive alphanumeric characters. Group chat and events are stored in the same database, limited to the latest 200 events per group. The protocol uses bounded request sizes, connection counts, group storage, join attempts and 512 publications per member. The server returns only explicitly selected item fields, not process addresses or local file paths.

An external host or HTTPS reverse proxy is not installed or deployed automatically. `Host` uses the temporary tunnel unless an existing server address is supplied. Each friend needs the updated Waymark client for the redesigned group screen and chat; old clients can still use the existing group, tab and item endpoints.
