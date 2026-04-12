# ADR 0374: Cross-Cutting Service Manifest

- **Date**: 2026-04-06
- **Status**: Accepted
- **Implementation Status**: Implemented
- **Implemented In Repo Version**: 0.178.124
- **Implemented In Platform Version**: not yet applied
- **Implemented On**: 2026-04-12
- **Deciders**: platform team
- **Concern**: platform, dry
- **Tags**: dns, sso, certificates, nginx, dry, manifest

## Context

Adding a new externally-accessible service to the platform currently requires manual, coordinated updates across **4-6 disconnected files and roles**:

| Step | Where | What | Risk if forgotten |
|---|---|---|---|
| 1. DNS record | Service playbook (58-line DNS play) | Add Hetzner A record | Service unreachable by domain name |
| 2. Subdomain catalog | `config/subdomain-catalog.json` | Declare the FQDN | Playbook DNS play fails assertion |
| 3. Nginx reverse proxy | `api_gateway_runtime` or `nginx_edge_publication` config | Add upstream + location block | Service not reachable via HTTPS |
| 4. TLS certificate | `config/certificate-catalog.json` + cert renewal role | Add domain to cert issuance | Browser shows untrusted warning |
| 5. SSO/OIDC client | Keycloak bootstrap + service env vars | Register OAuth2 client | Users can't log in via SSO |
| 6. Hairpin NAT | Other services' `docker-compose.yml.j2` `extra_hosts` | Add internal routing | Services can't reach new service internally |

Each step is owned by a different role/file and must be done manually. There is no single document that answers: "What does service X need from the platform's cross-cutting infrastructure?"

### Observed incidents caused by this fragmentation

1. **Stale DNS entries** — services were decommissioned but DNS records left dangling because the playbook was deleted without updating `subdomain-catalog.json`.
2. **Missing Keycloak clients** — 12+ roles independently validate that a Keycloak client secret file exists. When a new SSO-enabled service is added, the Keycloak bootstrap must be updated separately.
3. **Hairpin NAT drift** — `extra_hosts` entries in compose templates are manually maintained. When the API gateway IP changed, 8 compose files needed updating; 3 were missed and broke for 2 days.
4. **Certificate renewal gaps** — a service was published on HTTPS but its domain wasn't added to the certificate catalog, resulting in a Let's Encrypt certificate that didn't cover the new domain.

### What already exists

- ADR 0373 introduces `platform_service_registry` with core service identity (image, port, host).
- ADR 0368 introduces `platform_hairpin_nat_hosts` as a centrally managed list.
- `config/subdomain-catalog.json` exists but is disconnected from the service lifecycle.
- `config/certificate-catalog.json` exists but is manually maintained.
- Keycloak client registration is scattered across individual runtime roles.

## Decision

Extend the **platform service registry** (ADR 0373) with **cross-cutting concern declarations**. Each service declares what it needs from DNS, nginx, TLS, and SSO — in one place. Dedicated roles and generators consume these declarations to converge the actual state.

### Extended registry format

In `inventory/group_vars/platform_services.yml`, each service entry gains optional cross-cutting sections:

```yaml
platform_service_registry:
  directus:
    # --- Core identity (ADR 0373) ---
    image_catalog_key: directus_runtime
    internal_port: 8055
    host_group: docker-runtime
    needs_openbao: true
    needs_postgres: true

    # --- Cross-cutting declarations (this ADR) ---
    dns:
      # Declares the Hetzner DNS A records this service needs.
      # Generator ensures these exist in subdomain-catalog.json and converges them.
      records:
        - fqdn: data.example.com
          type: A
          target_host: nginx-edge     # Resolved to IP via platform_guest_catalog
          ttl: 60

    proxy:
      # Declares the nginx reverse proxy configuration.
      # Generator produces an nginx server block for nginx_edge_publication.
      enabled: true
      upstream_port: 8055            # Port on the Docker runtime VM
      upstream_host: docker-runtime  # Resolved to IP
      public_fqdn: data.example.com
      # Optional:
      websocket: false               # Default: false. Adds Upgrade headers if true.
      max_body_size: 100m            # Default: 10m
      custom_locations: []           # Escape hatch for service-specific location blocks
      auth_proxy: true               # Default: false. Fronts with oauth2-proxy if true.

    tls:
      # Declares TLS certificate requirements.
      # Generator ensures these domains exist in certificate-catalog.json.
      domains:
        - data.example.com

    sso:
      # Declares Keycloak OIDC client requirements.
      # Generator produces a Keycloak client configuration.
      enabled: true
      client_id: directus
      redirect_uris:
        - "https://data.example.com/auth/login/keycloak/callback"
      # Optional:
      client_secret_local_file: "{{ platform_local_artifact_dir }}/keycloak/directus-client-secret.txt"
      post_logout_redirect_uris:
        - "https://data.example.com"
      default_scopes:
        - openid
        - email
        - profile

    hairpin:
      # Declares that this service needs internal name resolution entries
      # in other services' compose files (via the hairpin_hosts() macro from ADR 0368).
      publish:
        - hostname: data.example.com
          address_host: nginx-edge    # Resolved to IP via platform_guest_catalog
```

