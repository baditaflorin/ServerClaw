# 0pipe moved

The configuration of the 0pipe build server (Hetzner HEL1: Proxmox host + build VM 100), its scripts, the rebuild recipe and a snapshot of everything outside the
machines (CT108 load-controller nodes, buildx alias, Prometheus job, builder pool, DNS, tailnet policy lines, hostconf entries, PDM remote) live in the private
repository **`baditaflorin/0pipe`** (https://github.com/baditaflorin/0pipe) since 2026-10-29. This directory held the same files from 2026-10-29 until then
(PRs #609, #611, #612, #613 here) and was identical to that repository when it was replaced by this pointer.

What stays in THIS repository because it is fleet-wide: the tailnet policy (`config/tailscale/policy.hujson`: `tag:build-worker`, 10.80.10.0/24), `config/hostconf/hostconf.yaml`
(`pve-0pipe`, `0pipe-build`), and the alert rules (`config/prometheus/rules/fleet-ci-host-pressure.yml`, `fleet-disk-health.yml`).
