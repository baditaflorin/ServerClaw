# Release 0.179.57

- Date: 2026-11-06

## Summary
- Keep sanitized Tailnet identities in generic shared-address space so exported network-policy checks retain their source classification.
- Prune only accepted findings eliminated by the public projection; reject new non-info findings, malformed policy/baseline pairs and unsafe file aliases before writing exported baselines.
- Run actual sanitized-policy regressions and portable foreign-source negative controls in Woodpecker while preserving private policy and baseline bytes.

## Platform Impact
- Publication automation only. Platform version remains 0.179.59; this release applies no runtime policy or application deployment.

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
