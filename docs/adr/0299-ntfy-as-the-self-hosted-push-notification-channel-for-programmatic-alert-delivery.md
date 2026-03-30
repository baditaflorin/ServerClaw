# ADR 0299: Ntfy As The Self-Hosted Push Notification Channel For Programmatic Alert Delivery

- Status: Accepted
- Implementation Status: Live applied
- Implemented In Repo Version: 0.177.152
- Implemented In Platform Version: 0.130.95
- Implemented On: 2026-04-03
- Date: 2026-03-29

## Context

`config/ntfy/server.yml` already exists in the repository, indicating that ntfy
has been deployed operationally. However, there is no governing ADR that defines
ntfy's role, its integration contracts with other platform components, or the
rules for how automation and correction loops use it as an alert delivery channel.

The platform currently routes human-visible alerts through Alertmanager and
Mattermost (ADR 0097). That path is well-suited for Prometheus rule-based alerts
that target operators watching a Mattermost channel. It is not well-suited for
programmatic notifications from autonomous workflows that need to deliver a
targeted push to a specific operator's mobile device or desktop without
operator-maintained Alertmanager routing rules.

The correction-loop architecture (ADR 0204), the observation-to-action closure
loop (ADR 0126), and the watchdog escalation pattern (ADR 0172) all produce events
that should reach a human within seconds when they require approval or signal a
non-recoverable failure. A lightweight, REST-callable notification channel with
zero per-notification configuration overhead is a missing operational primitive.

Ntfy (`binwiederhier/ntfy`) is a Go-based self-hosted pub/sub notification server.
It publishes push notifications to web, Android, and iOS clients by sending an
HTTP PUT or POST to a topic URL. It is Apache-2.0-licensed, ships as a single
Go binary with a Docker image under 20 MB, and has been in active production use
since 2021. Any Windmill script, Ansible task, shell command, or Gitea Actions
step can publish a notification with a single `curl` call requiring no SDK or
configuration beyond a topic name and an access token.

## Decision

We will formalise **ntfy** as the platform's self-hosted push notification channel
and define the integration contracts for all automation components that publish
to it.

### Deployment rules

- ntfy runs as a Docker Compose service on the `docker-runtime-lv3` VM
- the `config/ntfy/server.yml` file is the canonical runtime configuration and is
  managed by the Ansible role for `docker-runtime-lv3`
- the Docker image is pulled through Harbor (ADR 0068) and pinned to a specific
  SHA digest
- ntfy is published internally at `ntfy.lv3.internal` on the guest network and
  through the NGINX edge (ADR 0095) at `ntfy.lv3.org` behind authentication
- access tokens are stored in OpenBao (ADR 0043) and are injected at runtime;
  no long-lived tokens are committed to the repository

### Topic naming convention

- every ntfy topic uses a lowercase hyphenated slug such as
  `platform-alerts` or `platform-security-critical`; dotted NATS subject names
  are not reused directly as ntfy topic paths because the live ntfy HTTP
  publish endpoint rejects dotted topic names with `404 page not found`
- the topic registry is declared in `config/ntfy/topics.yaml` alongside
  `server.yml`; topics not in the registry are not published to by governed
  automation

### Integration contracts

- **Windmill workflows**: any workflow step that reaches an `escalate` repair
  action in `correction-loops.json` (ADR 0204) publishes to the appropriate ntfy
  topic via the platform's Windmill resource `res:ntfy/platform`; this resource
  holds the access token and base URL, injected from OpenBao
- **Ansible playbooks**: Ansible roles that perform irreversible mutations publish
  a `platform-ansible-warn` notification at the start and a
  `platform-ansible-info` notification on successful completion; failures publish
  to `platform-ansible-critical`; these ntfy paths remain hyphenated and are
  distinct from the dotted canonical NATS subject names
- **Gitea Actions**: the CI validation gate (ADR 0087) publishes a
  `platform-ci-critical` notification when a gate failure blocks a merge; this
  reaches the operator without requiring them to poll the Gitea UI
- **NATS bridge**: a lightweight Windmill subscription job bridges selected
  high-priority NATS subjects (`platform.security.cve_delta`,
  `platform.watchdog.stale_job`) to ntfy topics, so any NATS producer gains push
  delivery without directly depending on ntfy

### Deduplication and rate limiting

- ntfy is configured with per-token rate limits in `server.yml` to prevent runaway
  automation from flooding the channel
- Windmill workflows that publish ntfy notifications use the idempotency key
  pattern (ADR 0165); a notification for the same event ID is not re-sent within
  a configurable deduplication window

## Consequences

**Positive**

- any automation component can deliver a targeted push notification with a single
  HTTP call; there is no per-notification Alertmanager routing rule to maintain
- operators receive critical automation escalations on mobile without being tied
  to a Mattermost session
- the NATS bridge means NATS-producing components do not need a direct ntfy
  dependency; push delivery is an opt-in consumer

**Negative / Trade-offs**

- ntfy is a single-instance deployment with no built-in HA; a restart loses
  in-flight notifications; this is acceptable for a best-effort push channel
  but not for guaranteed delivery
- the topic registry in `config/ntfy/topics.yaml` must be kept in sync with
  governed automation; unregistered topics used by new components will not appear
  in the registry

## Boundaries

- Ntfy is a human-facing push delivery channel, not a durable message queue;
  guaranteed delivery and replay are the responsibility of NATS JetStream
  (ADR 0276)
- Ntfy does not replace Mattermost (ADR 0097) for team-visible alert threads,
  incident discussion, or runbook links; the two channels serve different audiences
- Ntfy does not route to PagerDuty or external on-call systems; the platform is
  operated by a single operator team for whom mobile push is sufficient

## Related ADRs

- ADR 0044: Windmill for agent and operator workflows
- ADR 0050: Notification profiles
- ADR 0077: Compose runtime secrets injection
- ADR 0097: Alerting routing and oncall runbook model
- ADR 0126: Observation-to-action closure loop
- ADR 0165: Workflow idempotency keys and double-execution prevention
- ADR 0172: Watchdog escalation and stale-job self-healing
- ADR 0204: Self-correcting automation loops
- ADR 0276: NATS JetStream as the platform event bus

## References

- <https://github.com/binwiederhier/ntfy>
