# ADR 0077: Compose Runtime Secrets Injection Via OpenBao Agent

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

Docker Compose stacks on `docker-runtime-lv3` currently source secrets from `.env` files written to disk by Ansible playbooks during provisioning. These files:

- persist on disk in plaintext (readable by any process with access to the compose directory)
- are not rotated when the secret in OpenBao is rotated (ADR 0065); the `.env` file is stale until the next playbook run
- appear in file-system snapshots and backup restores, creating a secret leakage vector
- require a full playbook re-run to update a single rotated credential
- are not audited when read by a container process

This is the most significant remaining gap between the OpenBao-based secrets model (ADR 0043, ADR 0047) and how Compose stacks actually receive credentials at runtime.

## Decision

We will replace `.env` file secret injection with OpenBao Agent sidecar injection for all Docker Compose stacks.

### Model

Each Compose stack that requires secrets will include an `openbao-agent` sidecar service. The agent:

1. authenticates to OpenBao using the VM's AppRole credential (provisioned once by Ansible)
2. fetches the required secrets from the configured OpenBao paths
3. renders them into a shared in-memory `tmpfs` volume as either:
   - a `.env` file consumed by other services via `env_file:` (format: `KEY=VALUE`)
   - or individual files consumed via `secrets:` (format: one value per file)
4. re-fetches and re-renders on TTL expiry so running containers see rotated credentials without restart

### Compose structure

```yaml
services:
  openbao-agent:
    image: openbao/openbao-agent:latest@sha256:<digest>
    volumes:
      - secrets:/run/secrets
      - ./openbao-agent.hcl:/etc/openbao-agent/agent.hcl:ro
    tmpfs:
      - /run/secrets:mode=0700,uid=1000
    restart: unless-stopped

  app:
    image: myapp:latest@sha256:<digest>
    env_file:
      - /run/secrets/.env
    depends_on:
      openbao-agent:
        condition: service_healthy
    volumes:
      - secrets:/run/secrets:ro

volumes:
  secrets:
    driver: local
    driver_opts:
      type: tmpfs
      device: tmpfs
      o: mode=0700,uid=1000
```

The `secrets` volume is `tmpfs` — it lives in RAM only and is never written to disk.

### Agent configuration template

`roles/docker_compose_stack/templates/openbao-agent.hcl.j2`:

```hcl
vault {
  address = "{{ openbao_addr }}"
}

auto_auth {
  method "approle" {
    config = {
      role_id_file_path   = "/etc/openbao/role_id"
      secret_id_file_path = "/etc/openbao/secret_id"
    }
  }
}

template {
  source      = "/etc/openbao-agent/env.tpl"
  destination = "/run/secrets/.env"
  perms       = "0600"
}
```

The `role_id` and `secret_id` files are written once by Ansible to a restricted directory; they are the only secrets that remain on disk, and they grant access only to the secrets scoped to this stack's policy.

### Ansible role update

`roles/docker_compose_stack` is updated to:
- template and deploy the `openbao-agent.hcl` configuration
- write the AppRole `role_id` and `secret_id` to `/opt/<stack>/openbao/` with `mode: 0600, owner: root`
- remove any existing `.env` file from the compose directory
- add a `make validate` check that no `*.env` files exist in compose directories on the controller (they should not be committed)

### Secret path convention

All secrets for a Compose stack are under `secret/<env>/<stack-name>/`:

- `secret/prod/grafana/admin_password`
- `secret/prod/windmill/database_url`
- `secret/staging/grafana/admin_password`

The environment prefix (`prod/` vs `staging/`) aligns with ADR 0072 environment topology.

## Consequences

- No plaintext secrets on disk within compose directories; the attack surface for secret theft via file-system access is eliminated.
- Secret rotation in OpenBao (ADR 0065) is reflected in running containers within one TTL cycle (default: 5 minutes) without a playbook re-run.
- The `openbao-agent` sidecar must be healthy before the application container starts; failed secret fetches block the stack from starting rather than starting with stale or missing credentials.
- Any Compose stack that needs secrets now has a mandatory sidecar; this adds one container per stack.
- Debugging becomes slightly more complex: secret fetch errors appear in the agent sidecar logs, not in the application logs.

## Boundaries

- This model applies to Compose stacks on `docker-runtime-lv3`. Secrets for Ansible-managed services that do not run as containers continue to be injected by Ansible at apply time using the OpenBao lookup plugin (ADR 0043).
- The AppRole credentials (`role_id`, `secret_id`) are intentionally stored on disk — they are low-privilege bootstrap credentials that grant access only to a scoped policy. Their compromise allows reading secrets but not writing them or accessing other stacks.
- Container-to-container secret sharing within the same Compose network (e.g. passing a database password between two containers) is handled by the shared `tmpfs` volume, not by environment variable inheritance.
