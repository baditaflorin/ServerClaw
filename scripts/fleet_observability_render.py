#!/usr/bin/env python3
"""Render what the fleet-observability roles would write, offline, and compare it with a live host (read-only).

The lv3.platform.fleet_* roles are driven by inventory/fleet-observability.yml. This script loads that inventory with
the role defaults, renders the same Jinja templates with an Ansible-compatible environment (trim_blocks, strict
undefined) and prints or diffs the result. It never changes anything:

  render      write the rendered files of one host under a directory (nothing is sent to the host)
  diff-live   fetch the live counterpart of every rendered artifact over SSH with read-only commands and print a diff

Usage:
  python3 scripts/fleet_observability_render.py list
  python3 scripts/fleet_observability_render.py render 0own_github_mirror --out /tmp/rendered
  python3 scripts/fleet_observability_render.py diff-live 0own_github_mirror

diff-live uses the operator's SSH aliases (ssh-fleet-sync/00-fleet.conf) and an allow-list of read-only remote commands
(cat, stat, ls, grep, tailscale status/prefs, pvesh get, proxmox-backup-manager ... list). It needs a single host name:
there is deliberately no "all hosts" mode. Secret files are only stat-ed, never read.
"""

from __future__ import annotations

import argparse
import difflib
import json
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jinja2
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
ROLES_ROOT = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles"
INVENTORY_PATH = REPO_ROOT / "inventory" / "fleet-observability.yml"

ROLE_BY_GROUP = {
    "fleet_node_exporter_hosts": "fleet_node_exporter",
    "fleet_tailscale_node_hosts": "fleet_tailscale_node",
    "fleet_guest_firewall_hosts": "fleet_guest_firewall",
    "fleet_pg_backup_hosts": "fleet_pg_backup",
    "fleet_docker_prune_hosts": "fleet_docker_prune",
}

# Remote commands diff-live may run. Everything else is refused.
READ_ONLY_PREFIXES = (
    "cat ",
    "sudo -n cat ",
    "stat ",
    "sudo -n stat ",
    "grep ",
    "sudo -n grep ",
    "systemctl is-active ",
    "systemctl is-enabled ",
    "tailscale debug prefs",
    "tailscale serve status --json",
    "pvesh get ",
    "proxmox-backup-manager user list",
    "proxmox-backup-manager acl list",
    "proxmox-backup-manager prune-job list",
)


class _Loader(yaml.SafeLoader):
    """SafeLoader that understands Ansible's !unsafe tag (kept as a plain string)."""


_Loader.add_constructor("!unsafe", lambda loader, node: loader.construct_scalar(node))


def load_yaml(path: Path) -> Any:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=_Loader)  # noqa: S506 - SafeLoader subclass


def load_inventory(path: Path = INVENTORY_PATH) -> dict[str, Any]:
    return load_yaml(path)["all"]


def _walk_groups(node: dict[str, Any], name: str, groups: dict[str, set[str]], hostvars: dict[str, dict[str, Any]]) -> None:
    members = groups.setdefault(name, set())
    for host, vars_ in (node.get("hosts") or {}).items():
        members.add(host)
        hostvars.setdefault(host, {}).update(vars_ or {})
    for child_name, child in (node.get("children") or {}).items():
        _walk_groups(child or {}, child_name, groups, hostvars)
        members.update(groups[child_name])


def inventory_model(inventory: dict[str, Any] | None = None) -> tuple[dict[str, set[str]], dict[str, dict[str, Any]], dict[str, Any]]:
    inventory = inventory or load_inventory()
    groups: dict[str, set[str]] = {}
    hostvars: dict[str, dict[str, Any]] = {}
    _walk_groups(inventory, "all", groups, hostvars)
    return groups, hostvars, inventory.get("vars") or {}


def role_defaults(role: str) -> dict[str, Any]:
    return load_yaml(ROLES_ROOT / role / "defaults" / "main.yml") or {}


def _to_bool(value: Any) -> bool:
    return value if isinstance(value, bool) else str(value).strip().lower() in {"1", "true", "yes", "on"}


def make_environment(template_dir: Path) -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_dir)),
        trim_blocks=True,
        keep_trailing_newline=True,
        undefined=jinja2.StrictUndefined,
    )
    env.filters["bool"] = _to_bool
    return env


