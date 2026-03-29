# Configure Edge Publication

## Purpose

This runbook converges public `lv3.org` subdomain publication on the NGINX edge VM at `10.10.10.10`.

## Result

- `grafana.lv3.org` reverse proxies to Grafana on `10.10.10.40:3000`
- `grafana.lv3.org/api/health` is intentionally blocked at the edge so unauthenticated callers cannot read the Grafana version banner
- `nginx.lv3.org` serves the edge landing page
- `lv3.org/robots.txt` and `*.lv3.org/robots.txt` return the shared crawl policy
- `proxmox.lv3.org`, `docker.lv3.org`, and `build.lv3.org` serve explicit informational pages instead of the default Debian NGINX page
- the edge obtains a Let's Encrypt certificate for the published subdomains plus `lv3.org` and redirects HTTP to HTTPS

## Command

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make configure-edge-publication env=production
```

## Verification

```bash
curl -I https://grafana.lv3.org
curl -i https://grafana.lv3.org/api/health
curl -I https://grafana.lv3.org/d/lv3-platform-overview/lv3-platform-overview
curl -I https://nginx.lv3.org
curl -I https://nginx.lv3.org/robots.txt
curl -I https://lv3.org/robots.txt
curl -I https://proxmox.lv3.org
curl -I https://docker.lv3.org
curl -I https://build.lv3.org
curl -s https://nginx.lv3.org | rg '<meta name="robots"'
```

Expected result:

- Grafana responds with a login redirect for dashboard URLs, not an anonymously readable dashboard
- `https://grafana.lv3.org/api/health` returns `404 Not Found`
- the other subdomains no longer return the default Debian NGINX page
- `robots.txt` returns `Disallow: /`
- published responses include `X-Robots-Tag: noindex, nofollow`
- the static landing page HTML includes `<meta name="robots" content="noindex, nofollow">`

## Notes

- `make configure-edge-publication` regenerates the shared `build/changelog-portal/` and `build/docs-portal/` artifacts before pushing them to the edge, so a fresh worktree does not need a separate manual portal/docs build step.
- This runbook does not publish Proxmox UI itself. The `proxmox.lv3.org` edge page is intentionally informational because Proxmox administration remains private and Tailscale-based.
- When only the NGINX edge config needs to change and the generated portal directories are already current on the guest, rerun `playbooks/public-edge.yml` from `Check whether the public edge certificate exists` to skip the slow static-directory copy and force the config render, validation, and reload path.
