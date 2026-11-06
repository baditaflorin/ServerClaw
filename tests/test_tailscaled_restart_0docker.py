"""The 0docker hypervisor's tailnet proxy sockets survive a tailscaled restart (2026-11-03, follow-up of tests/test_tailscaled_restart_proxies.py for 0mcp).

On 2026-11-02 at 12:33 CET tailscaled on the 0docker hypervisor updated itself and was restarted (the stop timed out after 90 s, it started again at 12:34:59). Three tailnet sockets are involved:
woodpecker-exec-proxy@9000.socket (the Woodpecker agent path; BindToDevice=tailscale0, so it BindsTo= the tailscale0 device unit), zdocker-hypervisor-metrics-proxy.socket (the node-exporter proxy; FreeBind,
no BindToDevice) and a stale woodpecker-exec-proxy@9100.socket that is disabled on purpose. PR 659 made the device Want the woodpecker socket; that is half a fix, because the device appears before it has its
address: the socket also needs FreeBind=true. The node-exporter proxy has FreeBind but nothing starts it after a separate stop and start of tailscaled: it is Wanted by the device too.

The behaviour is proven by scripts/tailscaled_restart_rig (the docker0-* variants, systemd 252); these tests keep the lists the fix is made of (the inventory of the node-exporter proxies, the hostconf catalog, the
unit text read from the host) from drifting apart, and keep the rig variants what they claim to be.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import fleet_observability_render as fleet
from test_tailscaled_restart_proxies import HOSTCONF_DIR, RUNBOOK, _manifest, _section, rig

REPO = Path(__file__).resolve().parents[1]
DEVICE_DROPIN_DIR = "/etc/systemd/system/sys-subsystem-net-devices-tailscale0.device.d/"
DEVICE = "sys-subsystem-net-devices-tailscale0.device"
WOODPECKER_INSTANCE = "woodpecker-exec-proxy@9000.socket"
HOST = "bastion"  # the 0docker hypervisor in config/hostconf/hostconf.yaml


def _proxies(state: str) -> list[dict]:
    _, hostvars, _ = fleet.inventory_model()
    return [p for p in hostvars["0docker_bastion"]["fleet_node_exporter_socket_proxies"] if p.get("state") == state]


def _device_entries() -> dict[str, dict]:
    """The catalog entries the 0docker hypervisor carries that are drop-ins of the tailscale0 device unit."""
    manifest = _manifest()
    carried = set(manifest["hosts"][HOST]["files"])
    return {
        fid: entry
        for fid, entry in manifest["files"].items()
        if fid in carried and entry["dest"].startswith(DEVICE_DROPIN_DIR)
    }


def _wants(entry: dict) -> list[str]:
    text = (HOSTCONF_DIR / "files" / entry["src"]).read_text(encoding="utf-8")
    assert [line for line in text.splitlines() if line.startswith("[")] == ["[Unit]"]
    lines = _section(text, "Unit")
    assert all(line.startswith("Wants=") for line in lines)
    return [line.removeprefix("Wants=") for line in lines]


def test_the_woodpecker_fixture_is_the_unit_as_found_on_the_host() -> None:
    """scripts/tailscaled_restart_rig/0docker-units/ holds the hand-installed template as read from the hypervisor (2026-11-03): no role renders it."""
    socket = (rig.DOCKER0_UNITS / "woodpecker-exec-proxy@.socket").read_text(encoding="utf-8")
    service = (rig.DOCKER0_UNITS / "woodpecker-exec-proxy@.service").read_text(encoding="utf-8")
    assert _section(socket, "Socket") == [
        f"ListenStream={rig.DOCKER0_ADDRESS}:%i",
        "BindToDevice=tailscale0",
        "NoDelay=true",
    ]
    assert "FreeBind" not in socket, "the fixture is the exposure: the host's own unit has no FreeBind"
    assert "Requires=tailscaled.service" in _section(socket, "Unit")
    assert "Requires=tailscaled.service woodpecker-exec-proxy@%i.socket" in _section(service, "Unit")


def test_the_free_bind_drop_in_is_exactly_the_socket_setting() -> None:
    text = (HOSTCONF_DIR / "files" / "socket-free-bind.0docker.conf").read_text(encoding="utf-8")
    assert _section(text, "Socket") == ["FreeBind=true"]
    assert [line for line in text.splitlines() if line.startswith("[")] == ["[Socket]"]


def test_hostconf_gives_the_woodpecker_template_a_free_bind_drop_in_next_to_its_ordering_one() -> None:
    manifest = _manifest()
    entry = manifest["files"]["socket-free-bind.woodpecker-exec-proxy"]
    # on the template, so every instance has it (9000 is the live one)
    assert entry["dest"] == "/etc/systemd/system/woodpecker-exec-proxy@.socket.d/20-free-bind.conf"
    assert entry["src"] == "socket-free-bind.0docker.conf"
    assert entry["expect"] == [{"systemd": WOODPECKER_INSTANCE, "property": "FreeBind", "value": "yes"}]
    ordering = manifest["files"]["socket-no-default-deps.woodpecker-exec-proxy"]
    assert Path(ordering["dest"]).parent == Path(entry["dest"]).parent
    carried = set(manifest["hosts"][HOST]["files"])
    assert {"socket-free-bind.woodpecker-exec-proxy", "woodpecker-exec-proxy-follows-tailscale0"} <= carried


def test_every_present_node_exporter_proxy_of_the_0docker_hypervisor_declares_free_bind() -> None:
    proxies = _proxies("present")
    assert {p["name"] for p in proxies} == {"zdocker-hypervisor-metrics-proxy"}
    for proxy in proxies:
        assert proxy.get("free_bind") is True, f"{proxy['name']} binds the tailnet address and must set free_bind: true"


def test_the_tailscale0_device_wants_every_tailnet_socket_of_the_0docker_hypervisor_and_nothing_stale() -> None:
    """The device drop-ins add up: together they list the woodpecker instance that is live and every present node-exporter proxy, and never the stale disabled instance (it would collide on :9100)."""
    entries = _device_entries()
    assert sorted(entries) == ["tailscale0-wants-zdocker-metrics-proxy", "woodpecker-exec-proxy-follows-tailscale0"]
    wanted = [name for entry in entries.values() for name in _wants(entry)]
    expected = [WOODPECKER_INSTANCE] + [f"{p['name']}.socket" for p in _proxies("present")]
    assert sorted(wanted) == sorted(expected)
    assert len(wanted) == len(set(wanted))
    for stale in _proxies("disabled"):
        assert f"{stale['name']}.socket" not in wanted
    assert "woodpecker-exec-proxy@9100.socket" not in wanted


def test_every_device_drop_in_is_proven_with_contains_because_they_add_up() -> None:
    """`value:` is an exact match of the whole Wants= list: with two drop-ins it would report drift on the first one's entry after the second is applied."""
    for fid, entry in _device_entries().items():
        names = _wants(entry)
        proven = []
        for x in entry["expect"]:
            assert x["systemd"] == DEVICE and x["property"] == "Wants", fid
            assert "value" not in x, f"{fid}: use contains, the device unit has more than one Wants= drop-in"
            proven.append(x["contains"])
        assert sorted(proven) == sorted(names), fid


