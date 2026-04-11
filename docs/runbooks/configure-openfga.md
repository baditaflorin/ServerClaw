# Configure OpenFGA

## Purpose

Operate the private OpenFGA runtime that implements ADR 0262's delegated
ServerClaw authorization model and keep its Keycloak-backed bootstrap state
replayable from the repository.

## Repo Sources Of Truth

- `playbooks/openfga.yml`
- `playbooks/services/openfga.yml`
- `roles/openfga_postgres`
- `roles/openfga_runtime`
- `scripts/serverclaw_authz.py`
- `config/serverclaw-authz/bootstrap.json`
- `config/serverclaw-authz/model.json`

## Preconditions

- OpenBao is already converged and the controller has
  `.local/openbao/init.json`.
- Keycloak is already converged, the named operator account exists for the
  stable `principal:keycloak-user__florin.badita` reference, and the
  `serverclaw-runtime` client can issue client-credentials tokens.
- PostgreSQL and `runtime-control` are reachable through the standard
  Proxmox jump path.

## Converge

Run:

```bash
make converge-openfga env=production
```

The converge flow:

- configures the Proxmox host Tailscale proxy for the private controller URL
- provisions the `openfga` PostgreSQL role and database
- deploys the OpenFGA runtime on `runtime-control`
- keeps the guest-reachable runtime contract on `http://10.10.10.92:8098` for
  SLO probes, k6 smoke/load validation, and other guest-network callers
- writes the runtime datastore URI and preshared API key through the OpenBao
  compose env helper
- bootstraps the `serverclaw-authz` store, authorization model, tuples, and
  live checks from the controller
- follow with `make converge-api-gateway env=production` after changing
  `config/api-gateway-catalog.json` so the shared `/v1/openfga` route stays
  aligned with the private runtime contract

## Verify

Run:

```bash
make syntax-check-openfga
python3 scripts/serverclaw_authz.py verify \
  --config config/serverclaw-authz/bootstrap.json \
  --openfga-url http://100.64.0.1:8014 \
  --openfga-preshared-key-file .local/openfga/preshared-key.txt \
  --keycloak-url https://sso.example.com
```

Expected results:

- `http://127.0.0.1:8098/healthz` returns `200 ok` on `runtime-control`
- `http://10.10.10.92:8098/healthz` stays reachable from the private guest
  network and is the canonical probe target for SLO and k6 validation
- `http://100.64.0.1:8014/stores` returns `200` when the repo-managed
  preshared key is presented
- the controller-side bootstrap and verify steps use the public Keycloak URL at
  `https://sso.example.com` because the control machine does not have direct
  routing to the private `runtime-control` listener
- the bootstrap report records the declared Keycloak operator principal and a
  live client-credentials token for `serverclaw-runtime`
- the configured OpenFGA checks all return their expected boolean result

## Controller Artifacts

- `.local/openfga/database-password.txt`
- `.local/openfga/preshared-key.txt`
- `.local/openfga/serverclaw-authz-bootstrap-report.json`
- `.local/keycloak/serverclaw-runtime-client-secret.txt`

## Recovery Notes

- Re-run `make converge-openfga env=production` instead of hand-editing the
  OpenFGA store, tuples, or the runtime Keycloak client.
- Keep the OpenFGA runtime on `8098`; `8096` is already occupied by the
  separate `browser-runner` stack on `runtime-control`. Treat
  `http://10.10.10.92:8098` as the canonical guest-network runtime URL, while
  the controller-private OpenFGA endpoint remains
  `http://100.64.0.1:8014` for controller-local bootstrap and bearer-key
  verification.
- If the controller-local preshared key is lost, rotate it by deleting
  `.local/openfga/preshared-key.txt` and replaying the converge from git.
- If the authz checks fail after runtime-client recreation, re-run the OpenFGA
  converge so the latest Keycloak runtime client and tuple seed are replayed
  together.
- During shared `runtime-control` converges, verify
  `http://10.10.10.92:8098/healthz` from the build host before re-running k6
  smoke/load probes; brief container restart churn can present as transient
  connection refusals without indicating repository drift.
- Re-run `make converge-api-gateway env=production` after modifying
  `config/api-gateway-catalog.json` so the routed `/v1/openfga` surface matches
  the repo-managed private service contract.
