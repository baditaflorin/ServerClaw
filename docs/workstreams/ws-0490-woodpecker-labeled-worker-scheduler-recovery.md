# WS-0490: Woodpecker labeled-worker scheduler recovery

## Status

Ready for merge. The live recovery has been applied and verified.

## Scope

The required CI label was advertised by two healthy workers, but both had a
persisted no-schedule flag. The repair restored eligibility for only those
two workers. It did not change application services, edge routing, identity
configuration, or Proxmox runtime configuration.

## Verification

- Both previously pending release-validation pipelines transitioned to running
  and completed successfully.
- GitHub received successful statuses for both required Woodpecker contexts.
- The receipt and generated platform manifest validate through the repository
  checks.

## Handoff

The branch records the targeted recovery in
`receipts/live-applies/2026-08-31-woodpecker-lv3-scheduler-recovery.json`.
Future CI investigations should first confirm that active label-matched
workers are schedulable before changing pipeline definitions or application
deployment configuration.