def test_the_second_device_drop_in_is_a_new_file_so_the_applied_one_is_not_rewritten() -> None:
    entries = _device_entries()
    first, second = (
        entries["woodpecker-exec-proxy-follows-tailscale0"],
        entries["tailscale0-wants-zdocker-metrics-proxy"],
    )
    assert first["dest"] == DEVICE_DROPIN_DIR + "10-wants-woodpecker-exec-proxy.conf"
    assert second["dest"] == DEVICE_DROPIN_DIR + "10-wants-zdocker-hypervisor-metrics-proxy.conf"
    assert first["src"] != second["src"]


def test_the_new_drop_ins_never_restart_anything() -> None:
    """hostconf applies a drop-in with a daemon-reload only; FreeBind takes effect when the socket next starts, the device Wants= when the device next appears."""
    import re

    for name in ("socket-free-bind.0docker.conf", "tailscale0-wants-zdocker-metrics-proxy.0docker.conf"):
        text = (HOSTCONF_DIR / "files" / name).read_text(encoding="utf-8")
        assert not re.search(r"^(Exec|Restart|Requires|BindsTo|Upholds)", text, flags=re.M), name


def test_the_rig_models_the_inventory_item_of_the_node_exporter_proxy() -> None:
    (proxy,) = _proxies("present")
    for key in (
        "name",
        "listen_address",
        "listen_port",
        "upstream",
        "free_bind",
        "socket_description",
        "service_description",
    ):
        assert rig.DOCKER0_METRICS[key] == proxy[key], key


