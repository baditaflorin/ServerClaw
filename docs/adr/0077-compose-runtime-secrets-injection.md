# ADR 0077: Compose Runtime Secrets Injection Via OpenBao Agent

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.83.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-23
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
3. renders them into a host `tmpfs` path under `/run/lv3-secrets/<service>/runtime.env` (format: `KEY=VALUE`)
4. re-fetches and re-renders on TTL expiry so the next controlled container recreate uses the updated values without a playbook rewrite

### Compose structure

The current implementation uses the host `/run` mount, which is already `tmpfs` on Debian. Each stack:

- keeps its agent config and AppRole material under `/opt/<service>/openbao/`
- writes the runtime env file to `/run/lv3-secrets/<service>/runtime.env`
- points the application service `env_file:` at that `/run/...` path
- removes any legacy `/opt/<service>/*.env` file after converge

This preserves RAM-only secret delivery while remaining compatible with Docker Compose, which reads `env_file` from the host filesystem rather than from another container volume.

### Agent configuration template

`roles/common/templates/openbao-agent.hcl.j2`:

```hcl
vault {
  address = "http://127.0.0.1:{{ openbao_http_port }}"
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
  source      = "/openbao-agent/runtime.env.ctmpl"
  destination = "/run/lv3-secrets/<service>/runtime.env"
  perms       = "0600"
}
```

The `role_id` and `secret_id` files are written by Ansible to `/opt/<service>/openbao/` with `0600` permissions. They are the only secret bootstrap artifacts left on disk, and they grant access only to the single `kv/data/services/<service>/runtime-env` path scoped to that stack.

### Ansible role update

The current mainline implementation uses service-specific roles plus the shared `roles/common/tasks/openbao_compose_env.yml` helper to:

- seed the service runtime payload in OpenBao
- template and deploy the `openbao-agent.hcl` configuration plus the runtime env template
- write the AppRole `role_id` and `secret_id` to `/opt/<service>/openbao/` with `0600` permissions
- remove any existing `.env` file from the compose directory
- make `make validate` fail if any `*.env` file exists inside the repository checkout

### Secret path convention

All secrets for a migrated Compose stack are stored under `kv/data/services/<service>/runtime-env` as fielded payloads used by the sidecar-rendered runtime env.

## Consequences

- No plaintext secrets remain under `/opt/<service>/` compose directories; the remaining runtime env file lives only under `/run`.
- Secret rotation in OpenBao (ADR 0065) now updates the runtime env source of truth without rewriting repo-managed files on disk.
- Services that only consume environment variables at process start still need a controlled restart to ingest changed values; the agent refreshes the host runtime env, not the process environment of an already-running container.
- Each migrated stack now has a mandatory sidecar; this adds one container per stack.
- Debugging moves into the sidecar logs and the `/run/lv3-secrets/<service>/runtime.env` render state.

## Boundaries

- This model applies to Compose-managed runtimes on `docker-runtime-lv3`. Grafana is not part of the current implementation because ADR 0011 converged it as a package-managed service on `monitoring-lv3`, not a Compose stack.
- The AppRole credentials (`role_id`, `secret_id`) are intentionally stored on disk — they are low-privilege bootstrap credentials that grant access only to a scoped policy. Their compromise allows reading secrets but not writing them or accessing other stacks.
- This ADR is implemented on current `main` for Windmill, Keycloak, Mattermost, Open WebUI, NetBox, the private platform-context API, and the mail-platform gateway.
