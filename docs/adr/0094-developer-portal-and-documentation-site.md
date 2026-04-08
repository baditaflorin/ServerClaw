# ADR 0094: Developer Portal and Service Documentation Site

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.97.0
- Implemented In Platform Version: 0.105.0
- Implemented On: 2026-03-23
- Date: 2026-03-23

## Context

The platform is thoroughly documented in ADRs (91 decisions) but that documentation is not operator-friendly. An operator who wants to know "what is the base URL for NetBox's API?", "which Keycloak realm does Windmill use?", or "how do I add a new service to the platform?" must:

1. Find and read the relevant ADR (which requires knowing which ADR covers the topic)
2. Cross-reference `config/service-capability-catalog.json` for live service details
3. Check `docs/assistant-operator-guide.md` for operational procedures
4. Look at `inventory/group_vars/` for the actual hostnames and ports

This friction is acceptable when there is one operator (the original builder). It becomes a blocker the moment a second person needs to use or contribute to the platform, and it prevents the platform being treated as a product with a defined interface.

The gap is a **single published reference** that answers the questions operators and integrators actually ask:

- What services exist and how do I reach them?
- How do I authenticate to each service?
- What is the API surface of the platform gateway?
- How do I add a new service, runbook, or alert?
- Where are the runbooks for common operations?

The platform already generates JSON catalogs (`config/service-capability-catalog.json`, `config/api-gateway-catalog.json`, `config/subdomain-catalog.json`) and has a rich ADR corpus. The documentation site should be generated from these canonical sources, not written separately.

## Decision

We will generate a **static documentation site** using MkDocs with the Material theme, auto-populated from the canonical platform data sources, and published at `docs.lv3.org` via the nginx edge.

### Site structure

```
docs.lv3.org/
├── index.md                    # Platform overview and quick-start
├── services/                   # Auto-generated from service-capability-catalog.json
│   ├── index.md                # Service directory
│   ├── grafana.md
│   ├── keycloak.md
│   └── ...
├── api/                        # Auto-generated from api-gateway-catalog.json
│   ├── index.md                # API gateway overview
│   └── openapi.md              # Rendered OpenAPI spec (Swagger UI embed)
├── runbooks/                   # Operator runbooks (hand-written, linked to Windmill)
│   ├── deploy-a-service.md
│   ├── rotate-certificates.md
│   ├── add-a-new-service.md
│   └── break-glass-recovery.md
├── architecture/               # ADR index and rendered ADRs
│   ├── index.md
│   └── decisions/              # Rendered from docs/adr/
├── reference/                  # Generated reference tables
│   ├── ports.md                # All service ports
│   ├── subdomains.md           # All published subdomains
│   ├── identities.md           # Identity classes and roles
│   └── secrets.md              # Secret names (not values) from secret-catalog.json
└── changelog.md                # Rendered from changelog.md
```

### Generation pipeline

A `scripts/generate_docs_site.py` script populates the generated sections before each MkDocs build:

```python
# Generates docs/site-generated/services/<service>.md for each entry
# in config/service-capability-catalog.json
def generate_service_pages(catalog: dict) -> None:
    for service in catalog["services"]:
        render_template("service_page.md.j2", service, output_dir="docs/site-generated/services")

# Generates docs/site-generated/reference/ports.md
def generate_port_reference(catalog: dict) -> None:
    rows = [(s["id"], s.get("port"), s.get("internal_url"), s.get("public_url"))
            for s in catalog["services"]]
    render_template("port_reference.md.j2", {"rows": rows}, output_path="docs/site-generated/reference/ports.md")
```

Each service page template includes:

```markdown
# {{ service.name }}

**Status**: {{ service.status }}
**Published URL**: `{{ service.public_url }}`
**Internal URL**: `{{ service.internal_url }}`
**VM**: {{ service.vm }}
**Health probe**: `{{ service.health_probe.endpoint }}`

## Authentication

{{ service.auth_model }}

## API

{% if service.api_docs_url %}
API reference: `{{ service.api_docs_url }}`
{% endif %}

## Related ADR

ADR {{ service.adr }} -> ../architecture/decisions/{{ service.adr_slug }}.md
```

### OpenAPI rendering

The API reference section embeds the live OpenAPI schema from the platform gateway (ADR 0092) at `/v1/openapi.json`. The static build fetches the schema at build time and renders it with the `mkdocs-swagger-ui-tag` plugin, producing a browsable, interactive API reference without requiring a live backend.

### Build and publish

The `make docs` target:
1. Runs `scripts/generate_docs_site.py` to populate generated pages
2. Runs `mkdocs build --strict` to produce the static site in `site/`
3. Rsync the output to `nginx-lv3` under `/srv/docs/`

The site is rebuilt and published on every merge to `main` as part of the Windmill post-merge workflow.

### MkDocs configuration

```yaml
# mkdocs.yml
site_name: lv3 Platform Docs
site_url: https://docs.lv3.org
theme:
  name: material
  features:
    - navigation.tabs
    - navigation.instant
    - content.code.copy
plugins:
  - search
  - swagger-ui-tag
nav:
  - Home: index.md
  - Services: site-generated/services/
  - API Reference: api/
  - Runbooks: runbooks/
  - Architecture: architecture/
  - Reference: site-generated/reference/
  - Changelog: changelog.md
```

### Access model

This original public-readability decision was superseded by ADR 0133 in repo version `0.122.0` and platform version `0.114.7`. `docs.lv3.org` now requires a Keycloak-backed operator session even though the site remains read-only after login.

## Consequences

**Positive**
- Every service, port, subdomain, secret name, and identity role is discoverable in one place — no more cross-referencing multiple JSON files and ADRs
- The site is generated from canonical sources so it cannot drift from the actual platform state (docs and config are the same files)
- ADRs are browsable as a structured documentation resource rather than raw Markdown files in a git repo
- Publicly accessible — shareable links work for anyone without an SSO session
- The Swagger UI embed provides a tryable API reference that agents can also use to discover the gateway API

**Negative / Trade-offs**
- The generated site is a point-in-time snapshot rebuilt on every merge; real-time data (current service health, live port assignments) is not reflected in the static site — the ops portal (ADR 0093) handles live status
- MkDocs + Material adds a Python build dependency and ~40 MB of packages; this is added to `requirements/docs.txt`, not the main requirements
- Writing and maintaining runbooks is manual work; the generation pipeline handles structure, but content quality depends on the operator

## Alternatives Considered

- **Docusaurus (React/MDX)**: richer ecosystem but introduces Node.js toolchain; inconsistent with the Python-native platform
- **Just improve the ADR structure**: ADRs are decision records, not how-to guides; they answer "why" not "how"; operators need both
- **GitBook or Notion**: external hosted services; documentation becomes dependent on a third-party SaaS that may be unavailable or change pricing

## Related ADRs

- ADR 0015: DNS and subdomain model (`docs.lv3.org` is a new subdomain)
- ADR 0021: Public subdomain publication (docs site is served via the nginx edge)
- ADR 0033: Declarative service topology catalog (source for generated service pages)
- ADR 0074: Ops portal (the live/interactive complement to the static docs site)
- ADR 0076: Subdomain governance (`docs.lv3.org` registration)
- ADR 0081: Platform changelog (changelog.md is rendered in the docs site)
- ADR 0092: Unified platform API gateway (OpenAPI schema source for API reference)