### Generator: `scripts/generate_cross_cutting_artifacts.py`

A single Python script reads the service registry and generates/validates the cross-cutting artifacts. This script integrates into the existing `make generate-platform-vars` pipeline.

**Subcommands:**

```bash
# Validate the registry cross-cutting declarations
python scripts/generate_cross_cutting_artifacts.py --check

# Generate all artifacts
python scripts/generate_cross_cutting_artifacts.py --write

# Generate only a specific concern
python scripts/generate_cross_cutting_artifacts.py --write --only dns
python scripts/generate_cross_cutting_artifacts.py --write --only proxy
python scripts/generate_cross_cutting_artifacts.py --write --only tls
python scripts/generate_cross_cutting_artifacts.py --write --only sso
python scripts/generate_cross_cutting_artifacts.py --write --only hairpin
```

**What each concern generates:**

#### DNS concern

1. **Validates** that every declared `dns.records[].fqdn` exists in `config/subdomain-catalog.json` with a matching `target` and `status: active`.
2. **In `--write` mode:** Adds missing entries to `subdomain-catalog.json` with `status: active` and the correct target IP (resolved from `target_host` via `platform_guest_catalog`).
3. **Warns** about entries in `subdomain-catalog.json` that have no corresponding service in the registry (potential stale records).

#### Proxy concern

1. **Generates** an nginx configuration snippet per service into `config/generated/nginx-edge/<service>.conf`.
2. Each snippet contains a `server` block with:
   - `server_name` from `proxy.public_fqdn`
   - `proxy_pass` to `upstream_host:upstream_port`
   - Websocket upgrade headers if `proxy.websocket: true`
   - `client_max_body_size` from `proxy.max_body_size`
   - oauth2-proxy auth_request block if `proxy.auth_proxy: true`
3. The `nginx_edge_publication` role is updated to `include` all files from `config/generated/nginx-edge/*.conf` rather than maintaining its own list.

#### TLS concern

1. **Validates** that every declared `tls.domains[]` entry exists in `config/certificate-catalog.json`.
2. **In `--write` mode:** Adds missing domains to the certificate catalog.
3. **Warns** about certificate catalog entries that have no corresponding service (potential stale certs).

#### SSO concern

1. **Generates** a Keycloak client manifest per SSO-enabled service into `config/generated/keycloak-clients/<service>.json`.
2. Each manifest contains the client configuration (client_id, redirect_uris, scopes, etc.) that the Keycloak bootstrap role consumes.
3. **Validates** that `client_secret_local_file` paths are consistent with the existing Keycloak secret storage pattern.

#### Hairpin concern

1. **Generates** `platform_hairpin_nat_hosts` (from ADR 0368) by aggregating all `hairpin.publish` entries across all services, resolving hostnames to IPs.
2. **Writes** the result into `inventory/group_vars/platform_hairpin.yml`:
   ```yaml
   # GENERATED — do not edit. Source: platform_service_registry hairpin declarations.
   # Regenerate: python scripts/generate_cross_cutting_artifacts.py --write --only hairpin
   platform_hairpin_nat_hosts:
     - hostname: data.example.com
       address: 10.10.10.92
     - hostname: agents.example.com
       address: 10.10.10.92
     # ... all published hostnames
   ```

### Validation in the pre-push gate

The `--check` mode of the generator runs in the `schema-validation` gate lane. It fails the gate if:

1. A service declares `dns.records` but the FQDN is missing from `subdomain-catalog.json`.
2. A service declares `tls.domains` but the domain is missing from `certificate-catalog.json`.
3. A service declares `sso.enabled: true` but has no `client_id` or `redirect_uris`.
4. A service declares `proxy.enabled: true` but the generated nginx config doesn't match the committed file.
5. The committed `platform_hairpin_nat_hosts` doesn't match the derived set.

This means the gate catches "forgot to regenerate after adding a service" errors before they reach production.

### Workflow for adding a new service

After this ADR, the complete workflow for adding an externally-accessible service is:

```bash
# 1. Add the service to the registry (one file, one entry)
vim inventory/group_vars/platform_services.yml
# Add: new_service: { image_catalog_key: ..., dns: ..., proxy: ..., tls: ..., sso: ... }

# 2. Regenerate all cross-cutting artifacts
python scripts/generate_cross_cutting_artifacts.py --write

# 3. Regenerate the platform manifest
uvx --python 3.12 --with pyyaml --with jsonschema --with requests --with jinja2 \
  python scripts/platform_manifest.py --write

# 4. Verify
python scripts/generate_cross_cutting_artifacts.py --check
make validate-schemas

# 5. Commit
git add inventory/group_vars/platform_services.yml \
        config/subdomain-catalog.json \
        config/certificate-catalog.json \
        config/generated/ \
        inventory/group_vars/platform_hairpin.yml
git commit -m "feat(new-service): register cross-cutting infrastructure — ADR 0374"

# 6. Create the runtime role and playbook (separate commit)
# ... standard role development ...
```