@dataclass
class Artifact:
    host: str
    role: str
    path: str
    kind: str  # file | line | dir | state
    content: str = ""
    mode: str = ""
    owner: str = ""
    group: str = ""
    secret_reference: bool = False
    state: Any = None
    note: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def _context(role: str, host_vars: dict[str, Any], all_vars: dict[str, Any]) -> dict[str, Any]:
    context = dict(role_defaults(role))
    context.update(all_vars)
    context.update({key: value for key, value in host_vars.items() if key.startswith("fleet_")})
    return context


def _render(role: str, template: str, context: dict[str, Any], item: dict[str, Any] | None = None) -> str:
    env = make_environment(ROLES_ROOT / role / "templates")
    variables = dict(context)
    if item is not None:
        variables["item"] = item
    return env.get_template(template).render(**variables)


def exporter_artifacts(host: str, context: dict[str, Any]) -> list[Artifact]:
    role = "fleet_node_exporter"
    artifacts: list[Artifact] = []
    if context["fleet_node_exporter_textfile_dir"]:
        artifacts.append(
            Artifact(
                host,
                role,
                context["fleet_node_exporter_textfile_dir"],
                "dir",
                mode=context["fleet_node_exporter_textfile_mode"].lstrip("0") or "0",
                owner=context["fleet_node_exporter_textfile_owner"],
                group=context["fleet_node_exporter_textfile_group"],
            )
        )
    line = _render(role, "node-exporter-args.j2", context).strip()
    artifacts.append(Artifact(host, role, context["fleet_node_exporter_defaults_file"], "line", content=line + "\n"))
    if context["fleet_node_exporter_restart_forever"]:
        artifacts.append(
            Artifact(
                host,
                role,
                f"{context['fleet_node_exporter_unit_dir']}/{context['fleet_node_exporter_service']}.service.d/10-retry-until-tailnet.conf",
                "file",
                content=_render(role, "node-exporter-restart.conf.j2", context),
                mode="644",
                owner="root",
                group="root",
            )
        )
    for proxy in context["fleet_node_exporter_socket_proxies"]:
        if proxy.get("state") == "disabled":
            artifacts.append(
                Artifact(
                    host,
                    role,
                    f"systemd unit {proxy['name']}.socket",
                    "state",
                    state={"enabled": "disabled", "active": "inactive"},
                    note=f"stale socket kept stopped and disabled (would listen on {proxy['listen_address']}:{proxy['listen_port']})",
                )
            )
            continue
        if proxy.get("state") != "present":
            artifacts.append(
                Artifact(
                    host,
                    role,
                    f"{context['fleet_node_exporter_unit_dir']}/{proxy['name']}.socket",
                    "state",
                    state={"unmanaged": True, "listens": f"{proxy['listen_address']}:{proxy['listen_port']}"},
                    note=str(proxy.get("unmanaged_reason", "")).strip(),
                )
            )
            continue
        for suffix, template in (("socket", "metrics-proxy.socket.j2"), ("service", "metrics-proxy.service.j2")):
            artifacts.append(
                Artifact(
                    host,
                    role,
                    f"{context['fleet_node_exporter_unit_dir']}/{proxy['name']}.{suffix}",
                    "file",
                    content=_render(role, template, context, proxy),
                    mode="644",
                    owner="root",
                    group="root",
                )
            )
    for forward in context["fleet_node_exporter_tailscale_serve_tcp"]:
        artifacts.append(
            Artifact(host, role, f"tailscale serve tcp {forward['port']}", "state", state={"TCPForward": forward["target"]})
        )
    return artifacts


def firewall_artifacts(host: str, context: dict[str, Any]) -> list[Artifact]:
    role = "fleet_guest_firewall"
    return [
        Artifact(
            host,
            role,
            context["fleet_guest_firewall_config_file"],
            "file",
            content=_render(role, "nftables.conf.j2", context),
            mode="644",
            owner="root",
            group="root",
        )
    ]


def tailscale_artifacts(host: str, context: dict[str, Any]) -> list[Artifact]:
    return [
        Artifact(
            host,
            "fleet_tailscale_node",
            "tailscale AdvertiseRoutes",
            "state",
            state=sorted(context["fleet_tailscale_node_advertise_routes"]),
        )
    ]


