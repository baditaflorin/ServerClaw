"""The 0mcp hypervisor's tailnet proxy sockets survive a tailscaled restart (2026-11-02).

At 12:33:26 CET tailscaled updated itself (the control plane sent `tailscale update --yes`, which ran `apt-get install tailscale=1.104.4`) and was restarted. systemd stopped every socket that has
Requires=tailscaled.service and started them again as soon as tailscaled reported "started", which is before tailscale0 exists and before it has its address. The lv3 sockets (BindToDevice=tailscale0,
so BindsTo= the device unit) failed with "Bound to unit sys-subsystem-net-devices-tailscale0.device, but unit isn't active"; zmcp-runtime-general-metrics-proxy.socket failed with "Cannot assign
requested address". All 20 stayed dead for 8 hours, OpenBao, Postgres, Vaultwarden, Gitea and Woodpecker proxies among them. woodpecker-0exec-build-metrics-proxy.socket had FreeBind=true and came back at once.

The fix has two parts, both pinned here: FreeBind=true on every proxy socket (the bind succeeds before the address exists), and a drop-in on the tailscale0 device unit that Wants= every proxy socket
(systemd starts them when the device comes back). The behaviour itself is proven by scripts/tailscaled_restart_rig (a throwaway systemd container); these tests keep the three lists the fix is made of
(the proxy catalog, the inventory of the node-exporter proxies, the hostconf catalog) from drifting apart, and keep the rig from rotting.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import jinja2
import pytest
import yaml

import fleet_observability_render as fleet

REPO = Path(__file__).resolve().parents[1]
ROLES = REPO / "collections" / "ansible_collections" / "lv3" / "platform" / "roles"
HOSTCONF_DIR = REPO / "config" / "hostconf"
RUNBOOK = REPO / "docs" / "runbooks" / "tailscaled-restart-proxies.md"
DEVICE_DROPIN = "/etc/systemd/system/sys-subsystem-net-devices-tailscale0.device.d/10-wants-lv3-tailscale-proxies.conf"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


rig = _load("tailscaled_restart_rig_build_variants", REPO / "scripts" / "tailscaled_restart_rig" / "build_variants.py")


def _manifest() -> dict:
    return yaml.safe_load((HOSTCONF_DIR / "hostconf.yaml").read_text(encoding="utf-8"))


def _lv3_proxy_names() -> list[str]:
    host_vars = yaml.safe_load((REPO / "inventory" / "host_vars" / "proxmox-host.yml").read_text(encoding="utf-8"))
    return [proxy["name"] for proxy in host_vars["proxmox_tailscale_tcp_proxies"]]


def _metrics_proxies() -> list[dict]:
    """The node-exporter socket proxies the role renders on the 0mcp hypervisor (state present)."""
    _, hostvars, _ = fleet.inventory_model()
    return [p for p in hostvars["operator-bastion"]["fleet_node_exporter_socket_proxies"] if p.get("state") == "present"]


def _section(text: str, name: str) -> list[str]:
    lines: list[str] = []
    inside = False
    for line in text.splitlines():
        if line.startswith("["):
            inside = line.strip() == f"[{name}]"
            continue
        if inside and line.strip() and not line.startswith("#"):
            lines.append(line.strip())
    return lines


def _env(role: str) -> jinja2.Environment:
    return rig.environment(role)


def test_the_lv3_proxy_socket_template_binds_before_the_address_exists() -> None:
    item = {
        "name": "example",
        "listen_address": "192.0.2.7",
        "listen_port": 8200,
        "upstream_host": "198.51.100.1",
        "upstream_port": 8200,
    }
    text = _env("proxmox_tailscale_proxy").get_template("lv3-tailscale-proxy.socket.j2").render(item=item)
    socket_section = _section(text, "Socket")
    # FreeBind lets the bind succeed before tailscale0 has its address; BindToDevice stays (the socket must never answer on another interface)
    assert "FreeBind=true" in socket_section
    assert "BindToDevice=tailscale0" in socket_section
    assert "ListenStream=192.0.2.7:8200" in socket_section
    # the 2026-10-13 ordering fix is still there
    assert "DefaultDependencies=no" in _section(text, "Unit")


def test_the_node_exporter_proxy_template_renders_free_bind_only_when_asked() -> None:
    template = _env("fleet_node_exporter").get_template("metrics-proxy.socket.j2")
    base = {
        "name": "p",
        "listen_address": "192.0.2.7",
        "listen_port": 9101,
        "upstream": "198.51.100.1:9100",
        "socket_description": "d",
    }
    assert "FreeBind=true" in _section(template.render(item={**base, "free_bind": True}), "Socket")
    assert "FreeBind=true" not in _section(template.render(item=base), "Socket")


def test_every_node_exporter_proxy_of_the_0mcp_hypervisor_declares_free_bind() -> None:
    proxies = _metrics_proxies()
    assert {p["name"] for p in proxies} >= {
        "zmcp-runtime-general-metrics-proxy",
        "woodpecker-0exec-build-metrics-proxy",
    }
    for proxy in proxies:
        assert proxy.get("free_bind") is True, f"{proxy['name']} binds the tailnet address and must set free_bind: true"


def test_the_free_bind_drop_in_is_exactly_the_socket_setting() -> None:
    text = (HOSTCONF_DIR / "files" / "socket-free-bind.0mcp.conf").read_text(encoding="utf-8")
    assert _section(text, "Socket") == ["FreeBind=true"]
    assert [line for line in text.splitlines() if line.startswith("[")] == ["[Socket]"]


def test_hostconf_gives_every_lv3_proxy_socket_and_the_runtime_general_proxy_a_free_bind_drop_in() -> None:
    manifest = _manifest()
    expected = [f"lv3-tailscale-proxy-{name}" for name in _lv3_proxy_names()] + ["zmcp-runtime-general-metrics-proxy"]
    carried_by_0mcp = set(
        manifest["hosts"]["pve-0mcp"]["files"]
    )  # the 0docker hypervisor has its own (tests/test_tailscaled_restart_0docker.py)
    entries = {
        fid: f for fid, f in manifest["files"].items() if fid.startswith("socket-free-bind.") and fid in carried_by_0mcp
    }
    assert sorted(fid.removeprefix("socket-free-bind.") for fid in entries) == sorted(expected)
    for unit, entry in ((fid.removeprefix("socket-free-bind."), f) for fid, f in entries.items()):
        assert entry["dest"] == f"/etc/systemd/system/{unit}.socket.d/20-free-bind.conf"
        assert entry["src"] == "socket-free-bind.0mcp.conf"
        assert entry["expect"] == [{"systemd": f"{unit}.socket", "property": "FreeBind", "value": "yes"}]
    carried = set(manifest["hosts"]["pve-0mcp"]["files"])
    assert set(entries) <= carried


def test_every_0mcp_tailnet_proxy_socket_is_covered_by_free_bind() -> None:
    """The sockets the 2026-10-13 ordering fix covers on the 0mcp hypervisor are the proxies of the catalog and of the inventory: all of them bind the tailnet address."""
    manifest = _manifest()
    ordering = {
        fid.removeprefix("socket-no-default-deps.")
        for fid in manifest["hosts"]["pve-0mcp"]["files"]
        if fid.startswith("socket-no-default-deps.")
    }
    catalog = {f"lv3-tailscale-proxy-{name}" for name in _lv3_proxy_names()} | {p["name"] for p in _metrics_proxies()}
    assert ordering == catalog
    with_drop_in = {
        fid.removeprefix("socket-free-bind.")
        for fid in manifest["hosts"]["pve-0mcp"]["files"]
        if fid.startswith("socket-free-bind.")
    }
    in_main_unit = {
        p["name"] for p in _metrics_proxies() if p.get("free_bind") is True
    }  # the role renders FreeBind=true into the unit itself
    assert catalog <= with_drop_in | in_main_unit


def test_the_tailscale0_device_drop_in_wants_every_proxy_socket_of_the_0mcp_hypervisor() -> None:
    manifest = _manifest()
    entry = manifest["files"]["tailscale0-wants-lv3-proxies"]
    assert entry["dest"] == DEVICE_DROPIN
    assert "tailscale0-wants-lv3-proxies" in manifest["hosts"]["pve-0mcp"]["files"]
    text = (HOSTCONF_DIR / "files" / entry["src"]).read_text(encoding="utf-8")
    assert [line for line in text.splitlines() if line.startswith("[")] == ["[Unit]"]
    wanted = [line.removeprefix("Wants=") for line in _section(text, "Unit")]
    assert all(line.startswith("Wants=") for line in _section(text, "Unit"))
    expected = [f"lv3-tailscale-proxy-{name}.socket" for name in _lv3_proxy_names()] + [
        f"{p['name']}.socket" for p in _metrics_proxies()
    ]
    assert sorted(wanted) == sorted(expected), "the device drop-in and the proxy catalogs must list the same sockets"
    assert len(wanted) == len(set(wanted))
    # the drift check proves every name in effect, not only the first
    proven = [x["contains"] for x in entry["expect"]]
    assert sorted(proven) == sorted(expected)
    assert all(
        x["systemd"] == "sys-subsystem-net-devices-tailscale0.device" and x["property"] == "Wants"
        for x in entry["expect"]
    )


def test_the_two_new_drop_ins_never_restart_anything() -> None:
    """hostconf applies a drop-in with a daemon-reload only; FreeBind takes effect when the socket next starts, the device Wants= when the device next appears."""
    for name in ("socket-free-bind.0mcp.conf", "tailscale0-wants-lv3-proxies.0mcp.conf"):
        text = (HOSTCONF_DIR / "files" / name).read_text(encoding="utf-8")
        assert not re.search(r"^(Exec|Restart|Requires|BindsTo|Upholds)", text, flags=re.M), name


def test_the_rig_builds_the_ablation_variants(tmp_path: Path) -> None:
    rig.build(tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(rig.VARIANTS + rig.DOCKER0_VARIANTS)

    def unit(variant: str, name: str) -> str:
        return (tmp_path / variant / "etc" / "systemd" / "system" / name).read_text(encoding="utf-8")

    def device_dropin(variant: str) -> Path:
        return (
            tmp_path
            / variant
            / "etc"
            / "systemd"
            / "system"
            / "sys-subsystem-net-devices-tailscale0.device.d"
            / "10-wants-lv3-tailscale-proxies.conf"
        )

    lv3, zmcp = "lv3-tailscale-proxy-openbao.socket", "zmcp-runtime-general-metrics-proxy.socket"
    assert (
        "FreeBind" not in unit("role-none", lv3)
        and "FreeBind" not in unit("role-none", zmcp)
        and not device_dropin("role-none").exists()
    )
    assert (
        "FreeBind=true" in unit("role-freebind", lv3)
        and "FreeBind=true" in unit("role-freebind", zmcp)
        and not device_dropin("role-freebind").exists()
    )
    assert "FreeBind" not in unit("role-wants", lv3) and device_dropin("role-wants").exists()
    assert (
        "FreeBind=true" in unit("role-fix", lv3)
        and "FreeBind=true" in unit("role-fix", zmcp)
        and device_dropin("role-fix").exists()
    )
    # the live layout: old main units, the hostconf drop-ins carry the settings
    assert "FreeBind" not in unit("hostconf-fix", lv3) and "DefaultDependencies" not in unit("hostconf-fix", lv3)
    for name in (lv3, zmcp):
        dropins = tmp_path / "hostconf-fix" / "etc" / "systemd" / "system" / f"{name}.d"
        assert sorted(p.name for p in dropins.iterdir()) == ["10-no-default-deps.conf", "20-free-bind.conf"]
    assert device_dropin("hostconf-fix").read_text(encoding="utf-8") == (
        HOSTCONF_DIR / "files" / "tailscale0-wants-lv3-proxies.0mcp.conf"
    ).read_text(encoding="utf-8")
    for variant in rig.VARIANTS:
        sockets = (tmp_path / variant / "etc" / "rig-sockets").read_text(encoding="utf-8").split()
        assert len(sockets) == 5 and all(s.endswith(".socket") for s in sockets)


def test_the_rig_models_the_restart_the_journal_showed() -> None:
    """The stand-in tailscaled reports ready first, creates the device 50 ms later and gives it the address 0.8 s after that (journal of 2026-11-02 12:33:31 to 12:33:32)."""
    script = rig.FAKE_TAILSCALED
    assert script.index("systemd-notify --ready") < script.index("ip link add tailscale0") < script.index("ip addr add")
    assert "sleep 0.05" in script and "sleep 0.75" in script


def test_the_runbook_names_the_apply_path_and_the_proof() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    for needle in (
        "hostconf.py apply --host pve-0mcp",
        "scripts/tailscaled_restart_rig/run.sh",
        "tailscale set --auto-update=false",
        "pg-replica-tailnet.service",
        "sys-subsystem-net-devices-tailscale0.device",
    ):
        assert needle in text, needle


@pytest.mark.parametrize("variant", ["role-fix", "hostconf-fix"])
def test_the_fix_variants_keep_the_operator_able_to_stop_a_socket(variant: str, tmp_path: Path) -> None:
    """Wants= is a one-time pull when the device appears; Upholds= would restart a socket an operator stopped on purpose."""
    rig.build(tmp_path)
    text = (
        tmp_path
        / variant
        / "etc"
        / "systemd"
        / "system"
        / "sys-subsystem-net-devices-tailscale0.device.d"
        / "10-wants-lv3-tailscale-proxies.conf"
    ).read_text(encoding="utf-8")
    assert "Upholds" not in text
