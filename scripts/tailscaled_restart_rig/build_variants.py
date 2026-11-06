#!/usr/bin/env python3
"""Build the unit trees that the tailscaled-restart rig boots. Renders the real role templates; touches no host.

The rig (run.sh) boots each tree in a throwaway systemd container whose "tailscaled" behaves like the real one did on the 0mcp hypervisor on 2026-11-02
(it reports "started" at once, creates tailscale0 50 ms later and gives it the tailnet address 0.8 s after that), then restarts it the ways a real one
restarts and reports which proxy sockets stay dead. The variants are an ablation of the fix, so each part is shown to be needed:

  role-none        the sockets as the repo rendered them before the fix (no FreeBind, nothing starts them when tailscale0 returns)
  role-freebind    FreeBind=true only
  role-wants       the tailscale0 device drop-in (Wants=) only
  role-fix         both: what a fresh converge of the role plus the hostconf device drop-in gives
  hostconf-fix     the live layout of the 0mcp hypervisor: the OLD main unit files plus the hostconf drop-ins (10-no-default-deps, 20-free-bind, device Wants=)

The 0docker hypervisor (systemd 252) has its own family, an ablation on top of what is live there today (PR 659 applied: the tailscale0 device Wants= woodpecker-exec-proxy@9000.socket). The units are the ones
read from the host (0docker-units/ for the hand-installed template, the role template for the node-exporter proxy), the drop-ins are the real hostconf files, the address is the 0docker tailnet address:

  docker0-live       what is on the hypervisor now: no FreeBind on the template, nothing Wants the node-exporter proxy. Must still lose sockets (the exposure this family exists for)
  docker0-freebind   live + the FreeBind drop-in of woodpecker-exec-proxy@.socket only
  docker0-wants      live + the device Wants= of zdocker-hypervisor-metrics-proxy.socket only
  docker0-fix        live + both: the 0docker hostconf entries of this change

Usage: python3 scripts/tailscaled_restart_rig/build_variants.py --out DIR
"""

from __future__ import annotations

import argparse
import re
import shutil
import stat
import sys
from pathlib import Path

import jinja2

REPO = Path(__file__).resolve().parents[2]
ROLES = REPO / "collections" / "ansible_collections" / "lv3" / "platform" / "roles"
HOSTCONF_FILES = REPO / "config" / "hostconf" / "files"
TAILNET_ADDRESS = "100.64.0.6"

# The proxies the rig models: three of the nineteen lv3 sockets (BindToDevice=tailscale0) and the two node-exporter proxies (no BindToDevice).
LV3 = [
    {
        "name": "openbao",
        "listen_address": TAILNET_ADDRESS,
        "listen_port": 8200,
        "upstream_host": "127.0.0.1",
        "upstream_port": 9,
    },
    {
        "name": "postgres",
        "listen_address": TAILNET_ADDRESS,
        "listen_port": 5432,
        "upstream_host": "127.0.0.1",
        "upstream_port": 9,
    },
    {
        "name": "gitea",
        "listen_address": TAILNET_ADDRESS,
        "listen_port": 3009,
        "upstream_host": "127.0.0.1",
        "upstream_port": 9,
    },
]
METRICS = [
    # zmcp-runtime-general-metrics-proxy has no free_bind in inventory/fleet-observability.yml before the fix; the build-metrics proxy has had it since 2026-10-12
    {
        "name": "zmcp-runtime-general-metrics-proxy",
        "listen_address": TAILNET_ADDRESS,
        "listen_port": 9101,
        "upstream": "127.0.0.1:9",
        "free_bind": False,
        "socket_description": "rig node-exporter proxy A",
        "service_description": "rig node-exporter proxy A",
    },
    {
        "name": "woodpecker-0exec-build-metrics-proxy",
        "listen_address": TAILNET_ADDRESS,
        "listen_port": 9103,
        "upstream": "127.0.0.1:9",
        "free_bind": True,
        "socket_description": "rig node-exporter proxy B",
        "service_description": "rig node-exporter proxy B",
    },
]
VARIANTS = ["role-none", "role-freebind", "role-wants", "role-fix", "hostconf-fix"]

