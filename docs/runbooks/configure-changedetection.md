# Configure Changedetection

## Purpose

This runbook converges ADR 0280 so operators have a private Changedetection.io
runtime for monitored upstream releases, security advisories, dependency feeds,
and external API documentation changes.

## Result

- `docker-runtime` runs the private Changedetection.io runtime from
  `/opt/changedetection`
- the private runtime listens on `10.10.10.20:5000` for host-local verification,
  API gateway access, and monitoring probes
- the shared API gateway refreshes `/v1/changedetection` on `https://api.example.com`
  for authenticated operator and automation access
- the repo-managed watch catalogue is reconciled over the live API and the
  drift-free check report is persisted at `/opt/changedetection/watch-sync-report.json`
- the controller-local API token mirror is refreshed under
  `.local/changedetection/api-token.txt`

## Commands

Syntax-check the Changedetection workflow:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server
make syntax-check-changedetection
```

Converge the private runtime and refresh the API gateway bundle:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server
make converge-changedetection
```

Refresh the generated platform vars after topology or port changes:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server
uvx --from pyyaml python scripts/generate_platform_vars.py --write
```

## Managed Artifacts

- runtime directory: `/opt/changedetection`
- runtime secret directory: `/etc/lv3/changedetection`
- compose file: `/opt/changedetection/docker-compose.yml`
- watch catalogue: `/etc/lv3/changedetection/watch-catalog.json`
- sync report: `/opt/changedetection/watch-sync-report.json`
- named volume: `changedetection-datastore`
- controller-local API token: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/changedetection/api-token.txt`

## Verification

Verify the local runtime and datastore on `docker-runtime`:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.64.0.1 \
  ops@10.10.10.20 \
  'docker compose --file /opt/changedetection/docker-compose.yml ps && docker volume inspect changedetection-datastore >/dev/null'
```

Verify the local system info and tag catalogue endpoints with the mirrored API token:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.64.0.1 \
  ops@10.10.10.20 \
  'python3 - <<'\''PY'\''
import json, urllib.request
key = open("/etc/lv3/changedetection/api-token", encoding="utf-8").read().strip()
for path in ("/api/v1/systeminfo", "/api/v1/tags"):
    req = urllib.request.Request(f"http://127.0.0.1:5000{path}", headers={"x-api-key": key})
    with urllib.request.urlopen(req, timeout=30) as response:
        payload = json.load(response)
    if path.endswith("systeminfo"):
        print(json.dumps({"watch_count": payload["watch_count"], "version": payload["version"]}, sort_keys=True))
    else:
        print(json.dumps({"tag_count": len(payload), "tag_titles": sorted(item["title"] for item in payload.values())}, sort_keys=True))
PY'
```

Verify the drift-free sync report written by the post-converge check:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.64.0.1 \
  ops@10.10.10.20 \
  'python3 -c '\''import json; payload=json.load(open("/opt/changedetection/watch-sync-report.json", encoding="utf-8")); assert payload["check_only"] is True and payload["changed"] is False; print(json.dumps(payload["summary"], sort_keys=True))'\'''
```

Verify the authenticated API gateway route proxies the private runtime:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server
LV3_TOKEN="$(cat .local/platform-context/api-token.txt)"
curl -fsS -H "Authorization: Bearer $LV3_TOKEN" https://api.example.com/v1/changedetection/
```

## Notes

- Changedetection stays private-only in this rollout. There is no public DNS record
  and no public edge publication.
- Mattermost and ntfy remain the repo-managed notification sinks for watch-group
  changes; do not hand-edit notification URLs in the UI.
- The governed API gateway route exists for authenticated operator and
  automation access, but the primary operational surface is still the private
  runtime on `docker-runtime`.
- The watch catalogue is the source of truth. UI-only watches or tag edits are
  reconciled away on the next converge.
- Treat `.local/changedetection/` as secret material and keep it outside git.
- The persisted drift-free report is the supported operational proof that the
  repo-managed watch catalogue already matches the live API state.
