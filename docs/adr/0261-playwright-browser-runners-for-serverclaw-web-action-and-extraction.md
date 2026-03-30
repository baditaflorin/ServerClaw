# ADR 0261: Playwright Browser Runners For ServerClaw Web Action And Extraction

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.95
- Implemented In Platform Version: 0.130.61
- Implemented On: 2026-03-30
- Date: 2026-03-28

## Context

ServerClaw should be able to act on websites, not only call APIs. That includes:

- structured extraction from pages
- authenticated navigation
- form completion
- download and upload flows
- screenshot and PDF capture for receipts or human review

The repository already selected Playwright for authenticated browser-journey
verification of first-party apps, but user-facing assistant work needs a
separate action-runtime contract.

## Decision

We will use **Playwright browser runners** as the default ServerClaw browser
action and extraction runtime.

### Runtime rule

- each task runs in an isolated browser context
- user identity, cookies, downloads, and artifacts remain scoped to the
  relevant workspace or delegated session
- browser output is normalized into structured results, screenshots, downloads,
  and receipts rather than raw uncontrolled browser access

### Separation rule

- ADR 0247 uses Playwright to prove our protected apps work
- this ADR uses Playwright to let ServerClaw act on external web surfaces under
  governed policy

## Consequences

**Positive**

- ServerClaw can automate the class of work that only exists behind browser
  sessions.
- One mature browser stack can serve both product assurance and user-facing web
  actions with different policies.
- Artifacts such as screenshots and downloaded files become first-class outputs
  instead of side effects on a workstation.

**Negative / Trade-offs**

- Browser automation is inherently slower and more fragile than direct API work.
- Credential hygiene, CAPTCHA handling, and anti-bot measures require careful
  product policy.

## Boundaries

- Playwright runners are not a license for arbitrary open-internet scraping.
- This ADR does not retire API-first integrations when a clean API exists.
- Browser automation should stay governed, scoped, and observable.

## Related ADRs

- ADR 0247: Authenticated browser journey verification via Playwright
- ADR 0258: Temporal as the durable ServerClaw session orchestrator

## References

- <https://playwright.dev/docs/intro>
- <https://playwright.dev/docs/auth>
