# Prepare Mail Platform Rollout

## Purpose

This runbook records the implementation checklist for ADR 0040 before any live mail deployment begins.

It exists so the next assistant can turn the mail decision into automation without reconstructing requirements from chat history.

## Target End State

The target mail stack is:

- primary mail server: Stalwart on `docker-runtime-lv3`
- local submission relay: Postfix sidecar on the same runtime host
- management surface: Stalwart REST API with scoped API keys
- observability surface: Grafana dashboard on `monitoring-lv3`
- fallback delivery: secondary relay route for queued outbound messages

## Preconditions

Before implementation starts, confirm:

1. the Docker runtime VM still remains the correct home for stateful containerized services
2. the monitoring VM still uses Grafana plus InfluxDB as the shared dashboard path
3. no other active workstream is already changing SMTP NAT, DNS publication, or Docker runtime network exposure
4. the chosen mail hostname, MX hostnames, and admin hostname do not conflict with the existing `lv3.org` publication model

## Required Design Inputs

Capture these values in repo-managed inventory or stack defaults before live work:

- primary mail hostname
- administrative HTTPS hostname
- local domains to receive mail for
- trusted source networks for internal SMTP submission
- fallback relay hostname, credentials, and activation policy
- DKIM selector names
- SPF and DMARC policy values
- reverse DNS target for the public sending IP
- data path and backup path for mail state

## Implementation Sequence

Implement the rollout in this order:

1. add stack variables, secret references, and a dedicated mail runtime role
2. converge the Docker runtime VM with Stalwart and the local relay sidecar, but keep public SMTP exposure disabled at first
3. verify private-network submission from trusted sources
4. wire metrics and webhook ingestion into the monitoring stack
5. provision the Grafana dashboard and verify queue and delivery panels
6. add DNS, reverse DNS, and public SMTP firewall or NAT publication
7. verify direct outbound delivery and fallback relay behavior
8. only then switch existing notification senders to the new local submission endpoint

## Observability Checklist

The Grafana dashboard should expose at least:

- accepted outbound submissions
- inbound accepted messages
- successful deliveries
- temporary failures
- permanent failures
- queue depth
- oldest queued item age
- authentication failures
- policy rejections
- fallback relay activations
- mail data disk usage

If one of these cannot be sourced from Stalwart metrics alone, ingest it from webhook events or queue inspection automation instead of dropping it from the dashboard.

## Verification Targets

The implementation should define explicit automated checks for:

- container health for the Stalwart and Postfix services
- local SMTP submission over the private network
- message queue visibility
- API authentication with a scoped non-admin key
- Grafana dashboard presence and data freshness
- fallback delivery after intentionally induced primary-route failure
- backup coverage for mail data and configuration

## Cutover Rule

Do not replace the current external sendmail dependency until:

- internal submission succeeds from the intended callers
- direct outbound delivery succeeds
- fallback delivery has been exercised
- Grafana shows recent end-to-end mail events
- restore steps for mail state are documented
