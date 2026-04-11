# Runtime Assurance Matrix

## Purpose

Use the governed runtime-assurance matrix to answer two operator questions:

- which active service and environment bindings currently have enough evidence
  to trust their declared runtime state
- which proof dimensions are still degraded, failed, or unknown before a human
  claims the surface is healthy

## Sources Of Truth

- matrix contract: `config/runtime-assurance-matrix.json`
- schema: `docs/schema/runtime-assurance-matrix.schema.json`
- report builder: `scripts/runtime_assurance.py`
- API surface: `GET /v1/platform/runtime-assurance`
- portal surface: `https://ops.example.com` -> `Runtime Assurance Matrix`

The matrix report is derived from the repo-managed service catalog plus current
live evidence such as mirrored receipts and health data. Unknown proof stays
unknown until a governed evidence source closes the gap.

## Local Validation

Run these before a live apply:

```bash
uv run --with pyyaml --with jsonschema --with nats-py==2.11.0 python3 scripts/runtime_assurance.py --validate --print-report-json
uv run --with fastapi==0.116.1 --with httpx==0.28.1 --with itsdangerous==2.2.0 --with jinja2==3.1.5 --with python-multipart==0.0.20 --with pytest==8.4.2 pytest tests/test_runtime_assurance.py tests/test_api_gateway.py tests/test_api_gateway_runtime_role.py tests/test_interactive_ops_portal.py tests/test_runtime_assurance_scoreboard.py -q
```

## Live Apply

Replay the control-plane surfaces through the repo automation:

```bash
make converge-api-gateway
make converge-ops-portal
```

If the gateway build or portal converge fails, do not patch the guest by hand.
Fix the repo-managed role or runtime source first, then replay the same target.
If the replay fails because `docker-runtime` has exhausted `/`, recover space
with [docs/runbooks/docker-runtime-disk-pressure.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0244-main-merge-r3/docs/runbooks/docker-runtime-disk-pressure.md)
and then rerun the repo-managed converge path.

## Live Verification

From `docker-runtime`:

```bash
curl -sf http://127.0.0.1:8083/v1/platform/runtime-assurance
curl -sf http://127.0.0.1:8092/partials/runtime-assurance
curl -sf http://127.0.0.1:8092/partials/overview | grep -F "Runtime Assurance"
```

For the authenticated API proof, use a valid bearer token and verify:

- `generated_at` is present
- `summary` includes `total`, `pass`, `degraded`, `failed`, and `unknown`
- `entries` is a non-empty list when active bindings exist

From an operator browser:

- the portal root renders the `Runtime Assurance Matrix` section
- the overview still renders the runtime-assurance scoreboard
- degraded or unknown dimensions surface explicit reasons instead of silently
  appearing green

## Interpreting States

- `pass` means the required dimension has matched live evidence
- `degraded` means partial or stale evidence exists but the binding still needs
  attention
- `failed` means the live evidence contradicts the declared runtime truth
- `unknown` means the matrix cannot yet prove the dimension
- `n_a` means the dimension is not required for that service profile

Only required dimensions participate in the overall binding state.

## Recording Evidence

When the replay succeeds, record a live-apply receipt under
`receipts/live-applies/` with:

- source commit
- repo and platform version context
- target surfaces and addresses
- local validation and live verification results
- any merge-to-main follow-ups that must wait for the protected integration step
