# Enrichment replica private ports

Add the nine exact registered ports on MCP for the primary gateway, standby gateway, and existing metrics collector. Add HTML port 3002 on own/database for the same sources. Existing grants and SSH restrictions remain intact. No public listener or debugging port is opened. Plan/apply uses the canonical ETag protected Tailscale reconciler, captures rollback, and verifies live semantic parity. No DomainScope job or API restart is involved.
