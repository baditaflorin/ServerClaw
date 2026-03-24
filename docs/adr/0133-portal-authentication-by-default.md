# ADR 0133: Portal Authentication by Default

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

The platform currently publishes or plans to publish several informational portals as subdomains:

- `changelog.lv3.org` (ADR 0081) — deployment history, actor names, workflow IDs, timestamps
- `docs.lv3.org` (ADR 0094) — ADR index, service catalog, API reference, runbook listing
- `grafana.lv3.org` (ADR 0011) — metrics dashboards with internal service names, topology, resource utilisation

All three are either currently public or planned to be public without authentication. This presents a significant information disclosure risk:

**`changelog.lv3.org`** would expose: the platform version history, names of workflows executed, actor identities (operator usernames, agent IDs), timestamps and frequency of deployments, affected service names, and deployment parameters. An attacker can use this to understand the platform's change cadence, identify dormant services, and time attacks around known deployment events.

**`docs.lv3.org`** would expose: all ADR content including internal IP ranges referenced in decision text, service architecture, dependency graph structure, known security decisions and their rationale, runbook steps including command syntax, and the full service capability catalog.

**`grafana.lv3.org`** with anonymous access exposes: service health timelines, resource utilisation patterns, internal service names as Prometheus label values, and metric names that reveal which software stack is running.

The pattern of "make it public because it's read-only" conflates read-only with non-sensitive. Infrastructure documentation, deployment history, and metrics are not public information even if they cannot directly trigger a change.

The correct default is: every portal requires authentication unless there is a specific, documented reason it must be public.

## Decision

We will enforce **authentication by default on all platform portals** using Keycloak OIDC (ADR 0056) via the OAuth2-proxy sidecar already integrated into the nginx edge (ADR 0021).

### Authentication requirement classification

Every subdomain entry in `config/subdomain-catalog.json` must declare an `auth_requirement` field:

```json
{
  "subdomain": "changelog",
  "auth_requirement": "keycloak_oidc",     // All access requires valid Keycloak session
  "audience": "operators",                  // Who is the intended audience
  "justification": null
}
```

| `auth_requirement` value | Meaning | Approval required |
|---|---|---|
| `keycloak_oidc` | All access requires a valid Keycloak OIDC session | None (default) |
| `keycloak_oidc_readonly` | OIDC required; any authenticated operator can read | None |
| `public_intentional` | No auth; intentionally public | ADR or explicit maintainer sign-off |
| `public_informational` | Static page; no sensitive content | Maintainer sign-off |

Any new subdomain without an `auth_requirement` field fails the repository validation pipeline (ADR 0031). Any subdomain with `public_intentional` requires either a linked ADR number or an explicit `justification` string. A validation script (`scripts/validate_portal_auth.py`) checks this on every push.

### Immediate changes

Three portals that are public or planned-public must be reclassified:

**`changelog.lv3.org`**: Change from `public` to `keycloak_oidc`. The changelog portal is for operators to review deployment history. No external user needs access. The nginx vhost must add `auth_request /oauth2/auth` before serving any content.

**`docs.lv3.org`**: Change from `public` to `keycloak_oidc_readonly`. The developer portal documents internal architecture. Even if individual ADR files are committed to a public repository, the rendered portal with cross-linked service catalogs, runbooks, and topology maps is an aggregate that exceeds the sensitivity of any individual document.

**`grafana.lv3.org`**: Remove anonymous viewer access. Retain Keycloak OIDC for authenticated operators. Any dashboard panels that were designed for public display (e.g., a public status page) must be migrated to `status.lv3.org` instead.

### nginx vhost pattern for authenticated portals

```nginx
# Added to every authenticated portal vhost
location /oauth2/ {
    proxy_pass       http://oauth2-proxy:4180;
    proxy_set_header Host                    $host;
    proxy_set_header X-Real-IP               $remote_addr;
    proxy_set_header X-Scheme                $scheme;
    proxy_set_header X-Auth-Request-Redirect $scheme://$host$request_uri;
}

location = /oauth2/auth {
    proxy_pass       http://oauth2-proxy:4180;
    proxy_set_header Host             $host;
    proxy_set_header X-Real-IP        $remote_addr;
    proxy_set_header X-Forwarded-URI  $request_uri;
    proxy_set_header Content-Length   "";
    proxy_pass_request_body           off;
}

location / {
    auth_request /oauth2/auth;
    error_page 401 = /oauth2/sign_in;

    auth_request_set $user   $upstream_http_x_auth_request_user;
    auth_request_set $email  $upstream_http_x_auth_request_email;
    proxy_set_header X-User  $user;
    proxy_set_header X-Email $email;

    proxy_pass http://backend;
}
```

This pattern is already used for `ops.lv3.org` (ADR 0093); this ADR extends it to all authenticated portals.

### Break-glass anonymous access

None. Operators who lose their Keycloak session can recover access via the break-glass procedure (ADR 0051) which restores their Keycloak account. There is no anonymous fallback for portal access.

## Consequences

**Positive**

- An external attacker cannot enumerate the platform's deployment history, architecture, internal service names, or resource utilisation without first obtaining valid operator credentials.
- The authentication model is uniform: every portal uses Keycloak OIDC. There is no patchwork of different auth mechanisms to reason about.
- Removing Grafana anonymous access reduces the information available to an attacker who is fingerprinting the stack via public metric labels.

**Negative / Trade-offs**

- Operators sharing a dashboard link externally (e.g., showing a Grafana panel to a colleague) will now need to share authenticated links or screenshots. This is minor friction but is the correct trade-off.
- `docs.lv3.org` can no longer be used as a public reference for colleagues or community members who want to understand the platform setup without creating a Keycloak account. If sharing docs publicly becomes a genuine need, a curated public subset (with sensitive content stripped) should be defined in a future ADR.

## Boundaries

- This ADR governs portal authentication. It does not govern API authentication; that is handled by the API gateway (ADR 0092) and bearer token model.
- `status.lv3.org` and `uptime.lv3.org` remain public; they contain only up/down status information and do not expose internal architecture details.
- `sso.lv3.org` (Keycloak) must remain public so operators can authenticate.

## Related ADRs

- ADR 0011: Grafana dashboards (anonymous access removed)
- ADR 0021: nginx edge publication (auth_request pattern)
- ADR 0049: Private-first API publication (extends the model to portals)
- ADR 0056: Keycloak SSO (OIDC provider)
- ADR 0076: Subdomain governance (auth_requirement field added)
- ADR 0081: Deployment changelog portal (reclassified to keycloak_oidc)
- ADR 0092: Unified platform API gateway (API auth unaffected)
- ADR 0093: Interactive ops portal (existing pattern for auth; extended here)
- ADR 0094: Developer portal (reclassified to keycloak_oidc_readonly)
- ADR 0134: Changelog portal content redaction (companion ADR)
- ADR 0135: Developer portal sensitivity classification (companion ADR)
- ADR 0139: Subdomain exposure audit (validates auth_requirement fields)
