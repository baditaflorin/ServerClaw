# WS-0501: HTTPS alert presence contract

## Problem

The target output is already tracked in a clean repository checkout, but the
deployment-local HTTPS alert output is ignored. Treating either paired output
as an optional-validation presence signal therefore made a clean checkout
incorrectly require the ignored alert artifact.

## Decision

`--check-if-present` keys its optional behavior solely on the ignored
`https_tls_alerts.yml` file. If that file is absent, the clean checkout is
accepted. If it exists, the generator strictly compares both paired outputs,
so stale alerts or stale targets remain a validation failure.

## Boundaries

This correction changes no catalog, topology, secret, runtime configuration,
or generated output. The role of the normal `--check` mode remains unchanged.
