# ADR 0300: Falco For Container Runtime Syscall Security Monitoring And Autonomous Anomaly Detection

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-29

## Context

The platform's current security posture covers:

- admission-time CVE scanning in Harbor (ADR 0201)
- static SBOM and vulnerability scanning in the CI gate (ADR 0298)
- network-layer visibility via ntopng (ADR 0059)
- Lynis host hardening audits captured in `config/lynis-suppressions.json`

None of these mechanisms detect anomalous **runtime behaviour** inside a running
container. A compromised container, a supply-chain attack that passes CVE
admission, a lateral movement attempt, or an unexpected privilege escalation is
invisible until an operator happens to notice it in logs or a network trace.

The platform runs workloads across 87+ services on shared VMs. A single exploited
service can attempt to read secrets from the OpenBao agent socket, write to the
host filesystem, or spawn unexpected child processes. Without a kernel-level
observer these events produce no alert.

Falco (`falcosecurity/falco`) is a CNCF-graduated runtime security tool. It
attaches to the Linux kernel via eBPF or a kernel module and evaluates a
rule-based policy against every syscall made by every container process. When a
rule matches (e.g. a shell spawned inside a container, a write to `/etc`, a
network connection to an unexpected port, a container namespace escape attempt),
Falco emits a structured JSON event within milliseconds. It is Apache-2.0-licensed,
has been in production use since 2016, ships as a single binary with a Docker
image and a Helm chart, and exposes a gRPC output API and a JSON webhook output
that integrates with any consumer.

## Decision

We will deploy **Falco** as a systemd service on each production VM, using the
eBPF probe to avoid a kernel module compile dependency, and route its output to
the platform's Loki and NATS pipelines.

### Deployment rules

- Falco is installed as a systemd service on each VM managed by the
  `docker-runtime-lv3`, `docker-build-lv3`, `monitoring-lv3`, and
  `postgres-lv3` hosts; the Ansible role for each VM manages Falco installation,
  version, and rules
- Falco uses the `falco-driver-loader` eBPF probe (`falco-bpf`); it does not
  require a kernel module or a kernel header package
- the Falco binary version is pinned in `versions/stack.yaml` and bumped via the
  Renovate Bot process (ADR 0297)
- Falco is never run as a container on the same host it is monitoring; running
  Falco in a container it could theoretically monitor undermines the integrity
  guarantee

### Rule configuration

- the default Falco ruleset is the starting point; platform-specific overrides
  are maintained in `config/falco/rules.d/platform-overrides.yaml`
- rules are tuned to suppress known-safe patterns (e.g. Dozzle reading
  `/var/run/docker.sock`, the backup agent accessing `/etc` for snapshot),
  documented in `config/falco/suppressions.yaml` alongside the business reason
- a rule addition or suppression requires a pull request that passes the
  validation gate (ADR 0087) and includes a comment citing the reason; rules are
  not edited in production

### Output routing

- Falco emits JSON events to stdout; Alloy (the Grafana agent already deployed on
  each VM) tails the Falco journald unit and ships structured log events to Loki
  with label `job="falco"`
- a Falco webhook output is also configured to POST `priority >= WARNING` events
  to a lightweight Windmill webhook endpoint that:
  1. publishes the event to the NATS `platform.security.falco` subject (ADR 0276)
  2. for `CRITICAL` events, publishes an ntfy notification to
     `platform.security.critical` (ADR 0299)
  3. records the event in the mutation audit log (ADR 0066) as a
     `security_anomaly_detected` entry
- `INFO`-level events remain in Loki only; they do not trigger the NATS or ntfy
  path to avoid alert fatigue

### Automated response scope

- Falco detects and reports; it does not autonomously kill containers or modify
  rules in response to a match
- the correction loop for a `CRITICAL` Falco event is `escalate` requiring
  operator approval; no automated container stop is initiated without explicit
  approval (ADR 0204)
- future ADRs may introduce containment automation once the rule signal-to-noise
  ratio is validated

## Consequences

**Positive**

- the platform gains visibility into container-level runtime anomalies that static
  scanning and network monitoring cannot detect
- structured JSON events in Loki enable forensic queries for incident
  post-mortems without relying on raw kernel logs
- the eBPF probe approach means Falco does not require a custom kernel module and
  works on the Proxmox-managed Debian 13 kernel without additional build steps
- Falco events feed the existing NATS and ntfy pipelines with no new transport
  dependency

**Negative / Trade-offs**

- eBPF probe attachment requires Linux 4.14+ and CAP_BPF; the Proxmox Debian 13
  kernel meets this requirement but an upstream kernel update that changes the BPF
  interface may require a Falco version bump
- the initial rule tuning period will produce false positives until
  platform-specific suppressions are calibrated; this requires active operator
  review during the first two weeks post-deployment
- Falco's CPU overhead per container increases with event volume; high-syscall
  workloads (e.g. Playwright browser runners) may require dedicated rule tuning
  to suppress chatty but benign syscall patterns

## Boundaries

- Falco monitors container runtime syscalls on VMs where it is deployed; it does
  not monitor the Proxmox hypervisor host or the backup VM in the first phase
- Falco does not perform network packet inspection; ntopng (ADR 0059) covers
  that layer
- Falco rules are not a replacement for OS hardening; Lynis and the Ansible
  hardening playbooks remain the authoritative hardening surface

## Related ADRs

- ADR 0059: Ntopng for network flow visibility
- ADR 0066: Structured mutation audit log
- ADR 0087: Repository validation gate
- ADR 0102: Security posture reporting
- ADR 0126: Observation-to-action closure loop
- ADR 0204: Self-correcting automation loops
- ADR 0276: NATS JetStream as the platform event bus
- ADR 0298: Syft and Grype for SBOM and CVE scanning
- ADR 0299: Ntfy as the push notification channel

## References

- <https://github.com/falcosecurity/falco>