# The 0docker hypervisor. DOCKER0_METRICS is its node-exporter proxy as inventory/fleet-observability.yml declares it (tests/test_tailscaled_restart_0docker.py keeps the two equal).
DOCKER0_ADDRESS = "100.64.0.5"
DOCKER0_UNITS = Path(__file__).resolve().parent / "0docker-units"
DOCKER0_WOODPECKER_INSTANCE = "woodpecker-exec-proxy@9000"
DOCKER0_METRICS = {
    "name": "zdocker-hypervisor-metrics-proxy",
    "listen_address": DOCKER0_ADDRESS,
    "listen_port": 9100,
    "upstream": "10.10.10.1:9100",
    "free_bind": True,
    "socket_description": "Tailscale-only node-exporter proxy for 0docker hypervisor (10.10.10.1:9100)",
    "service_description": "Forward 0docker hypervisor node-exporter over Tailscale only",
}
DOCKER0_VARIANTS = ["docker0-live", "docker0-freebind", "docker0-wants", "docker0-fix"]

FAKE_TAILSCALED_UNIT = """[Unit]
Description=Stand-in for tailscaled (tailscaled-restart rig)
Wants=network-pre.target
After=network-pre.target

[Service]
Type=notify
NotifyAccess=all
ExecStart=/usr/local/bin/fake-tailscaled
ExecStopPost=/bin/sh -c 'ip link del tailscale0 2>/dev/null; true'
Restart=on-failure

[Install]
WantedBy=multi-user.target
"""


def fake_tailscaled(address: str) -> str:
    return (
        """#!/bin/sh
# Timing of the real tailscaled on the 0mcp hypervisor, restart of 2026-11-02 12:33:31 (journal): "Started tailscaled.service" at +0.00 s, "Creating
# WireGuard device" at +0.01 s, the tailnet address on tailscale0 (peerapi serving on it) at about +0.8 s. The device goes away when the process exits.
# The 0docker hypervisor's start of 12:34:59 was faster (device +0.004 s, address +0.31 s); the slower timing is kept for both, it is the harder case.
systemd-notify --ready
sleep 0.05
ip link add tailscale0 type dummy
ip link set tailscale0 up
sleep 0.75
ip addr add %s/32 dev tailscale0
exec sleep infinity
"""
        % address
    )


FAKE_TAILSCALED = fake_tailscaled(TAILNET_ADDRESS)

SETTLE = """#!/bin/sh
# rig-settle MAX_SECONDS: poll the modelled sockets until all are active (prints "ok after N ms", plus the ones found down at the first look) or MAX_SECONDS pass (prints "DEAD name ... after N ms").
max=${1:-12}
start=$(date +%s%N)
limit=$((start + max * 1000000000))
while :; do
  dead=""
  for u in $(cat /etc/rig-sockets); do
    [ "$(systemctl is-active "$u")" = active ] || dead="$dead ${u%.socket}"
  done
  now=$(date +%s%N)
  ms=$(( (now - start) / 1000000 ))
  [ -n "${first+x}" ] || first=$dead
  if [ -z "$dead" ]; then
    if [ -n "$first" ]; then echo "ok after ${ms} ms (were down:$first)"; else echo "ok after ${ms} ms"; fi
    exit 0
  fi
  if [ "$now" -gt "$limit" ]; then echo "DEAD$dead after ${ms} ms"; exit 1; fi
  sleep 0.2
done
"""


def environment(*role_names: str) -> jinja2.Environment:
    """The Ansible template settings the repo tests use (trim_blocks, strict undefined)."""
    loader = jinja2.FileSystemLoader([str(ROLES / name / "templates") for name in role_names])
    env = jinja2.Environment(
        loader=loader, trim_blocks=True, keep_trailing_newline=True, undefined=jinja2.StrictUndefined
    )
    env.filters["bool"] = lambda value: (
        value if isinstance(value, bool) else str(value).strip().lower() in ("1", "true", "yes", "on")
    )  # Ansible's bool filter
    return env


