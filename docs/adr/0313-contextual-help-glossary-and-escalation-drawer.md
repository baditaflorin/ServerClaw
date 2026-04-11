# ADR 0313: Contextual Help, Glossary, And Escalation Drawer

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.139
- Implemented In Platform Version: 0.130.87
- Implemented On: 2026-04-02
- Date: 2026-03-31

## Context

The repository already contains strong documentation and runbooks, but users
still have to leave the flow of work to answer basic questions:

- what does this page do?
- what does this platform term mean?
- where is the right runbook?
- what should I do if this action fails or I get stuck?

That context switch is especially painful during onboarding, incidents, and
infrequently used administrative tasks.

## Decision

We will provide a shared **contextual help and escalation drawer** in
first-party browser surfaces.

### Drawer contents

Every first-party page should be able to surface:

- a short explanation of the page purpose and intended audience
- glossary definitions for platform-specific terms on that page
- links to the most relevant runbooks, ADRs, and reference pages
- the escalation path if the user cannot proceed safely

### Content-source rule

The help drawer should not become a second documentation system. It should
summarize and deep-link to the canonical sources already maintained in docs,
runbooks, and living knowledge surfaces.

### Escalation rule

When a page includes a risky or failure-prone task, the help drawer must say:

- how to back out safely
- where to find the owning runbook
- how to ask for help or hand off the task

## Consequences

**Positive**

- users can answer common questions without abandoning their current page
- platform vocabulary becomes more consistent because the glossary is visible in
  context
- the help system becomes a practical bridge between onboarding, docs, and
  operational recovery

**Negative / Trade-offs**

- context-aware help content must stay synchronized with the page behavior or it
  becomes misleading
- the drawer can become cluttered if it tries to mirror full documentation

## Boundaries

- This ADR does not replace full runbooks, docs, or wiki content.
- This ADR does not require third-party product-native UIs to expose the same
  drawer, though the workbench should still link to contextual help before the
  user leaves a first-party page.

## Implemented Live Replay

- The branch-local live apply on 2026-04-02 replayed the shared drawer from
  `codex/ws-0313-live-apply` source commit `154564f3c2433d5dd0b295a64c34272fd3b7f956`,
  converged the interactive `ops_portal` runtime on `docker-runtime`,
  republished the generated docs and changelog portals through `nginx-edge`, and
  recorded the proof in
  `receipts/live-applies/2026-04-02-adr-0313-contextual-help-live-apply.json`.
- Earlier direct replay attempts remain preserved in
  `receipts/live-applies/evidence/` because they exposed two real defects on the
  latest lineage: Docker bridge chains could disappear after nftables
  evaluation on `docker-runtime`, and the mirrored runtime tree imported
  `platform.datetime_compat` even though the isolated image layout does not ship
  the repo `platform` package.
- After `origin/main` advanced to repository version `0.177.138` during the
  first exact-main attempt, the refreshed replay from
  `codex/ws-0313-main-integration` source commit
  `ab0d29de49bee1a9ac0c17c17afd4fc5491d8927` cut repository version
  `0.177.139`, converged the interactive `ops_portal` runtime on
  `docker-runtime` with final recap
  `ok=189 changed=14 unreachable=0 failed=0 skipped=36`, republished the
  generated docs and changelog portals through `nginx-edge`, and recorded the
  canonical proof in
  `receipts/live-applies/2026-04-02-adr-0313-contextual-help-mainline-live-apply.json`.

## Related ADRs

- ADR 0094: Developer portal and documentation site
- ADR 0199: Outline living knowledge wiki
- ADR 0239: Browser-local search experience via Pagefind
- ADR 0242: Guided human onboarding via Shepherd tours
- ADR 0312: Shared notification center and activity timeline

## References

- [Developer Portal](../runbooks/developer-portal.md)
- [Portal Authentication By Default](../runbooks/portal-authentication-by-default.md)