def docker_prune_artifacts(host: str, context: dict[str, Any]) -> list[Artifact]:
    role = "fleet_docker_prune"
    unit = context["fleet_docker_prune_unit_name"]
    files = [
        (context["fleet_docker_prune_script_path"], "fleet-docker-prune.sh.j2", "755"),
        (f"/etc/systemd/system/{unit}.service", "fleet-docker-prune.service.j2", "644"),
        (f"/etc/systemd/system/{unit}.timer", "fleet-docker-prune.timer.j2", "644"),
    ]
    return [
        Artifact(host, role, path, "file", content=_render(role, template, context), mode=mode, owner="root", group="root")
        for path, template, mode in files
    ]


def pg_backup_artifacts(host: str, context: dict[str, Any]) -> list[Artifact]:
    role = "fleet_pg_backup"
    components = context["fleet_pg_backup_components"]
    artifacts: list[Artifact] = []
    if "pve_backup" in components:
        artifacts.append(
            Artifact(
                host,
                role,
                context["fleet_pg_backup_hook_path"],
                "file",
                content=_render(role, "vzdump-pg-metrics-hook.j2", context),
                mode="755",
                owner="root",
                group="root",
            )
        )
        storage = context["fleet_pg_backup_pve_storage"]
        artifacts.append(
            Artifact(host, role, storage["password_file"], "file", secret_reference=True, mode="600", owner="root", group="www-data")
        )
        artifacts.append(
            Artifact(
                host,
                role,
                f"pvesh /storage/{storage['id']}",
                "state",
                state={
                    key: storage[key]
                    for key in ("server", "datastore", "namespace", "username", "fingerprint", "content")
                },
            )
        )
        for job in context["fleet_pg_backup_pve_jobs"]:
            artifacts.append(
                Artifact(
                    host,
                    role,
                    f"pvesh /cluster/backup/{job['id']}",
                    "state",
                    state={
                        "vmid": str(job["vmid"]),
                        "storage": job["storage"],
                        "mode": job["mode"],
                        "schedule": job["schedule"],
                        "bwlimit": job["bwlimit"],
                        "compress": job["compress"],
                        "script": job["script"],
                        "notes-template": job["notes_template"],
                        "comment": job["comment"],
                        "enabled": 1 if _to_bool(job["enabled"]) else 0,
                    },
                )
            )
    if "pgbackrest" in components:
        conf_dir = context["fleet_pg_backup_pgbackrest_conf_dir"]
        user, group = context["fleet_pg_backup_pgbackrest_user"], context["fleet_pg_backup_pgbackrest_group"]
        prepared = context["fleet_pg_backup_pgbackrest_prepared_dir"]
        artifacts += [
            Artifact(host, role, f"{conf_dir}/pgbackrest.conf", "file", content=_render(role, "pgbackrest.conf.j2", context), mode="640", owner=user, group=group),
            Artifact(host, role, f"{conf_dir}/{context['fleet_pg_backup_pgbackrest_cipher_file']}", "file", secret_reference=True, mode="600", owner=user, group=group),
            Artifact(host, role, context["fleet_pg_backup_pgbackrest_wrapper_path"], "file", content=_render(role, "pgbackrest-daily.j2", context), mode="755", owner="root", group="root"),
            Artifact(host, role, f"{prepared}/pgbackrest-daily.service", "file", content=_render(role, "pgbackrest-daily.service.j2", context), mode="644", owner="root", group="root"),
            Artifact(host, role, f"{prepared}/pgbackrest-daily.timer", "file", content=_render(role, "pgbackrest-daily.timer.j2", context), mode="644", owner="root", group="root"),
            Artifact(host, role, f"{prepared}/RUNBOOK.txt", "file", content=(ROLES_ROOT / role / "files" / "pgbackrest-RUNBOOK.txt").read_text(encoding="utf-8"), mode="644", owner="root", group="root"),
        ]
    if "pbs_server" in components:
        user_id = context["fleet_pg_backup_pbs_user"]["id"]
        artifacts.append(Artifact(host, role, f"pbs user {user_id}", "state", state={"enable": True, "comment": context["fleet_pg_backup_pbs_user"]["comment"]}))
        artifacts.append(
            Artifact(
                host,
                role,
                "pbs acl entries",
                "state",
                state=sorted(f"{acl['path']} {acl['role']} {acl['auth_id']}" for acl in context["fleet_pg_backup_pbs_acls"]),
            )
        )
        for job in context["fleet_pg_backup_pbs_prune_jobs"]:
            artifacts.append(
                Artifact(
                    host,
                    role,
                    f"pbs prune-job {job['id']}",
                    "state",
                    state={
                        "store": job["store"],
                        "schedule": job["schedule"],
                        "keep-last": job["keep_last"],
                        "keep-weekly": job["keep_weekly"],
                        "comment": job["comment"],
                        **({"ns": job["ns"]} if job.get("ns") else {}),
                        **{key.replace("_", "-"): job[key] for key in ("keep_daily", "keep_monthly", "max_depth") if key in job},
                    },
                )
            )
    return artifacts


