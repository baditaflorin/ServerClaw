# ADR 0061: GlitchTip For Application Exceptions And Task Failures

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

Metrics, logs, and traces are necessary but still leave a gap around:

- uncaught application exceptions
- failed background jobs
- release regressions that surface as repeated error signatures
- grouping failures by environment, release, and service owner

As more internal applications are added, that gap becomes operationally expensive.

## Decision

We will use GlitchTip or an equivalent self-hosted Sentry-compatible platform for application exception and task-failure visibility.

Initial expectations:

1. internal applications and automation components report structured errors
2. issues are grouped by service, environment, and release where possible
3. notifications route into the approved operator channels
4. issue visibility stays private-first and operator-oriented

Initial integration targets:

- mail platform application components
- Windmill jobs or wrappers where structured error reporting is practical
- future internal APIs and operator-facing applications

## Consequences

- Operators gain a focused error console instead of inferring repeated failures from raw logs.
- Agents can summarize regressions, top error groups, and new issue spikes with less noise.
- Application teams need release and environment metadata discipline for the system to be useful.
- Another stateful application is added to the control plane and must be operated deliberately.

## Boundaries

- Exception tracking does not replace logs, traces, or uptime checks.
- Sensitive payloads must be scrubbed before they are reported.
- Public user-facing error reporting is out of scope unless a later ADR approves it.
