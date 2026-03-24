# Release 0.130.1

- Date: 2026-03-24

## Summary
- finalized ADR 0140 by hardening the public Grafana edge so unauthenticated dashboard URLs redirect to login, `/api/health` is blocked, and the hostname is marked `noindex`
- fixed the generated Prometheus latency SLO recording rules so Prometheus accepts the rule set during monitoring convergence
- recorded the repository release needed to carry the Grafana hardening live-state follow-through on top of the current integrated `main`

## Platform Impact
- repository version advances to `0.130.1`
- platform version remains `0.114.7` until the live receipts for ADR 0140 are recorded from `main`

## Residual Risk
- the shared `make live-apply-service service=grafana env=production` path still depends on the controller-local ntfy Alertmanager password file being present in `.local/ntfy/alertmanager-password.txt` when Alertmanager runtime validation runs in a fresh worktree

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
