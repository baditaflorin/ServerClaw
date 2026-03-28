# Release 0.177.28

- Date: 2026-03-28

## Summary
- repaired shared edge publication playbooks so service-specific converges always load the canonical platform topology before rebuilding the shared certificate SAN set, preventing `wiki.lv3.org` and `draw.lv3.org` from dropping out of live publication
- replayed the shared edge from merged `main`, re-expanded the live certificate, and re-verified the governed Outline surface at `wiki.lv3.org`
- integrated ADR 0194 by converging the dedicated Coolify guest, protected dashboard publication, wildcard app ingress, and the governed `lv3 deploy-repo` wrapper with end-to-end repo deployment verification

## Platform Impact
- promotes the platform to `0.130.35`; the 2026-03-28 merged-`main` replay restored shared edge certificate coverage for `wiki.lv3.org` and `draw.lv3.org` and keeps Coolify repo deployment live with protected dashboard publication plus wildcard app ingress.

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