def test_the_0docker_variants_are_the_ablation_they_claim_to_be(tmp_path: Path) -> None:
    rig.build(tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(rig.VARIANTS + rig.DOCKER0_VARIANTS)

    def system(variant: str) -> Path:
        return tmp_path / variant / "etc" / "systemd" / "system"

    def same(a: Path, b: Path) -> bool:
        return a.read_text(encoding="utf-8") == b.read_text(encoding="utf-8")

    free_bind = {"docker0-live": False, "docker0-freebind": True, "docker0-wants": False, "docker0-fix": True}
    zdocker_wants = {"docker0-live": False, "docker0-freebind": False, "docker0-wants": True, "docker0-fix": True}
    assert set(free_bind) == set(zdocker_wants) == set(rig.DOCKER0_VARIANTS)
    for variant in rig.DOCKER0_VARIANTS:
        unit_dir = system(variant)
        # the template as the host has it (no FreeBind in the unit itself), the hostconf drop-ins carry the settings
        assert same(unit_dir / "woodpecker-exec-proxy@.socket", rig.DOCKER0_UNITS / "woodpecker-exec-proxy@.socket")
        template_dropins = sorted(p.name for p in (unit_dir / "woodpecker-exec-proxy@.socket.d").iterdir())
        assert template_dropins == (
            ["10-no-default-deps.conf", "20-free-bind.conf"] if free_bind[variant] else ["10-no-default-deps.conf"]
        )
        if free_bind[variant]:
            assert same(
                unit_dir / "woodpecker-exec-proxy@.socket.d" / "20-free-bind.conf",
                HOSTCONF_DIR / "files" / "socket-free-bind.0docker.conf",
            )
        # the node-exporter proxy: FreeBind in its unit (the role renders it), no DefaultDependencies in the unit text (the host's drop-in has it)
        zdocker = (unit_dir / "zdocker-hypervisor-metrics-proxy.socket").read_text(encoding="utf-8")
        assert "FreeBind=true" in zdocker and "DefaultDependencies" not in zdocker
        assert f"ListenStream={rig.DOCKER0_ADDRESS}:9100" in zdocker and "BindToDevice" not in zdocker
        # PR 659 is applied on the host in every variant; the zdocker Wants= only where the variant adds it
        device_dir = unit_dir / "sys-subsystem-net-devices-tailscale0.device.d"
        assert same(
            device_dir / "10-wants-woodpecker-exec-proxy.conf",
            HOSTCONF_DIR / "files" / "woodpecker-exec-proxy-follows-tailscale0.0docker.conf",
        )
        extra = device_dir / "10-wants-zdocker-hypervisor-metrics-proxy.conf"
        assert extra.exists() is zdocker_wants[variant]
        if zdocker_wants[variant]:
            assert same(extra, HOSTCONF_DIR / "files" / "tailscale0-wants-zdocker-metrics-proxy.0docker.conf")
        # no tailscaled.service.wants links on this host; both sockets are enabled through sockets.target
        assert not (unit_dir / "tailscaled.service.wants").exists()
        assert sorted(p.name for p in (unit_dir / "sockets.target.wants").iterdir()) == [
            WOODPECKER_INSTANCE,
            "zdocker-hypervisor-metrics-proxy.socket",
        ]
        root = tmp_path / variant
        assert (root / "etc" / "rig-sockets").read_text(encoding="utf-8").split() == [
            WOODPECKER_INSTANCE,
            "zdocker-hypervisor-metrics-proxy.socket",
        ]
        assert (root / "etc" / "rig-operator-socket").read_text(encoding="utf-8").strip() == WOODPECKER_INSTANCE
        tailscaled = (root / "usr" / "local" / "bin" / "fake-tailscaled").read_text(encoding="utf-8")
        assert f"ip addr add {rig.DOCKER0_ADDRESS}/32" in tailscaled and rig.TAILNET_ADDRESS not in tailscaled
    # the 0mcp family keeps its own address
    assert f"ip addr add {rig.TAILNET_ADDRESS}/32" in (
        tmp_path / "role-fix" / "usr" / "local" / "bin" / "fake-tailscaled"
    ).read_text(encoding="utf-8")


def test_run_sh_runs_the_0docker_variants_on_the_0docker_systemd_and_judges_them() -> None:
    text = (REPO / "scripts" / "tailscaled_restart_rig" / "run.sh").read_text(encoding="utf-8")
    for variant in rig.DOCKER0_VARIANTS:
        assert variant in text, variant
    assert '[ "$base" = bookworm ]' in text, (
        "the docker0 family belongs on debian:bookworm (systemd 252, as on the 0docker hypervisor)"
    )
    assert "docker0-fix" in text and "docker0-live" in text
    assert "rig-operator-socket" in text


@pytest.mark.parametrize(
    "needle",
    [
        "## 0docker hypervisor",
        "hostconf.py apply --host bastion",
        "socket-free-bind.woodpecker-exec-proxy",
        "tailscale0-wants-zdocker-metrics-proxy",
        "docker0-live",
        "docker0-fix",
        "0memory-postgres-relay.service",
        "registrant-postgres-relay.service",
        "systemctl show -p FreeBind",
    ],
)
def test_the_runbook_has_the_0docker_apply_the_checks_and_the_scan(needle: str) -> None:
    assert needle in RUNBOOK.read_text(encoding="utf-8"), needle
