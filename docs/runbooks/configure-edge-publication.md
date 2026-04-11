# Configure Edge Publication

## Purpose

This runbook converges public `example.com` subdomain publication on the NGINX edge VM at `10.10.10.10`.

## Result

- `grafana.example.com` reverse proxies to Grafana on `10.10.10.40:3000`
- `grafana.example.com/api/health` is intentionally blocked at the edge so unauthenticated callers cannot read the Grafana version banner
- `nginx.example.com` serves the edge landing page
- `example.com/robots.txt` and `*.example.com/robots.txt` return the shared crawl policy
- `proxmox.example.com`, `docker.example.com`, and `build.example.com` serve explicit informational pages instead of the default Debian NGINX page
- the edge obtains a Let's Encrypt certificate for the published subdomains plus `example.com` and redirects HTTP to HTTPS

## Command

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server
make configure-edge-publication env=production
```

The make target now runs the ADR 0273 public-endpoint admission check before
touching `nginx-edge`. It fails fast when the subdomain catalog, generated
publication registry, shared-edge certificate domain set, and
`config/certificate-catalog.json` disagree.

## Verification

```bash
curl -I https://grafana.example.com
curl -i https://grafana.example.com/api/health
curl -I https://grafana.example.com/d/lv3-platform-overview/lv3-platform-overview
curl -I https://nginx.example.com
curl -I https://nginx.example.com/robots.txt
curl -I https://example.com/robots.txt
curl -I https://proxmox.example.com
curl -I https://docker.example.com
curl -I https://build.example.com
curl -s https://nginx.example.com | rg '<meta name="robots"'
```

Expected result:

- Grafana responds with a login redirect for dashboard URLs, not an anonymously readable dashboard
- `https://grafana.example.com/api/health` returns `404 Not Found`
- the other subdomains no longer return the default Debian NGINX page
- `robots.txt` returns `Disallow: /`
- published responses include `X-Robots-Tag: noindex, nofollow`
- the static landing page HTML includes `<meta name="robots" content="noindex, nofollow">`

## Notes

- `uvx --from pyyaml python scripts/subdomain_exposure_audit.py --validate` is
  the repo-side admission gate for public endpoint changes. Use it directly
  when validating a branch before a live replay.
- `make configure-edge-publication` regenerates the shared `build/changelog-portal/` and `build/docs-portal/` artifacts before pushing them to the edge, so a fresh worktree does not need a separate manual portal/docs build step.
- This runbook does not publish Proxmox UI itself. The `proxmox.example.com` edge page is intentionally informational because Proxmox administration remains private and Tailscale-based.
- When only the NGINX edge config needs to change and the generated portal directories are already current on the guest, rerun `playbooks/public-edge.yml` from `Check whether the public edge certificate exists` to skip the slow static-directory copy and force the config render, validation, and reload path.