BUILDERS = {
    "fleet_node_exporter": exporter_artifacts,
    "fleet_tailscale_node": tailscale_artifacts,
    "fleet_guest_firewall": firewall_artifacts,
    "fleet_pg_backup": pg_backup_artifacts,
    "fleet_docker_prune": docker_prune_artifacts,
}


def render_host(host: str, inventory: dict[str, Any] | None = None) -> list[Artifact]:
    groups, hostvars, all_vars = inventory_model(inventory)
    if host not in hostvars:
        raise SystemExit(f"unknown host {host}; run `list` to see the inventory")
    artifacts: list[Artifact] = []
    for group, role in ROLE_BY_GROUP.items():
        if host in groups.get(group, set()):
            artifacts += BUILDERS[role](host, _context(role, hostvars[host], all_vars))
    return artifacts


# ----------------------------------------------------------------------------- live comparison


def _ssh(host: str, command: str, *, become: bool) -> subprocess.CompletedProcess[str]:
    if become and not command.startswith("sudo "):
        command = "sudo -n " + command
    if not command.startswith(READ_ONLY_PREFIXES):
        raise RuntimeError(f"refusing non read-only command: {command}")
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", host, command],
        text=True,
        capture_output=True,
        check=False,
    )


def _unified(live: str, rendered: str, name: str) -> list[str]:
    return list(
        difflib.unified_diff(
            live.splitlines(keepends=True),
            rendered.splitlines(keepends=True),
            fromfile=f"live:{name}",
            tofile=f"rendered:{name}",
        )
    )


def _live_state(host: str, artifact: Artifact, become: bool) -> Any:
    path = artifact.path
    if path == "tailscale AdvertiseRoutes":
        result = _ssh(host, "tailscale debug prefs", become=False)
        return sorted(json.loads(result.stdout).get("AdvertiseRoutes") or [])
    if path.startswith("tailscale serve tcp "):
        port = path.rsplit(" ", 1)[1]
        result = _ssh(host, "tailscale serve status --json", become=False)
        return {"TCPForward": ((json.loads(result.stdout or "{}").get("TCP") or {}).get(port) or {}).get("TCPForward")}
    if path.startswith("systemd unit "):
        name = path.split(" ", 2)[2]
        return {
            "enabled": _ssh(host, f"systemctl is-enabled {name}", become=become).stdout.strip(),
            "active": _ssh(host, f"systemctl is-active {name}", become=become).stdout.strip(),
        }
    if path.startswith("pvesh "):
        result = _ssh(host, f"pvesh get {path.split(' ', 1)[1]} --output-format json", become=False)
        live = json.loads(result.stdout) if result.returncode == 0 else {}
        return {key: live.get(key) for key in (artifact.state or {})}
    if path.startswith("pbs user "):
        users = json.loads(_ssh(host, "proxmox-backup-manager user list --output-format json", become=False).stdout)
        match = next((u for u in users if u["userid"] == path.split(" ", 2)[2]), {})
        return {"enable": bool(match.get("enable", False)), "comment": match.get("comment")}
    if path == "pbs acl entries":
        acls = json.loads(_ssh(host, "proxmox-backup-manager acl list --output-format json", become=False).stdout)
        wanted = {entry.rsplit(" ", 1)[1] for entry in artifact.state}
        return sorted(f"{a['path']} {a['roleid']} {a['ugid']}" for a in acls if a["ugid"] in wanted and a["path"].startswith("/datastore/own-pbs/0database"))
    if path.startswith("pbs prune-job "):
        jobs = json.loads(_ssh(host, "proxmox-backup-manager prune-job list --output-format json", become=False).stdout)
        match = next((j for j in jobs if j["id"] == path.rsplit(" ", 1)[1]), {})
        return {key: match.get(key) for key in (artifact.state or {})}
    if artifact.state and artifact.state.get("unmanaged"):
        unit = _ssh(host, f"cat {path}", become=become)
        listens = unit.stdout.split("ListenStream=")[1].split()[0] if "ListenStream=" in unit.stdout else None
        name = Path(path).name
        active = _ssh(host, f"systemctl is-active {name}", become=become).stdout.strip()
        enabled = _ssh(host, f"systemctl is-enabled {name}", become=become).stdout.strip()
        return {"unmanaged": True, "listens": listens, "_live_only": f"active={active} enabled={enabled}"}
    return None


