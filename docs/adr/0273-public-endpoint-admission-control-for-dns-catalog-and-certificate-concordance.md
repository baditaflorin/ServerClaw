# ADR 0273: Public Endpoint Admission Control For DNS Catalog And Certificate Concordance

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-28

## Context

Recent exposure and repair receipts show that public endpoint drift appears in
several forms at once:

- undeclared hostnames remain present in DNS
- catalog and zone records disagree
- TLS probes fail or a hostname is absent from the shared certificate SAN set
- endpoint publication is repaired only after user-visible breakage

The platform already has route and DNS truth direction, but it still needs an
admission rule that prevents these mismatches from merging or replaying live.

## Decision

We will require **public endpoint admission control** that proves concordance
across the DNS catalog, publication model, and certificate scope.

### Required admission checks

- hostname exists in the canonical catalog
- DNS records match the declared publication target
- edge publication config contains the hostname
- certificate plan covers the hostname before promotion
- declared auth and exposure class match the endpoint audience

### Enforcement rules

- a public hostname change may not merge or live-apply until all admission
  checks pass
- undeclared public hostnames must surface as policy violations
- certificate repair after the fact is not an acceptable steady-state workflow

## Consequences

**Positive**

- public endpoint drift is caught before user traffic finds it
- DNS, edge, and TLS ownership stay tied to one declared service identity
- certificate SAN planning becomes proactive instead of reactive

**Negative / Trade-offs**

- shared-edge changes require tighter sequencing and more preflight evidence
- emergency hostname publication may feel slower without a prepared admission
  path

## Boundaries

- This ADR governs public endpoint admission across catalog, DNS, and
  certificate truth.
- It does not replace browser-auth journey verification for the applications
  behind those endpoints.

## Related ADRs

- ADR 0015: LV3.org DNS and subdomain model
- ADR 0021: Public subdomain publication at the NGINX edge
- ADR 0076: Subdomain governance and DNS lifecycle
- ADR 0101: Automated certificate lifecycle management
- ADR 0139: Subdomain exposure audit
- ADR 0252: Route and DNS publication assertion ledger
