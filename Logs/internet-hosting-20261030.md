# Hosting for people outside the LAN

Added Host over Internet, Copy Internet address and Stop Internet hosting controls to Connections. Hosting starts a loopback local server and an owned Cloudflare Quick Tunnel process, producing a temporary public HTTPS address. Friends use that address with the existing private-group invite flow; they need no tunnel software. Normal local hosting remains available.

The helper is downloaded only when explicitly starting Internet hosting, from the official cloudflare/cloudflared GitHub release. Its published SHA-256 is checked before execution; mismatched downloads are rejected. It is cached outside release folders. Stopping Internet hosting or closing Waymark terminates the owned helper. The latest ready address/PID is recorded in `internet-host.json` without credentials.

Testing exposed a local DNS issue: Windows returned NXDOMAIN for a generated tunnel name while Cloudflare and Google public DNS returned valid public A records. Added a bounded app-only DNS-over-HTTPS fallback for trycloudflare.com names after a socket DNS failure. Original HTTP Host, TLS SNI, hostname checking and certificate verification are preserved; private resolved IPs are rejected. System DNS and Tailscale settings were not changed.

236 unit/integration tests passed. A real public HTTPS smoke test used isolated synthetic SQLite data, two clients, invite joining, an item upload and retrieval through the Cloudflare URL. Both temporary test tunnels were stopped and synthetic groups were discarded. This verifies public routing from this PC, not an independent second ISP.

Quick Tunnels need no account/domain, but have no uptime guarantee and change hostnames on restart. A fixed long-term address still requires a named tunnel/permanent host. Official reference: https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/
