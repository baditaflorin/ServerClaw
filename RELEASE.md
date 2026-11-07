# Release 0.179.58

- Date: 2026-11-07

## Summary
- Correct hypervisor log-shipping alert selection and grouping to preserve shipper_host independently of the collector guest scrape labels.
- Exercise actual guest scrape labels in Prometheus fixtures and record native validation plus exact merged-main replay against both installed files.
- Record five fresh shippers and healthy alert rules after an atomic reload without changing application deployment dates or credentials.

## Platform Impact
- Platform0.179.60 records the exact-main log-shipping alert correction; no catalog application deployment.

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
