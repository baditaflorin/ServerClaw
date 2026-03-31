# Release 0.177.118

- Date: 2026-03-31

## Summary
- implements ADR 0292 by hardening exact-main Lago replay recovery, verifying the protected billing.lv3.org surface plus public event-ingest and current-usage smoke contracts on merged mainline, and restoring the governed Restic live-apply backup trigger for the service wrapper

## Platform Impact
- Platform version advances to 0.130.77 by promoting the ADR 0292 exact-main Lago replay, with verified billing.lv3.org publication, public ingest, current-usage aggregation, and the governed restic live-apply backup trigger on top of the 0.130.76 baseline

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