def diff_live(host: str) -> int:
    groups, hostvars, _ = inventory_model()
    become = bool(hostvars[host].get("ansible_become"))
    differences = 0
    for artifact in render_host(host):
        label = f"[{artifact.role}] {artifact.path}"
        if artifact.kind == "dir":
            result = _ssh(host, f"stat -c '%U:%G %a' {shlex.quote(artifact.path)}", become=become)
            live = result.stdout.strip() if result.returncode == 0 else "missing"
            wanted = f"{artifact.owner}:{artifact.group} {artifact.mode}"
            same = live == wanted
            print(("OK    " if same else "DIFF  ") + f"{label} live={live} rendered={wanted}")
            differences += 0 if same else 1
        elif artifact.secret_reference:
            result = _ssh(host, f"stat -c '%U:%G %a' {shlex.quote(artifact.path)}", become=become)
            live = result.stdout.strip() if result.returncode == 0 else "missing"
            wanted = f"{artifact.owner}:{artifact.group} {artifact.mode}"
            same = live == wanted
            print(("OK    " if same else "DIFF  ") + f"{label} (secret file, only stat-ed) live={live} expected={wanted}")
            differences += 0 if same else 1
        elif artifact.kind == "line":
            result = _ssh(host, f"grep -E '^ARGS=' {shlex.quote(artifact.path)}", become=become)
            live = result.stdout
            lines = _unified(live, artifact.content, artifact.path)
            print(("OK    " if not lines else "DIFF  ") + label)
            sys.stdout.writelines(lines)
            differences += 1 if lines else 0
        elif artifact.kind == "file":
            result = _ssh(host, f"cat {shlex.quote(artifact.path)}", become=become)
            live = result.stdout if result.returncode == 0 else ""
            lines = _unified(live, artifact.content, artifact.path)
            mode = _ssh(host, f"stat -c '%U:%G %a' {shlex.quote(artifact.path)}", become=become).stdout.strip() or "missing"
            wanted = f"{artifact.owner}:{artifact.group} {artifact.mode}"
            same = not lines and mode == wanted
            print(("OK    " if same else "DIFF  ") + f"{label} live-owner-mode={mode} rendered={wanted}")
            sys.stdout.writelines(lines)
            differences += 0 if same else 1
        else:
            live = _live_state(host, artifact, become)
            wanted = artifact.state
            if isinstance(live, dict) and "_live_only" in live:
                info = live.pop("_live_only")
                print(f"NOTE  {label} (unmanaged, not touched) {info} {artifact.note}")
            same = live == wanted if live is not None else None
            if same is None:
                print(f"NOTE  {label} {wanted} {artifact.note}")
            else:
                print(("OK    " if same else "DIFF  ") + f"{label}")
                if not same:
                    print(f"      live    = {json.dumps(live, sort_keys=True)}")
                    print(f"      rendered= {json.dumps(wanted, sort_keys=True)}")
                    differences += 1
    return differences


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list the inventory hosts and the roles that apply to each")
    render_parser = sub.add_parser("render", help="write the rendered files of one host to a directory")
    render_parser.add_argument("host")
    render_parser.add_argument("--out", type=Path, required=True)
    diff_parser = sub.add_parser("diff-live", help="diff the rendered artifacts of ONE host against the live host (read-only)")
    diff_parser.add_argument("host")
    args = parser.parse_args(argv)

    if args.command == "list":
        groups, hostvars, _ = inventory_model()
        for host in sorted(hostvars):
            roles = [role for group, role in ROLE_BY_GROUP.items() if host in groups.get(group, set())]
            print(f"{host:26s} {', '.join(roles) or '(inventory seed only)'}")
        return 0
    if args.command == "render":
        for artifact in render_host(args.host):
            if artifact.kind in {"file", "line"} and not artifact.secret_reference:
                target = args.out / args.host / artifact.path.lstrip("/")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(artifact.content, encoding="utf-8")
                print(target)
        return 0
    differences = diff_live(args.host)
    print(f"\n{differences} artifact(s) differ from the live host")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
