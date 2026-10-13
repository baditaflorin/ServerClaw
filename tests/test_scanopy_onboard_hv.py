"""Tests for the hypervisor-side forced command of the Scanopy onboarding job.

The wrapper is the only thing the onboarding SSH key can run on a Proxmox host, so its argument validation, the way it hands the
daemon key to the guest (stdin only) and its guest listing are what keep that key narrow. Proxmox commands are replaced by a
scripted `run`; nothing here touches a real host.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "collections/ansible_collections/lv3/platform/roles/monitoring_vm/files/scanopy-onboard/scanopy_onboard_hv.py"
)
KEY = "k3y-0123456789.abc"
GOOD = ["install", "ct", "107", "http://10.10.10.1:60072", "ct-0docker-107-pve-exporter", "0.17.22"]


@pytest.fixture()
def hv(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    spec = importlib.util.spec_from_file_location("scanopy_onboard_hv_under_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Recorder:
    def __init__(self, replies: dict[str, tuple[int, str, str]]) -> None:
        self.replies = replies
        self.calls: list[tuple[list[str], str | None]] = []

    def __call__(self, cmd, stdin=None, timeout=60):
        self.calls.append((list(cmd), stdin))
        for prefix, reply in self.replies.items():
            if " ".join(cmd).startswith(prefix):
                return reply
        return 0, "", ""


def invoke(hv: ModuleType, monkeypatch: pytest.MonkeyPatch, original: str, stdin: str = "") -> int:
    monkeypatch.setenv("SSH_ORIGINAL_COMMAND", original)
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    return hv.main()


def test_only_list_and_install_are_accepted(hv, monkeypatch) -> None:
    rec = Recorder({})
    monkeypatch.setattr(hv, "run", rec)

    for forbidden in ("", "bash", "list extra", "install", "reboot", "qm stop 100", "list; id", "$(id)"):
        assert invoke(hv, monkeypatch, forbidden) == 2, forbidden
    assert rec.calls == []


@pytest.mark.parametrize(
    "args",
    [
        ["install", "lxc", "107", "http://10.10.10.1:60072", "n", "0.17.22"],  # kind
        ["install", "ct", "10x", "http://10.10.10.1:60072", "n", "0.17.22"],  # vmid
        ["install", "ct", "107", "http://evil.example:60072", "n", "0.17.22"],  # not a fleet relay
        ["install", "ct", "107", "http://10.10.10.1:8080", "n", "0.17.22"],  # wrong port
        ["install", "ct", "107", "https://10.10.10.1:60072", "n", "0.17.22"],
        ["install", "ct", "107", "http://10.10.10.1:60072", "a b", "0.17.22"],  # name
        ["install", "ct", "107", "http://10.10.10.1:60072", "$(id)", "0.17.22"],
        ["install", "ct", "107", "http://10.10.10.1:60072", "n", "1.2"],  # version
        ["install", "ct", "107", "http://10.10.10.1:60072", "n", "0.17.22; id"],
    ],
)
def test_install_refuses_malformed_arguments_before_touching_anything(hv, monkeypatch, args) -> None:
    rec = Recorder({})
    monkeypatch.setattr(hv, "run", rec)

    assert invoke(hv, monkeypatch, " ".join(args), KEY + "\n") == 2

    assert rec.calls == []


def test_install_refuses_a_missing_or_malformed_key_and_a_guest_that_is_not_running(hv, monkeypatch) -> None:
    rec = Recorder({"pct list": (0, "VMID Status Lock Name\n107 running pve-exporter\n108 stopped other\n", "")})
    monkeypatch.setattr(hv, "run", rec)

    assert invoke(hv, monkeypatch, " ".join(GOOD), "") == 2
    assert invoke(hv, monkeypatch, " ".join(GOOD), "bad key with spaces\n") == 2
    assert invoke(hv, monkeypatch, " ".join(GOOD).replace(" 107 ", " 108 "), KEY + "\n") == 2  # stopped
    assert invoke(hv, monkeypatch, " ".join(GOOD).replace(" 107 ", " 999 "), KEY + "\n") == 2  # unknown
    assert not any(call[0][:2] == ["pct", "exec"] for call in rec.calls)


def test_install_in_a_container_pipes_the_script_with_the_key_on_stdin_only(hv, monkeypatch, capsys) -> None:
    rec = Recorder({
        "pct list": (0, "VMID Status Lock Name\n107 running pve-exporter\n", ""),
        "pct exec 107": (0, "RESULT active=yes docker=no\n", ""),
    })
    monkeypatch.setattr(hv, "run", rec)

    assert invoke(hv, monkeypatch, " ".join(GOOD), KEY + "\n") == 0

    (cmd, script), = [call for call in rec.calls if call[0][:2] == ["pct", "exec"]]
    assert cmd == ["pct", "exec", "107", "--", "bash", "-s"]
    assert f"KEY={KEY}" in script and "http://10.10.10.1:60072" in script and "'0.17.22'" not in script
    assert ' install --server-url "$URL" --mode daemon_poll' in script
    assert not any(KEY in part for call in rec.calls for part in call[0])  # never in argv
    assert "RESULT active=yes docker=no" in capsys.readouterr().out


def test_install_in_a_vm_goes_through_the_guest_agent_with_stdin_and_returns_the_guest_exit_code(hv, monkeypatch, capsys) -> None:
    reply = json.dumps({"exited": 1, "exitcode": 6, "out-data": "ERR install failed: x\n", "err-data": ""})
    rec = Recorder({"qm list": (0, "VMID NAME STATUS MEM\n200 stage running 4096\n", ""), "qm guest exec 200": (0, reply, "")})
    monkeypatch.setattr(hv, "run", rec)

    rc = invoke(hv, monkeypatch, "install vm 200 http://10.10.10.1:60072 vm-0mcp-200-stage latest", KEY + "\n")

    assert rc == 6
    (cmd, script), = [call for call in rec.calls if call[0][:3] == ["qm", "guest", "exec"]]
    assert cmd[:6] == ["qm", "guest", "exec", "200", "--pass-stdin", "1"] and cmd[-3:] == ["--", "bash", "-s"]
    assert KEY in script and not any(KEY in part for part in cmd)
    assert "ERR install failed: x" in capsys.readouterr().out


def test_the_guest_script_refuses_an_active_daemon_and_other_architectures(hv) -> None:
    script = hv.GUEST_SCRIPT.format(key="k", url="u", version="v")

    assert "systemctl is-active --quiet scanopy-daemon" in script and "RESULT skipped=already-active" in script
    assert 'uname -m)" = x86_64' in script
    assert "-gt 5000000" in script  # a truncated or HTML download is not installed
    assert "set -x" not in script  # the key is in the script text; tracing would print it


def test_list_reports_running_non_template_guests_with_macs_and_real_interface_addresses(hv, monkeypatch, capsys, tmp_path) -> None:
    confs = {
        ("vm", "200"): ["name: stage", "net0: virtio=BC:24:11:AA:BB:CC,bridge=vmbr20"],
        ("vm", "201"): ["template: 1", "net0: virtio=BC:24:11:AA:BB:DD,bridge=vmbr20"],
        ("ct", "107"): ["hostname: exporter", "net0: name=eth0,bridge=vmbr10,hwaddr=BC:24:11:00:00:07,ip=dhcp"],
    }
    monkeypatch.setattr(hv, "conf_lines", lambda kind, vmid: confs.get((kind, vmid), []))
    agent = [
        {"name": "lo", "ip-addresses": [{"ip-address": "127.0.0.1", "ip-address-type": "ipv4"}]},
        {"name": "ens18", "ip-addresses": [{"ip-address": "10.10.10.200", "ip-address-type": "ipv4"},
                                           {"ip-address": "fe80::1", "ip-address-type": "ipv6"}]},
        {"name": "docker0", "ip-addresses": [{"ip-address": "172.17.0.1", "ip-address-type": "ipv4"}]},
        {"name": "br-1234", "ip-addresses": [{"ip-address": "172.20.0.1", "ip-address-type": "ipv4"}]},
    ]
    rec = Recorder({
        "qm list": (0, "VMID NAME STATUS MEM\n200 stage running 1\n201 tpl running 1\n202 off stopped 1\n", ""),
        "qm agent 200": (0, json.dumps(agent), ""),
        "pct list": (0, "VMID Status Lock Name\n107 running pve-exporter\n", ""),
        "pct exec 107": (0, "2: eth0    inet 10.10.10.107/24 brd 10.10.10.255 scope global eth0\n3: docker0    inet 172.17.0.1/16 scope global docker0\n", ""),
    })
    monkeypatch.setattr(hv, "run", rec)

    assert invoke(hv, monkeypatch, "list") == 0

    out = json.loads(capsys.readouterr().out)
    assert out["wrapper_version"] == hv.WRAPPER_VERSION
    assert out["guests"] == [
        {"kind": "vm", "id": 200, "name": "stage", "macs": ["bc:24:11:aa:bb:cc"], "ips": ["10.10.10.200"], "manageable": True},
        {"kind": "ct", "id": 107, "name": "pve-exporter", "macs": ["bc:24:11:00:00:07"], "ips": ["10.10.10.107"], "manageable": True},
    ]


def test_a_vm_whose_guest_agent_fails_is_listed_as_not_manageable(hv, monkeypatch, capsys) -> None:
    monkeypatch.setattr(hv, "conf_lines", lambda kind, vmid: ["name: x"])
    rec = Recorder({"qm list": (0, "VMID NAME STATUS\n640 mirror running\n", ""), "qm agent 640": (255, "", "QEMU guest agent is not running"),
                    "pct list": (0, "VMID Status Lock Name\n", "")})
    monkeypatch.setattr(hv, "run", rec)

    invoke(hv, monkeypatch, "list")

    (g,) = json.loads(capsys.readouterr().out)["guests"]
    assert g["manageable"] is False and g["ips"] == []
