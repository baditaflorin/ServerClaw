# Configure Edge Publication

## Purpose

This runbook converges public `lv3.org` subdomain publication on the NGINX edge VM at `10.10.10.10`.

## Result

- `grafana.lv3.org` reverse proxies to Grafana on `10.10.10.40:3000`
- `nginx.lv3.org` serves the edge landing page
- `proxmox.lv3.org`, `docker.lv3.org`, and `build.lv3.org` serve explicit informational pages instead of the default Debian NGINX page
- the edge obtains a Let's Encrypt certificate for the published subdomains and redirects HTTP to HTTPS

## Command

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/hosts.yml /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/public-edge.yml --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

## Verification

```bash
curl -I https://grafana.lv3.org
curl -I https://nginx.lv3.org
curl -I https://proxmox.lv3.org
curl -I https://docker.lv3.org
curl -I https://build.lv3.org
```

Expected result:

- Grafana responds with a Grafana-origin redirect or login page
- the other subdomains no longer return the default Debian NGINX page

## Notes

- This runbook does not publish Proxmox UI itself. The `proxmox.lv3.org` edge page is intentionally informational because Proxmox administration remains private and Tailscale-based.
