#!/usr/bin/env python3
"""ADR 0443 — controller-side topology reconciler.

Reads the active deployment's enabled-services set, computes the
expected (host -> {service, port}) mapping from
platform_service_registry, optionally fans out to every host to collect
a topology probe (scripts/topology_probe.py), and writes a drift report
to .local/deployments/<slug>/state/drift-report.{json,md}.

Two modes:

  --mode plan
      Compute and print the expected mapping. No SSH. Useful in CI to
      validate the registry against itself.

  --mode reconcile
      SSH-fan-out, collect probes, diff against expected. Writes
      drift-report.{json,md}. Exit code 1 when drift is detected, 0
      otherwise.

  --probe-input <file.json>
      Skip SSH; load the probe snapshots from a JSON file instead.
      Shape: {"<host>": {<probe-snapshot>, ...}}. Used by tests and by
      operators who already collected probes via Ansible.

Usage:

    python3 scripts/topology_reconciler.py --mode plan
    python3 scripts/topology_reconciler.py --mode reconcile
    python3 scripts/topology_reconciler.py --mode reconcile --deployment 0fork
    python3 scripts/topology_reconciler.py --mode reconcile --probe-input /tmp/probes.json

Output schema: drift-report/v1.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import deployment as _dep_module  # noqa: E402

DRIFT_SCHEMA = "drift-report/v1"


def _utc_now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------
# Loading registries
# --------------------------------------------------------------------------


def load_service_registry(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    path = repo_root / "inventory" / "group_vars" / "all" / "platform_services.yml"
    return yaml.safe_load(path.read_text())["platform_service_registry"]


def load_profile_catalog(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    path = repo_root / "inventory" / "group_vars" / "all" / "service_profiles.yml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    return data.get("service_profiles", {})


# --------------------------------------------------------------------------
# Expected mapping
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ExpectedService:
    name: str
    host_group: str
    internal_port: int | None
    container_name: str | None


def build_expected(
    enabled: Iterable[str],
    service_registry: dict[str, Any],
) -> dict[str, list[ExpectedService]]:
    """Group enabled services by their host_group.

    Returns {host_group: [ExpectedService, ...]}.
    """
    expected: dict[str, list[ExpectedService]] = {}
    for name in enabled:
        entry = service_registry.get(name)
        if not entry:
            continue
        host = entry.get("host_group")
        if not host:
            continue
        port = entry.get("internal_port")
        try:
            port = int(port) if port is not None else None
        except (TypeError, ValueError):
            port = None
        expected.setdefault(host, []).append(
            ExpectedService(
                name=name,
                host_group=host,
                internal_port=port,
                container_name=entry.get("container_name") or name,
            )
        )
    return expected


# --------------------------------------------------------------------------
# Probe collection
# --------------------------------------------------------------------------


def _ssh_probe(host: str, *, ssh_user: str, ssh_key: str | None) -> dict[str, Any] | None:
    """Run topology_probe.py over SSH on `host` and return its JSON output.
    Returns None on any error.
    """
    probe_src = (REPO_ROOT / "scripts" / "topology_probe.py").read_text()
    cmd = ["ssh", "-o", "StrictHostKeyChecking=accept-new", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
    if ssh_key:
        cmd += ["-i", ssh_key]
    cmd += [f"{ssh_user}@{host}", "python3", "-"]
    try:
        proc = subprocess.run(
            cmd,
            input=probe_src,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def collect_probes(
    hosts: dict[str, str],
    *,
    ssh_user: str,
    ssh_key: str | None,
) -> dict[str, dict[str, Any] | None]:
    """Run the probe on each host. `hosts` maps host_group -> ssh_target.
    Returns host_group -> probe-or-None.
    """
    probes: dict[str, dict[str, Any] | None] = {}
    for group, target in hosts.items():
        probes[group] = _ssh_probe(target, ssh_user=ssh_user, ssh_key=ssh_key)
    return probes


# --------------------------------------------------------------------------
# Diff
# --------------------------------------------------------------------------


@dataclass
class DriftEntry:
    severity: str  # "missing" | "misplaced" | "unexpected" | "port_stranger"
    host: str
    service: str | None
    detail: str
    expected: dict[str, Any] | None = None
    observed: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "host": self.host,
            "service": self.service,
            "detail": self.detail,
            "expected": self.expected,
            "observed": self.observed,
        }


def _container_matches_service(container: dict[str, Any], svc: ExpectedService) -> bool:
    name = (container.get("name") or "").lower()
    if not name:
        return False
    expected_name = (svc.container_name or svc.name).lower()
    # container_name may be exact or have docker-compose suffix
    return name == expected_name or name.startswith(expected_name + "-") or name.startswith(expected_name + "_")


def _listening_has_port(listening: list[dict[str, Any]], port: int) -> bool:
    return any(int(e.get("port", -1)) == port for e in listening)


def diff(
    expected: dict[str, list[ExpectedService]],
    probes: dict[str, dict[str, Any] | None],
    *,
    all_known_services: set[str] | None = None,
) -> list[DriftEntry]:
    """Compare expected mapping against probe snapshots."""
    drifts: list[DriftEntry] = []

    # 1. Hosts that have an expected role but no probe data — report as
    # an INFO-level drift so operators see the gap.
    for host in expected:
        if host not in probes or probes[host] is None:
            drifts.append(
                DriftEntry(
                    severity="missing",
                    host=host,
                    service=None,
                    detail=f"No probe data for host {host!r} (SSH failed or probe error).",
                )
            )

    # 2. Per-host: missing / misplaced services.
    where_running: dict[str, set[str]] = {}  # service_name -> {host, ...}
    for host, probe in probes.items():
        if probe is None:
            continue
        containers = probe.get("containers") or []
        listening = probe.get("listening_tcp") or []
        for c in containers:
            cname = (c.get("name") or "").lower()
            if not cname:
                continue
            # Strip docker-compose suffixes for service-name inference.
            base = cname.split("-")[0] if "-" in cname else cname.split("_")[0] if "_" in cname else cname
            where_running.setdefault(base, set()).add(host)

        for svc in expected.get(host, []):
            container_present = any(_container_matches_service(c, svc) for c in containers)
            port_present = svc.internal_port is None or _listening_has_port(listening, svc.internal_port)
            if not container_present and not port_present:
                drifts.append(
                    DriftEntry(
                        severity="missing",
                        host=host,
                        service=svc.name,
                        detail=f"Expected {svc.name} on {host}: no container '{svc.container_name}' and no listener on port {svc.internal_port}.",
                        expected={"container": svc.container_name, "port": svc.internal_port},
                    )
                )
            elif not container_present and port_present:
                # Port present but no container by that name — could be a
                # rebrand/rename, worth flagging.
                drifts.append(
                    DriftEntry(
                        severity="missing",
                        host=host,
                        service=svc.name,
                        detail=f"Port {svc.internal_port} is listening on {host} but no container matches name '{svc.container_name}'.",
                        expected={"container": svc.container_name, "port": svc.internal_port},
                    )
                )

    # 3. Misplaced: a service is running on a host that is not the
    # expected host for it.
    for svc_name, hosts in where_running.items():
        # Find which hosts SHOULD run this service.
        expected_hosts = {
            host
            for host, svcs in expected.items()
            if any(s.name == svc_name or (s.container_name or "").lower().startswith(svc_name) for s in svcs)
        }
        if not expected_hosts:
            # Either an unrecognised service name, or a service that the
            # active profile doesn't enable. Don't report — that's the
            # job of the "unexpected" check below, gated by
            # all_known_services.
            continue
        wrong_hosts = hosts - expected_hosts
        for h in wrong_hosts:
            drifts.append(
                DriftEntry(
                    severity="misplaced",
                    host=h,
                    service=svc_name,
                    detail=f"Service {svc_name!r} is running on {h} but registry says it should run on {sorted(expected_hosts)!r}.",
                    expected={"hosts": sorted(expected_hosts)},
                    observed={"host": h},
                )
            )

    # 4. Unexpected: a container that doesn't correspond to any known
    # service in platform_service_registry. Skipped unless
    # all_known_services is provided.
    if all_known_services is not None:
        for host, probe in probes.items():
            if probe is None:
                continue
            for c in probe.get("containers") or []:
                cname = (c.get("name") or "").lower()
                if not cname:
                    continue
                base = cname.split("-")[0]
                if base not in all_known_services and cname not in all_known_services:
                    drifts.append(
                        DriftEntry(
                            severity="unexpected",
                            host=host,
                            service=None,
                            detail=f"Container {cname!r} on {host} does not match any registered service.",
                            observed={"container": cname, "image": c.get("image")},
                        )
                    )

    return drifts


# --------------------------------------------------------------------------
# Report writer
# --------------------------------------------------------------------------


def write_reports(
    *,
    deployment_slug: str,
    state_dir: Path,
    expected: dict[str, list[ExpectedService]],
    probes: dict[str, dict[str, Any] | None],
    drifts: list[DriftEntry],
) -> tuple[Path, Path]:
    state_dir.mkdir(parents=True, exist_ok=True)
    json_path = state_dir / "drift-report.json"
    md_path = state_dir / "drift-report.md"

    json_payload = {
        "schema": DRIFT_SCHEMA,
        "deployment": deployment_slug,
        "captured_at": _utc_now_iso(),
        "expected": {
            host: [{"name": s.name, "container": s.container_name, "port": s.internal_port} for s in svcs]
            for host, svcs in expected.items()
        },
        "probes": probes,
        "drifts": [d.to_dict() for d in drifts],
        "drift_count": len(drifts),
    }
    json_path.write_text(json.dumps(json_payload, indent=2, sort_keys=True) + "\n")

    md_lines = [
        f"# Topology Drift Report — {deployment_slug}",
        "",
        f"Captured at {json_payload['captured_at']}.",
        f"Drift count: **{len(drifts)}**.",
        "",
    ]
    if drifts:
        md_lines.append("## Drift entries")
        for d in drifts:
            md_lines.append(f"- **{d.severity}** — `{d.host}` `{d.service or '(any)'}`: {d.detail}")
        md_lines.append("")
    else:
        md_lines.append("_No drift detected. Reality matches the registry._")
    md_lines.append("")
    md_lines.append("## Expected services per host")
    for host, svcs in sorted(expected.items()):
        md_lines.append(f"- `{host}`:")
        for s in sorted(svcs, key=lambda x: x.name):
            md_lines.append(f"  - {s.name} (port={s.internal_port}, container={s.container_name})")
    md_path.write_text("\n".join(md_lines) + "\n")

    return json_path, md_path


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def _resolve_host_targets(
    expected: dict[str, list[ExpectedService]],
    repo_root: Path,
) -> dict[str, str]:
    """Resolve host_group names to SSH targets.

    For now, use the host_group name as the SSH alias; production runs
    via the existing Ansible inventory which has the proxmox jump host
    configured. Operators can override per-host via the
    PLATFORM_TOPOLOGY_SSH_TARGET_<HOST> env vars.
    """
    import os

    targets = {}
    for group in expected:
        env_key = f"PLATFORM_TOPOLOGY_SSH_TARGET_{group.upper().replace('-', '_')}"
        targets[group] = os.environ.get(env_key, group)
    return targets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--mode", choices=["plan", "reconcile"], default="reconcile")
    parser.add_argument("--deployment", default=None, help="Deployment slug (default: resolve from env/marker).")
    parser.add_argument(
        "--probe-input", default=None, help="Path to a JSON file mapping host -> probe snapshot. Skips SSH."
    )
    parser.add_argument("--ssh-user", default="ops", help="SSH user (default: ops).")
    parser.add_argument("--ssh-key", default=None, help="Path to SSH private key.")
    parser.add_argument(
        "--write-report",
        action="store_true",
        default=True,
        help="Write drift-report.{json,md} to deployment state/ (default).",
    )
    parser.add_argument(
        "--no-report", dest="write_report", action="store_false", help="Skip writing reports; print drift to stdout."
    )
    args = parser.parse_args(argv)

    try:
        slug = _dep_module.resolve_active_slug(args.deployment)
    except _dep_module.DeploymentNotResolvedError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    try:
        d = _dep_module.load(slug, validate=True)
    except _dep_module.DeploymentNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    service_registry = load_service_registry(REPO_ROOT)
    profile_catalog = load_profile_catalog(REPO_ROOT)

    enabled = _dep_module.resolve_enabled_services(
        d,
        profile_catalog=profile_catalog or None,
        service_registry=service_registry,
    )
    expected = build_expected(enabled, service_registry)

    if args.mode == "plan":
        print(
            json.dumps(
                {
                    "deployment": slug,
                    "enabled_count": len(enabled),
                    "expected": {
                        host: [{"name": s.name, "port": s.internal_port, "container": s.container_name} for s in svcs]
                        for host, svcs in expected.items()
                    },
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    # reconcile mode
    probes: dict[str, dict[str, Any] | None]
    if args.probe_input:
        probes = json.loads(Path(args.probe_input).read_text())
    else:
        targets = _resolve_host_targets(expected, REPO_ROOT)
        probes = collect_probes(targets, ssh_user=args.ssh_user, ssh_key=args.ssh_key)

    all_known = {name for name in service_registry}
    drifts = diff(expected, probes, all_known_services=all_known)

    if args.write_report:
        json_path, md_path = write_reports(
            deployment_slug=slug,
            state_dir=d.state_dir,
            expected=expected,
            probes=probes,
            drifts=drifts,
        )
        print(f"Wrote {json_path}")
        print(f"Wrote {md_path}")
    else:
        for drift in drifts:
            print(f"  [{drift.severity}] {drift.host} {drift.service or ''}: {drift.detail}")
        if not drifts:
            print("No drift detected.")

    return 0 if not drifts else 1


if __name__ == "__main__":
    raise SystemExit(main())