Compare this with the current workflow which requires edits to 4-6 disconnected files with no validation that they're consistent.

### What the generator script must NOT do

- **Must NOT** make live API calls (no Hetzner DNS API, no Keycloak API, no cert issuance). The generator only produces files that Ansible roles consume during `make converge-*`.
- **Must NOT** modify files outside of `config/generated/`, `config/subdomain-catalog.json`, `config/certificate-catalog.json`, and `inventory/group_vars/platform_hairpin.yml`.
- **Must NOT** import `requests` at module load time (same constraint as `agent_tool_registry.py` — breaks `--export-mcp` validation container).
- **Must** use functions from `validation_toolkit.py` (ADR 0369) for all input validation.

### Migration strategy

This ADR layers on top of ADR 0373 (service registry). It can be implemented incrementally — start with the hairpin concern (simplest, highest impact), then DNS, then TLS, then proxy, then SSO.

#### Phase 1: Hairpin (immediate win)

1. Add `hairpin.publish` entries to existing `platform_service_registry` entries.
2. Implement the hairpin generator.
3. Replace all manual `extra_hosts` in compose templates with the `hairpin_hosts()` macro from ADR 0368.

#### Phase 2: DNS

1. Add `dns.records` entries.
2. Implement the DNS validator/generator.
3. Replace the 16 duplicated DNS plays in playbooks with the shared include from ADR 0372.

#### Phase 3: TLS

1. Add `tls.domains` entries.
2. Implement the TLS validator.
3. This is primarily a validation layer — the actual cert issuance workflow doesn't change.

#### Phase 4: Proxy

1. Add `proxy` entries.
2. Implement the nginx config generator.
3. Update `nginx_edge_publication` to consume generated configs.

#### Phase 5: SSO

1. Add `sso` entries.
2. Implement the Keycloak client manifest generator.
3. Update Keycloak bootstrap to consume generated manifests.
4. Remove the 12+ duplicated Keycloak client secret validation blocks from individual runtime roles.

### What NOT to do

- Do **not** implement all 5 concerns at once. Phase them as described above.
- Do **not** remove the existing `config/subdomain-catalog.json` or `config/certificate-catalog.json`. The generator **augments** them; they remain the source of truth consumed by Ansible roles.
- Do **not** auto-apply the generated artifacts on `git push`. Generation is manual (`--write`); the gate validates that committed files match the declared state.
- Do **not** add fields to the registry "just in case." Each field must have a concrete generator that consumes it.
- Do **not** generate Ansible roles from the registry. Roles are handwritten; the registry only generates configuration data that roles consume.

## Consequences

**Positive:**
- Adding a new externally-accessible service requires editing **one file** (the registry) + running one command (the generator), instead of 4-6 disconnected files.
- Cross-cutting consistency is enforced by the gate — you cannot push a service with DNS but without a TLS certificate declaration.
- Stale artifacts are detectable: the generator warns about catalog entries with no corresponding registry service.
- The hairpin NAT problem is permanently solved — no more manually maintaining `extra_hosts` in 15 compose files.
- The registry becomes the authoritative "what does service X need?" document.

**Negative / Trade-offs:**
- Adds a generation step to the workflow. Developers must remember to run `--write` after modifying the registry. Mitigated by the gate catching drift.
- The generator is a new script to maintain. Mitigated by using `validation_toolkit.py` and following the existing catalog validator pattern.
- The registry file will grow as more concerns are declared. At ~20 lines per service × 50 services = ~1,000 lines. This is acceptable for a declarative data file.
- The proxy concern (Phase 4) is the most complex because nginx configurations have many edge cases. The `custom_locations` escape hatch handles this, but it may need iteration.

## Implementation plan

1. Add cross-cutting fields to `platform_service_registry` format (schema only, no generator)
2. Implement `scripts/generate_cross_cutting_artifacts.py` with `--check` mode for hairpin concern
3. Implement `--write` mode for hairpin concern
4. Populate `hairpin.publish` entries for all services that currently have `extra_hosts`
5. Generate `platform_hairpin_nat_hosts` and verify against current manual entries
6. Repeat steps 2-5 for DNS, TLS, proxy, SSO concerns in order

## Depends on

- ADR 0368 (Compose Macro Library) — `hairpin_hosts()` macro consumes the generated `platform_hairpin_nat_hosts`
- ADR 0369 (Validation Toolkit) — generator uses shared validation functions
- ADR 0372 (Data-Driven Playbook Composition) — shared DNS/postgres/nginx plays are replaced by generated includes
- ADR 0373 (Service Registry) — this ADR extends the registry with cross-cutting sections

## Related

- ADR 0042 (Hetzner DNS) — the DNS management this ADR centralizes
- ADR 0063 (OpenBao Integration) — the secret management patterns SSO builds on
- ADR 0359 (PostgreSQL Client Registry) — same "declare once, derive everywhere" philosophy
