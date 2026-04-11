# Configure Browser Runner

This runbook covers the private Playwright browser runner introduced by
[ADR 0261](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0261-playwright-browser-runners-for-serverclaw-web-action-and-extraction.md).

## Scope

The browser runner workflow converges:

- the private Playwright runtime on `docker-runtime`
- the governed operator route `/v1/browser-runner/*` through `api.example.com`
- the governed Dify tool `browser-run-session` through the existing tool-provider sync path
- controller-local verification via `scripts/browser_runner_smoke.py`

## Preconditions

- `bootstrap_ssh_private_key` is present under `.local/ssh/`
- `keycloak_agent_client_secret` is present under `.local/keycloak/`
- the shared API gateway at `api.example.com` is already healthy enough to accept a route replay
- Dify is already deployed if you intend to verify the governed tool-provider sync end to end

## Converge

Run:

```bash
make converge-browser-runner
```

The make target replays the private browser-runner runtime first and then
refreshes the API gateway runtime so the new `/v1/browser-runner/*` route is
present on the live gateway image.

## Verification

Repository and syntax checks:

```bash
make syntax-check-browser-runner
make syntax-check-api-gateway
python3 scripts/validate_service_completeness.py --service browser_runner
./scripts/validate_repo.sh data-models agent-standards
```

Direct private runtime verification through a tunnel to `docker-runtime`:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o ProxyCommand="ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -W %h:%p ops@100.64.0.1" \
  -L 18096:127.0.0.1:8096 ops@10.10.10.20

curl -fsS http://127.0.0.1:18096/healthz
uv run --with-requirements requirements/browser-runner.txt python scripts/browser_runner_smoke.py \
  --base-url http://127.0.0.1:18096
```

Operator-route verification through the API gateway:

```bash
ACCESS_TOKEN=...
curl -fsS https://api.example.com/v1/browser-runner/healthz \
  -H "Authorization: Bearer ${ACCESS_TOKEN}"
```

Governed Dify tool-provider verification:

```bash
uv run --with requests --with pyyaml python3 scripts/sync_tools_to_dify.py \
  --base-url https://agents.example.com \
  --admin-email operator@example.com \
  --admin-password-file .local/dify/admin-password.txt \
  --tools-api-key-file .local/dify/tools-api-key.txt

TOOLS_KEY=$(cat .local/dify/tools-api-key.txt)
curl -sS -X POST https://api.example.com/v1/dify-tools/browser-run-session \
  -H "Content-Type: application/json" \
  -H "X-LV3-Dify-Api-Key: ${TOOLS_KEY}" \
  -d @<(uv run --with-requirements requirements/browser-runner.txt python - <<'PY'
from browser_runner_smoke import build_smoke_payload
import json
print(json.dumps(build_smoke_payload()))
PY
)
```

## Operational Notes

- The runtime stays private-only. It is not published on the shared NGINX edge.
- Bounded session artifacts are stored under `/opt/browser-runner/data/artifacts` on `docker-runtime`.
- The governed tool handler resolves the browser runner base URL from the service capability catalog, so keep `config/service-capability-catalog.json` current when the private listener moves.
