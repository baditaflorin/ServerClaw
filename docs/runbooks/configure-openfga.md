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
- Keycloak is already converged and can issue tokens for the repo-managed
  `serverclaw-operator-cli` and `serverclaw-runtime` clients.
- PostgreSQL and `docker-runtime-lv3` are reachable through the standard
  Proxmox jump path.

## Converge

Run:

```bash
make converge-openfga env=production
```

The converge flow:

- configures the Proxmox host Tailscale proxy for the private controller URL
- provisions the `openfga` PostgreSQL role and database
- deploys the OpenFGA runtime on `docker-runtime-lv3`
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
  --keycloak-url https://sso.lv3.org
```

Expected results:

- `http://127.0.0.1:8096/healthz` returns `200 ok` on `docker-runtime-lv3`
- `http://100.64.0.1:8014/stores` returns `200` when the repo-managed
  preshared key is presented
- Keycloak can issue:
  - a password-grant token for `serverclaw-operator-cli`
  - a client-credentials token for `serverclaw-runtime`
- the configured OpenFGA checks all return their expected boolean result

## Controller Artifacts

- `.local/openfga/database-password.txt`
- `.local/openfga/preshared-key.txt`
- `.local/openfga/serverclaw-authz-bootstrap-report.json`
- `.local/keycloak/serverclaw-operator-client-secret.txt`
- `.local/keycloak/serverclaw-runtime-client-secret.txt`

## Recovery Notes

- Re-run `make converge-openfga env=production` instead of hand-editing the
  OpenFGA store, tuples, or Keycloak clients.
- If the controller-local preshared key is lost, rotate it by deleting
  `.local/openfga/preshared-key.txt` and replaying the converge from git.
- If the authz checks fail after client recreation, re-run the OpenFGA converge
  so the latest Keycloak clients and tuple seed are replayed together.
- Re-run `make converge-api-gateway env=production` after modifying
  `config/api-gateway-catalog.json` so the routed `/v1/openfga` surface matches
  the repo-managed private service contract.
