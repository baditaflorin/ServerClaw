# ADR 0086: Ansible Collection Packaging and Versioned Role Distribution

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.88.0
- Implemented In Platform Version: not applicable (repo-only)
- Implemented On: 2026-03-23
- Date: 2026-03-22

## Context

The repository currently contains 40+ Ansible roles under `roles/`. These roles have grown organically and exhibit several DRY violations:

1. **Duplicated task fragments**: preflight tasks (check OS version, assert required variables, verify connectivity) are copy-pasted across 15+ roles with minor variations
2. **Duplicated handler blocks**: `systemd daemon-reload`, `restart docker`, `restart nginx` appear in 8+ roles with identical content
3. **Inconsistent variable namespacing**: some roles use `role_name_var`, others use flat names; no enforced convention
4. **No versioned distribution**: roles are consumed only by playbooks in this same repo; there is no mechanism to share a stable role version between multiple repos (e.g., a future `proxmox-host_apps` repo) without copy-paste
5. **No collection-level tests**: individual roles have no `molecule` or equivalent; the only test is the full-stack playbook run

The Ansible Collections format solves all of these by providing:
- a standard directory structure with enforced namespacing
- a `galaxy.yml` manifest for versioning and metadata
- a packaging and distribution mechanism (`ansible-galaxy collection build`)
- a standard test surface via `molecule` per role

## Decision

We will restructure the `roles/` directory into a proper **Ansible Collection** `lv3.platform` and publish it to the internal Ansible Galaxy server (`galaxy.example.com`).

### Collection namespace and name

- **Namespace**: `lv3`
- **Collection name**: `platform`
- **Full qualified name**: `lv3.platform`
- **Version policy**: semantic versioning; minor bump for new roles, patch for role fixes, major for breaking variable changes

### New directory structure

```
collections/
  ansible_collections/
    lv3/
      platform/
        galaxy.yml          # collection metadata + version
        README.md
        roles/
          common/           # migrated from repo-root roles/common
          docker_runtime/   # migrated from repo-root roles/docker_runtime
          openbao_runtime/  # migrated from repo-root roles/openbao_runtime
          ...
        plugins/
          callback/
          filter/
        playbooks/
          site.yml
        meta/
          runtime.yml
        molecule/
```

The existing repo-root `roles/`, `filter_plugins/`, and `callback_plugins/` paths are compatibility symlinks that point into the collection.

### Shared role utilities (DRY extraction)

We will extract the following fragments into dedicated roles consumed by other roles via `dependencies`:

| Shared role | Extracted from | Purpose |
|---|---|---|
| `lv3.platform.preflight` | 15+ roles | OS assert, connectivity check, required-vars check |
| `lv3.platform.common_handlers` | 8+ roles | systemd daemon-reload, docker restart, nginx reload |
| `lv3.platform.secret_fact` | 6+ roles | Fetch a secret from OpenBao and expose as a fact |
| `lv3.platform.wait_for_healthy` | 10+ roles | Wait for HTTP health endpoint with retry/timeout |

Each consumer role declares:
```yaml
# roles/openbao_runtime/meta/main.yml
dependencies:
  - role: lv3.platform.preflight
  - role: lv3.platform.secret_fact
```

This eliminates the copy-pasted boilerplate without any runtime overhead.

### Internal Galaxy server

`galaxy.example.com` is a lightweight [Pulp](https://pulpproject.org/) instance (or `ansible-galaxy-api` minimal server) hosted on `docker-runtime`. Roles are installed from it by adding to `ansible.cfg`:

```ini
[galaxy]
server_list = internal_galaxy

[galaxy_server.internal_galaxy]
url = https://galaxy.example.com/
auth_url = https://keycloak.example.com/realms/lv3/protocol/openid-connect/token
token = <fetched from OpenBao at install time>
```

### Build and publish workflow

```bash
make collection-build       # ansible-galaxy collection build → build/collections/lv3-platform-<version>.tar.gz
make collection-publish     # push to galaxy.example.com
make collection-install     # install from the built tarball (or server when requested)
```

A Windmill workflow (`collection-publish`) runs on every merge to `main` that touches `collections/`.

### Playbook consumption

Top-level playbooks reference the collection with FQCNs:
```yaml
- name: converge docker runtime
  hosts: docker_runtime
  roles:
    - lv3.platform.docker_runtime
```

## Consequences

**Positive**
- Preflight, handler, secret-fetch, and health-wait boilerplate is written once and tested once; fixes propagate to all consumers automatically
- Collection version pinning enables a future second repo to consume `lv3.platform:1.2.0` without tracking this repo's `HEAD`
- `galaxy.yml` version history provides a clean record of when role interfaces changed
- `molecule` tests at the collection level run on the build server; no local Docker required for role development
- repo-root playbooks continue to work through collection FQCNs and compatibility symlinks, while packaged consumers can install the same collection tarball directly

**Negative / Trade-offs**
- Migration of 40+ roles to the collection structure is a multi-hour mechanical task; must be done carefully to avoid breaking existing playbook imports
- Internal Galaxy server is a new service dependency; it must be bootstrapped before collection install can work in CI
- FQCNs in playbooks are more verbose (`lv3.platform.docker_runtime` vs `docker_runtime`); editors with Ansible LS handle this gracefully

## Alternatives Considered

- **Keep flat `roles/` directory**: cannot distribute to other repos; DRY violations remain
- **Git submodules for shared roles**: fragile, hard to version, painful merge experience
- **Ansible Galaxy (public)**: roles are private; publishing to public Galaxy is inappropriate for a homelab

## Related ADRs

- ADR 0079: Playbook decomposition (collection structure reinforces the group-playbook model)
- ADR 0082: Remote build execution gateway (collection builds run on the build server)
- ADR 0083: Docker check runner (ansible image includes `molecule`)
- ADR 0087: Repository validation gate (collection lint is part of the pre-push gate)
