# ADR 0341: Open WebUI Keycloak OIDC With Break-Glass Fallback

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.178.3
- Implemented In Platform Version: 0.130.98
- Implemented On: 2026-04-03
- Date: 2026-04-03
- Tags: open-webui, keycloak, oidc, operator-auth, break-glass

## Context

ADR 0060 introduced Open WebUI as the private operator and agent workbench.
The runtime already includes most of the technical OIDC plumbing:

- the role can render OIDC environment variables
- the runtime already knows the callback path
- the repo already runs Keycloak as the shared operator identity plane

But the deployed Open WebUI contract still behaves like a standalone local-login
service:

- the playbook does not reconcile a dedicated Open WebUI Keycloak client
- the expected OIDC secret is treated as an externally provided local file
- the documented routine login path is the local bootstrap admin password

That leaves operators with one more service-specific credential to remember for
day-to-day use even though Keycloak already exists precisely to remove that
burden.

At the same time, Open WebUI is an operational workbench, not a purely public
product surface. Removing local auth entirely would make recovery and smoke
verification depend on the full external identity chain being healthy. The repo
still needs one controlled recovery path when Keycloak or the browser SSO flow
is degraded.

## Decision

Open WebUI will use a dedicated repo-managed Keycloak OIDC client for routine
operator sign-in while retaining the local bootstrap admin as a break-glass
fallback.

### Auth model

- routine operator login uses Keycloak OIDC
- the Open WebUI login form remains enabled
- password auth remains enabled for the repo-managed admin bootstrap account
- public signup remains disabled
- the service stays private behind the existing Proxmox host Tailscale proxy at
  `http://100.64.0.1:8008`

### Secret flow

- the Keycloak runtime owns the Open WebUI client secret
- that client secret is mirrored to the controller under `.local/keycloak/`
- the Open WebUI runtime consumes that mirrored Keycloak-managed secret instead
  of expecting a separately provided `.local/open-webui/oidc-client-secret.txt`

### Playbook contract

`playbooks/open-webui.yml` gains an explicit Keycloak-client reconciliation
step before the Open WebUI runtime converge step. The playbook itself becomes
the full repo-managed surface for:

1. the private Tailscale-facing host proxy
2. the dedicated Open WebUI Keycloak client
3. the Open WebUI runtime

### Verification contract

Verification must prove both sides of the new auth model:

- the local Open WebUI root page responds
- the local bootstrap admin can still sign in when password auth is enabled
- the OIDC login endpoint redirects correctly when Keycloak OIDC is enabled

## Consequences

### Positive

- operators stop relying on a separate routine Open WebUI-only password
- the OIDC client secret becomes repo-managed and mirrored the same way as other
  Keycloak-integrated services
- the Open WebUI playbook becomes a self-contained deployment surface rather
  than assuming a manual Keycloak-side prerequisite
- the break-glass path remains available for operational recovery

### Trade-Offs

- Open WebUI still carries local password auth, so the service now supports both
  OIDC and a recovery credential rather than an OIDC-only posture
- the dedicated Keycloak client introduces another client object to reconcile,
  test, and document

### Rejected Alternative

Reject “OIDC-only with no local fallback” for now. That would make a Keycloak or
session-broker outage block recovery access to the operator workbench and would
remove a simple repo-verifiable smoke path.

## Implementation Notes

- add `open_webui` client defaults and secret mirroring to `keycloak_runtime`
- add a standalone `open_webui_client.yml` task entrypoint so the Open WebUI
  playbook can reconcile only its own client contract
- change Open WebUI defaults from “OIDC later” to “OIDC enabled by default”
- document the Keycloak-first routine login and the retained local admin
  fallback in the Open WebUI and Keycloak runbooks