def write(path: Path, text: str, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(path.stat().st_mode | (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH if executable else 0))


def link(path: Path, target: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or path.exists():
        path.unlink()
    path.symlink_to(target)


def legacy(socket_text: str) -> str:
    """The socket unit as it still is on the hypervisor: rendered before the 2026-10-13 and 2026-11-02 changes (no DefaultDependencies block, no FreeBind)."""
    text = re.sub(
        r"^(FreeBind=true|DefaultDependencies=no|Conflicts=shutdown\.target|Before=shutdown\.target)\n",
        "",
        socket_text,
        flags=re.M,
    )
    assert "FreeBind" not in text and "DefaultDependencies" not in text
    return text


def build(out: Path) -> None:
    lv3_env = environment("proxmox_tailscale_proxy")
    metrics_env = environment("fleet_node_exporter")
    shutil.rmtree(out, ignore_errors=True)
    for variant in VARIANTS:
        root = out / variant
        unit_dir = root / "etc" / "systemd" / "system"
        sockets: list[str] = []
        stand_in_tailscaled(root, TAILNET_ADDRESS)
        free_bind_in_main = variant in ("role-freebind", "role-fix")

        for item in LV3:
            unit = f"lv3-tailscale-proxy-{item['name']}"
            socket_text = lv3_env.get_template("lv3-tailscale-proxy.socket.j2").render(item=item)
            assert "FreeBind=true" in socket_text, "the role template no longer renders FreeBind=true"
            if variant == "hostconf-fix":
                socket_text = legacy(socket_text)
            elif not free_bind_in_main:
                socket_text = socket_text.replace("FreeBind=true\n", "")
            write(unit_dir / f"{unit}.socket", socket_text)
            write(
                unit_dir / f"{unit}.service", lv3_env.get_template("lv3-tailscale-proxy.service.j2").render(item=item)
            )
            link(unit_dir / "sockets.target.wants" / f"{unit}.socket", f"/etc/systemd/system/{unit}.socket")
            link(unit_dir / "tailscaled.service.wants" / f"{unit}.socket", f"/etc/systemd/system/{unit}.socket")
            sockets.append(f"{unit}.socket")
            if variant == "hostconf-fix":
                shutil.copy(
                    HOSTCONF_FILES / "socket-no-default-deps.0mcp.conf",
                    _dropin(unit_dir, f"{unit}.socket", "10-no-default-deps.conf"),
                )
                shutil.copy(
                    HOSTCONF_FILES / "socket-free-bind.0mcp.conf",
                    _dropin(unit_dir, f"{unit}.socket", "20-free-bind.conf"),
                )

        for item in METRICS:
            unit = item["name"]
            context = {"fleet_node_exporter_proxyd_path": "/usr/lib/systemd/systemd-socket-proxyd"}
            proxy = dict(item)
            if variant in ("role-freebind", "role-fix") and unit.startswith("zmcp"):
                proxy["free_bind"] = True  # the inventory change of the fix
            socket_text = metrics_env.get_template("metrics-proxy.socket.j2").render(item=proxy, **context)
            if variant == "hostconf-fix":
                socket_text = (
                    legacy(socket_text)
                    if not item["free_bind"]
                    else socket_text.replace(
                        "DefaultDependencies=no\nConflicts=shutdown.target\nBefore=shutdown.target\n", ""
                    )
                )
            write(unit_dir / f"{unit}.socket", socket_text)
            write(
                unit_dir / f"{unit}.service",
                metrics_env.get_template("metrics-proxy.service.j2").render(item=proxy, **context),
            )
            link(unit_dir / "sockets.target.wants" / f"{unit}.socket", f"/etc/systemd/system/{unit}.socket")
            sockets.append(f"{unit}.socket")
            if variant == "hostconf-fix":
                shutil.copy(
                    HOSTCONF_FILES / "socket-no-default-deps.0mcp.conf",
                    _dropin(unit_dir, f"{unit}.socket", "10-no-default-deps.conf"),
                )
                if unit.startswith("zmcp"):
                    shutil.copy(
                        HOSTCONF_FILES / "socket-free-bind.0mcp.conf",
                        _dropin(unit_dir, f"{unit}.socket", "20-free-bind.conf"),
                    )

        if variant in ("role-wants", "role-fix", "hostconf-fix"):
            device_dir = unit_dir / "sys-subsystem-net-devices-tailscale0.device.d"
            device_dir.mkdir(parents=True, exist_ok=True)
            # the file the hypervisor gets, unmodified: it names all nineteen sockets, the rig loads three (systemd ignores a Wants= on a unit it does not have)
            shutil.copy(
                HOSTCONF_FILES / "tailscale0-wants-lv3-proxies.0mcp.conf",
                device_dir / "10-wants-lv3-tailscale-proxies.conf",
            )
        write(root / "etc" / "rig-sockets", "\n".join(sockets) + "\n")
        write(root / "etc" / "rig-operator-socket", "lv3-tailscale-proxy-gitea.socket\n")
        print(f"built {variant}: {len(sockets)} sockets", file=sys.stderr)
    build_docker0(out)


def stand_in_tailscaled(root: Path, address: str) -> None:
    """The stand-in tailscaled (ready first, device 50 ms later, address 0.75 s after that), the settle helper and the boot symlink: the same for every family."""
    unit_dir = root / "etc" / "systemd" / "system"
    write(unit_dir / "tailscaled.service", FAKE_TAILSCALED_UNIT)
    write(root / "usr" / "local" / "bin" / "fake-tailscaled", fake_tailscaled(address), executable=True)
    write(root / "usr" / "local" / "bin" / "rig-settle", SETTLE, executable=True)
    link(unit_dir / "multi-user.target.wants" / "tailscaled.service", "/etc/systemd/system/tailscaled.service")


def build_docker0(out: Path) -> None:
    """The 0docker family: the units as they are on the hypervisor (legacy: no DefaultDependencies in the unit text) plus the real hostconf drop-ins of the variant."""
    metrics_env = environment("fleet_node_exporter")
    context = {"fleet_node_exporter_proxyd_path": "/usr/lib/systemd/systemd-socket-proxyd"}
    for variant in DOCKER0_VARIANTS:
        root = out / variant
        unit_dir = root / "etc" / "systemd" / "system"
        stand_in_tailscaled(root, DOCKER0_ADDRESS)
        # hand-installed template, verbatim from the host: BindToDevice=tailscale0, no FreeBind (the exposure)
        template = DOCKER0_UNITS / "woodpecker-exec-proxy@.socket"
        assert "BindToDevice=tailscale0" in template.read_text(encoding="utf-8")
        shutil.copy(template, unit_dir / "woodpecker-exec-proxy@.socket")
        shutil.copy(DOCKER0_UNITS / "woodpecker-exec-proxy@.service", unit_dir / "woodpecker-exec-proxy@.service")
        link(
            unit_dir / "sockets.target.wants" / f"{DOCKER0_WOODPECKER_INSTANCE}.socket",
            "/etc/systemd/system/woodpecker-exec-proxy@.socket",
        )
        shutil.copy(
            HOSTCONF_FILES / "socket-no-default-deps.0docker.conf",
            _dropin(unit_dir, "woodpecker-exec-proxy@.socket", "10-no-default-deps.conf"),
        )
        if variant in ("docker0-freebind", "docker0-fix"):
            shutil.copy(
                HOSTCONF_FILES / "socket-free-bind.0docker.conf",
                _dropin(unit_dir, "woodpecker-exec-proxy@.socket", "20-free-bind.conf"),
            )

        # the node-exporter proxy, rendered by the role and cut back to the unit text the host has (the ordering lines live in the hostconf drop-in)
        name = DOCKER0_METRICS["name"]
        socket_text = metrics_env.get_template("metrics-proxy.socket.j2").render(item=DOCKER0_METRICS, **context)
        live_text = socket_text.replace(
            "DefaultDependencies=no\nConflicts=shutdown.target\nBefore=shutdown.target\n", ""
        )
        assert "FreeBind=true" in live_text and "DefaultDependencies" not in live_text
        write(unit_dir / f"{name}.socket", live_text)
        write(
            unit_dir / f"{name}.service",
            metrics_env.get_template("metrics-proxy.service.j2").render(item=DOCKER0_METRICS, **context),
        )
        link(unit_dir / "sockets.target.wants" / f"{name}.socket", f"/etc/systemd/system/{name}.socket")
        shutil.copy(
            HOSTCONF_FILES / "socket-no-default-deps.0docker.conf",
            _dropin(unit_dir, f"{name}.socket", "10-no-default-deps.conf"),
        )

        # PR 659, applied on the host: the device Wants= the woodpecker socket; the zdocker Wants= is the second drop-in of this change
        device_dir = unit_dir / "sys-subsystem-net-devices-tailscale0.device.d"
        device_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(
            HOSTCONF_FILES / "woodpecker-exec-proxy-follows-tailscale0.0docker.conf",
            device_dir / "10-wants-woodpecker-exec-proxy.conf",
        )
        if variant in ("docker0-wants", "docker0-fix"):
            shutil.copy(
                HOSTCONF_FILES / "tailscale0-wants-zdocker-metrics-proxy.0docker.conf",
                device_dir / "10-wants-zdocker-hypervisor-metrics-proxy.conf",
            )
        sockets = [f"{DOCKER0_WOODPECKER_INSTANCE}.socket", f"{name}.socket"]
        write(root / "etc" / "rig-sockets", "\n".join(sockets) + "\n")
        write(root / "etc" / "rig-operator-socket", f"{DOCKER0_WOODPECKER_INSTANCE}.socket\n")
        print(f"built {variant}: {len(sockets)} sockets", file=sys.stderr)


def _dropin(unit_dir: Path, unit: str, name: str) -> Path:
    directory = unit_dir / f"{unit}.d"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / name


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--out", required=True, type=Path, help="directory to write one tree per variant into (removed first)"
    )
    args = parser.parse_args()
    build(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
