# ADR 0350: Nginx Fragment-Based Atomic Configuration

- Status: Accepted
- Implementation Status: Not Implemented
- Date: 2026-04-05
- Tags: nginx, atomicity, infrastructure, agent-coordination, include-dirs

## Context

Multiple agents may need to modify nginx configuration simultaneously:
- An apply agent adding a new upstream and `server` block for a new service.
- A cert renewal agent updating `ssl_certificate` paths.
- An OIDC config agent modifying `auth_request` directives.
- A guest-access agent writing rate-limit rules.

The current pattern writes directly to per-service nginx config files inside
a service role and then reloads nginx. Two agents targeting different services
but living on the same reverse-proxy VM can race on the reload gate, leaving
nginx with one service's config applied and another's partially written.

Additionally, there is no canonical record of "which ADR / which workstream
added this nginx rule". Config files accumulate directives with no provenance.

nginx supports `include` directives natively. This ADR formalises an
**include-directory pattern** where each service writes exactly one named
fragment file, and a coordinator role applies and reloads atomically.

## Decision

### 1. Directory structure on the nginx VM

```
/etc/nginx/
├── nginx.conf                      # managed by nginx_runtime role only
├── conf.d/
│   └── platform-includes.conf      # single include glob: include /etc/nginx/fragments.d/*.conf;
└── fragments.d/                    # one file per service; agents write here
    ├── 0022-keycloak.conf          # prefix = ADR number that authorized the rule
    ├── 0031-gitea.conf
    ├── 0099-minio.conf
    └── ...
```

### 2. Fragment file naming convention

```
<adr_number>-<service_name>.conf
```

- `adr_number`: The ADR that first authorized exposing this service via nginx.
- `service_name`: The canonical service name from `service.llm.yaml` (ADR 0348).

Fragment files are owned by the service role that deploys the service. They are
rendered from a Jinja2 template `templates/nginx-fragment.conf.j2` inside
the service role.

Each fragment must include a provenance header:

```nginx
# Fragment managed by: roles/keycloak_runtime
# ADR: 0022 — Keycloak as platform IdP
# Workstream: {{ workstream_id }}
# Last applied: {{ ansible_date_time.iso8601 }}
# DO NOT EDIT by hand — regenerated on each apply

upstream keycloak {
    server 10.10.10.104:8080;
    keepalive 32;
}

server {
    listen 443 ssl;
    server_name auth.{{ platform_domain }};
    ...
}
```

### 3. Write-then-validate-then-reload protocol

Agents must follow this sequence when updating a fragment:

1. **Acquire** `file:vm:<vmid>:nginx` exclusive lock (ADR 0347).
2. **Render** the new fragment to a temporary file `fragments.d/.<adr>-<service>.conf.tmp`.
3. **Validate** with `nginx -t -c /etc/nginx/nginx.conf` (tests the whole config
   with the tmp file staged as the real file via symlink swap).
4. **Atomic rename** `mv .tmp → <adr>-<service>.conf`.
5. **Reload** via `nginx_reload_gated.yml` (ADR 0347).
6. **Release** lock.

If step 3 fails, the `.tmp` file is deleted, the lock is released, and the
agent exits 1 with structured error JSON. The existing fragment is untouched.

### 4. Fragment inventory

`scripts/nginx_fragment_inventory.py` (new):

```
nginx_fragment_inventory.py list --vmid <id>           # list all fragments + metadata
nginx_fragment_inventory.py validate --vmid <id>       # dry-run nginx -t
nginx_fragment_inventory.py diff --vmid <id> --service <name>  # show pending vs applied
nginx_fragment_inventory.py orphans --vmid <id>        # fragments with no live service
```

Exits per ADR 0343 contract.

### 5. Orphan detection

A fragment is an orphan if its `service_name` has no corresponding running
container (`docker ps --filter name=<service>`). The `nginx_fragment_inventory.py
orphans` command is added to the daily platform health check playbook. Orphan
fragments are alerted via ntfy (ADR 0095) but not auto-removed — removal
requires an explicit operator action or a `--prune` flag.

### 6. Multi-VM nginx

For platforms with multiple nginx VMs (e.g., public-edge vs. internal reverse
proxy), the directory structure and protocol are identical; the `vmid` in the
domain key differentiates them. A fragment must declare which nginx VM it
targets in its role defaults:

```yaml
# roles/keycloak_runtime/defaults/main.yml
nginx_vmid: 101        # target nginx VM for this service's fragment
```

## Places That Need to Change

### `roles/nginx_runtime/` (new or existing)

Add tasks to create `/etc/nginx/fragments.d/` and write
`conf.d/platform-includes.conf`. Ensure `nginx.conf` does not contain inline
`server` or `upstream` blocks for platform services.

### `roles/*/templates/nginx-fragment.conf.j2` (new per role)

Each service role that currently writes an nginx config inline must extract
that config into a `nginx-fragment.conf.j2` template and write it to
`/etc/nginx/fragments.d/<adr>-<service>.conf` using the write-validate-reload
protocol.

### `roles/*/tasks/main.yml` — all roles exposing services via nginx

Replace direct nginx-config-writing tasks with fragment-write tasks that
follow the protocol. Include `file_domain_lock_acquire.yml` before writing.

### `scripts/nginx_fragment_inventory.py` (new)

Layer 2 tool per ADR 0345 (service-aware). Implements `list`, `validate`,
`diff`, `orphans` subcommands.

### `playbooks/tasks/preflight.yml`

Add `nginx_fragment_inventory.py validate` as a pre-flight check for any
playbook that touches nginx-exposed services.

### `docs/runbooks/nginx-fragment-config.md` (new)

Operator runbook: how to add a fragment, validate, force-reload, inspect
orphans, and roll back a bad fragment.

## Consequences

### Positive

- Concurrent agents can each write their own named fragment without conflict —
  races are limited to the reload gate, which is serialised by the lock.
- Every nginx rule has a provenance header; grepping for an ADR number in
  `fragments.d/` shows all rules that ADR introduced.
- `nginx -t` validates the full config before any reload — bad configs cannot
  be activated.
- Fragment files are idempotent: re-running a role renders the same content
  and triggers a no-op reload if the file is unchanged.

### Negative / Trade-offs

- Migrating all existing role-specific nginx configs to fragment format is a
  significant one-time effort.
- Fragment ordering within `fragments.d/` is lexicographic by filename.
  Services that need to be matched before others must have their ADR prefix
  chosen carefully or use a numeric override prefix.
- The orphan problem: removing a service does not auto-clean its fragment.
  Operators must run `nginx_fragment_inventory.py --prune` or delete manually.

## Related ADRs

- ADR 0085: IaC Boundary
- ADR 0165: Playbook and Role Metadata Standard
- ADR 0329: Shared Docker Runtime Bridge Chain Checks Must Fail-Safe
- ADR 0343: Operator Tool Interface Contract
- ADR 0347: Agent File-Domain Locking for Atomic Infrastructure Mutations
- ADR 0348: Per-Service LLM Context File
- ADR 0349: Agent Capability Manifest and Peer Discovery
