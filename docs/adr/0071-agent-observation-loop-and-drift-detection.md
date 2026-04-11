# ADR 0071: Agent Observation Loop And Autonomous Drift Detection

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.59.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-23
- Date: 2026-03-22

## Context

Today's platform state is observed reactively:

- alerts fire when a metric threshold is breached
- Uptime Kuma signals when an endpoint goes down
- a human or agent runs a playbook and notices drift during convergence

There is no proactive loop that routinely compares intended state (repo + `stack.yaml`) against live state and surfaces the delta as a structured finding before it becomes an incident. Drift accumulates silently: package versions skew, container images fall behind, a unit is disabled, a firewall rule is missing.

For agents to be genuinely useful operations partners rather than reactive tools, they need a scheduled observation capability with a governed output format.

## Decision

We will implement a scheduled agent observation loop that detects drift and publishes structured findings.

Loop components:

1. **observation workflow** — a Windmill workflow (`platform-observation-loop`) scheduled to run every 4 hours
2. **drift checks** — the workflow executes a series of named checks, each producing a structured result:
   - `check-vm-state` — compare running VMs against `stack.yaml` guest definitions
   - `check-service-health` — call every probe in `health-probe-catalog.json` (ADR 0064)
   - `check-image-freshness` — compare pinned digests in `image-catalog.json` against running containers (ADR 0068)
   - `check-secret-ages` — compare last-rotated timestamps in `secret-catalog.json` against rotation periods (ADR 0065)
   - `check-certificate-expiry` — query step-ca for certificates expiring within 14 days
   - `check-backup-recency` — verify the most recent PBS backup is within the declared retention window
3. **finding format** — each check emits a structured finding to NATS (`platform.findings.observation`):
   ```json
   { "check": "check-image-freshness", "severity": "warning|critical|ok",
     "summary": "3 images are more than 30 days behind upstream",
     "details": [...], "ts": "<ISO-8601>", "run_id": "<uuid>" }
   ```
4. **finding routing** — findings above `ok` are forwarded to Mattermost (ADR 0057) in the `#platform-findings` channel and to GlitchTip (ADR 0061) for tracking
5. **agent summary** — Open WebUI (ADR 0060) surfaces a daily digest of findings so an operator reviewing the dashboard sees the current drift posture without querying individually

Autonomous remediation scope (first iteration):

- findings below `critical` severity are surfaced only; no automatic remediation
- `critical` findings for known self-healing conditions (e.g. a container that exited cleanly) can trigger a named command from the command catalog (ADR 0048) if the command is marked `auto_approve: true`

## Consequences

- Drift is detected within hours of occurring rather than at the next human-initiated convergence run.
- The observation loop is itself a managed service; if it stops running, the absence of findings is itself a signal (dead-man's switch pattern via the NATS last-message timestamp).
- Agents summarising platform health have a structured, current, canonical finding stream rather than assembling it from scattered checks.
- False positive findings (e.g. expected temporary downtime during maintenance) must be suppressible via a maintenance-window mechanism to avoid alert fatigue.

## Boundaries

- Autonomous remediation is limited to pre-approved self-healing commands in the first iteration; all other findings require human or agent-initiated action.
- The observation loop does not replace Grafana alerts or Uptime Kuma; it operates at a different cadence and granularity.
- Security-specific scanning (vulnerability CVEs, secret leaks) is handled by dedicated tools referenced from this loop but not implemented within it.

## Implementation Notes

- The controller now executes the six checks through [scripts/platform_observation_tool.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server-agent-observation-loop/scripts/platform_observation_tool.py), writing structured findings under [`.local/platform-observation/latest/`](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server-agent-observation-loop/.local/platform-observation/latest) and an Open WebUI digest under [`.local/open-webui/platform-findings-daily.md`](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server-agent-observation-loop/.local/open-webui/platform-findings-daily.md).
- The machine-readable contracts for probes, secrets, images, and findings now live in [config/health-probe-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server-agent-observation-loop/config/health-probe-catalog.json), [config/secret-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server-agent-observation-loop/config/secret-catalog.json), [config/image-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server-agent-observation-loop/config/image-catalog.json), and [docs/schema/platform-finding.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server-agent-observation-loop/docs/schema/platform-finding.json).
- Findings can optionally route to NATS, Mattermost, and GlitchTip through the controller-local secret contract additions in [config/controller-local-secrets.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server-agent-observation-loop/config/controller-local-secrets.json), with lane metadata recorded in [config/control-plane-lanes.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server-agent-observation-loop/config/control-plane-lanes.json) and [config/api-publication.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server-agent-observation-loop/config/api-publication.json).
- Windmill now seeds disabled placeholder scripts and schedules for the observation loop and daily digest through [roles/windmill_runtime/defaults/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server-agent-observation-loop/roles/windmill_runtime/defaults/main.yml) and [roles/windmill_runtime/tasks/main.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server-agent-observation-loop/roles/windmill_runtime/tasks/main.yml), but live activation remains pending equivalent secret and execution contracts inside Windmill.
- Operator usage and the five-hour dead-man contract are documented in [docs/runbooks/agent-observation-loop.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server-agent-observation-loop/docs/runbooks/agent-observation-loop.md).
