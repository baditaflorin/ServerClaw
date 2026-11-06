"""The per-VM Proxmox firewall install must never delete live rules, in check mode or in a real run.

On 2026-10-30 `--tags proxmox-vm-firewall` copied the inventory render over `/etc/pve/firewall/<vmid>.fw` on 0mcp and removed about
25 production rules for three minutes: the live files also carry hand-authored rules, an AUTO-MIGRATED set and, on one VM, a
`# BEGIN fleet-pool-fw` block, none of which the render knows. The `--check --diff` before it had shown 19 added lines and no
removal because it compared the render with the staging copy `/root/.lv3-vm-<vmid>.fw`, not with the live file.

`roles/proxmox_network/files/pve_fw_guard.py` now decides what may be written. These tests pin four things with fixtures in
tests/fixtures/pve_firewall_guard/ (live and render files shaped like the incident):

* the guard itself: a removed rule line, option line, disabled rule or managed block is refused, nothing is written (not even a
  backup), and an addition, a new file, a comment, spacing or order change is allowed, backed up first and restorable;
* the role: the comparison runs in check mode against the LIVE directory, the install is the guard's `apply`, and no other task
  copies a render over a live file;
* the whole role run by ansible-playbook against a temporary "live" directory with `qm` and `pve-firewall` shims: `--check`
  fails on a removal and writes nothing, a real run fails the same way, `-e proxmox_network_allow_rule_removal=true` backs up and
  installs, an additive run (including a new VM file) installs and a second run changes nothing.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
ROLE = REPO / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / "proxmox_network"
GUARD = ROLE / "files" / "pve_fw_guard.py"
TASKS = ROLE / "tasks" / "main.yml"
DEFAULTS = ROLE / "defaults" / "main.yml"
SPECS = ROLE / "meta" / "argument_specs.yml"
FIXTURES = REPO / "tests" / "fixtures" / "pve_firewall_guard"
ALLOW_VARIABLE = "proxmox_network_allow_rule_removal"

_spec = importlib.util.spec_from_file_location("pve_fw_guard", GUARD)
assert _spec is not None and _spec.loader is not None
guard = importlib.util.module_from_spec(_spec)
sys.modules["pve_fw_guard"] = guard
_spec.loader.exec_module(guard)


# --- helpers for the guard ---------------------------------------------------------------------------------------------------


def _stage(
    tmp_path: Path, vmids: list[int], *, live_from: Path = FIXTURES / "live", render_from: Path = FIXTURES / "render"
):
    """Copy fixture files into a live dir and a staging dir named like the role names them."""
    live, stage, backup = tmp_path / "live", tmp_path / "stage", tmp_path / "backup"
    for directory in (live, stage, backup):
        directory.mkdir()
    for vmid in vmids:
        if (live_from / f"{vmid}.fw").is_file():
            shutil.copy2(live_from / f"{vmid}.fw", live / f"{vmid}.fw")
        shutil.copy2(render_from / f"{vmid}.fw", stage / f".lv3-vm-{vmid}.fw")
    return live, stage, backup


def _run(
    mode: str, tmp_path: Path, vmids: list[int], *extra: str, capsys: pytest.CaptureFixture[str]
) -> tuple[int, dict]:
    live, stage, backup = tmp_path / "live", tmp_path / "stage", tmp_path / "backup"
    code = guard.main(
        [
            mode,
            *map(str, vmids),
            "--live-dir",
            str(live),
            "--stage-dir",
            str(stage),
            "--backup-root",
            str(backup),
            "--timestamp",
            "20261030T120000Z",
            "--format",
            "json",
            *extra,
        ]
    )
    return code, json.loads(capsys.readouterr().out)


def _tree(directory: Path) -> dict[str, str]:
    return {
        str(path.relative_to(directory)): path.read_text(encoding="utf-8")
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def _plan_text(live: str | None, render: str, tmp_path: Path, vmid: int = 7):
    live_dir, stage_dir = tmp_path / "live", tmp_path / "stage"
    live_dir.mkdir(exist_ok=True)
    stage_dir.mkdir(exist_ok=True)
    if live is not None:
        (live_dir / f"{vmid}.fw").write_text(live, encoding="utf-8")
    (stage_dir / f".lv3-vm-{vmid}.fw").write_text(render, encoding="utf-8")
    return guard.plan_vm(vmid, live_dir, stage_dir)


BASE = "[OPTIONS]\nenable: 1\npolicy_in: DROP\n\n[RULES]\nIN ACCEPT -p tcp -dport 443\n"


# --- the guard: what is a removal -------------------------------------------------------------------------------------------


def test_the_incident_shape_is_refused_and_nothing_is_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """VM 191: hand-authored rules, an AUTO-MIGRATED set, a disabled rule and a managed block that the render lacks."""
    live, _, backup = _stage(tmp_path, [191, 140])
    before = _tree(live)

    code, result = _run("apply", tmp_path, [191, 140], capsys=capsys)

    assert code == guard.EXIT_REFUSED
    assert result["refused"] is True
    assert result["removal_vmids"] == [191]
    assert result["installed_vmids"] == [] and result["backup_dir"] is None
    assert _tree(live) == before, "a refused run must leave every live file as it was, including the additive VM 140"
    assert list(backup.iterdir()) == [], "a refused run writes nothing at all, not even a backup"
    removed = {item["line"] for vm in result["vms"] for item in vm["removed"]}
    assert "IN ACCEPT -source 10.10.10.14/32 -p tcp -dport 9100 # prometheus" in removed
    assert "|IN ACCEPT -source 10.10.10.22/32 -p tcp -dport 18021" in removed, (
        "a disabled rule is still the operator's rule"
    )
    assert "IN ACCEPT -source 10.10.10.30/32 -p tcp -dport 8443" in removed
    by_vmid = {vm["vmid"]: vm for vm in result["vms"]}
    assert by_vmid[191]["removed_blocks"] == ["fleet-pool-fw"]
    assert by_vmid[140]["removed"] == [] and by_vmid[140]["state"] == "additive"
    report = "\n".join(result["report"])
    assert "REMOVES 7 live rule/option line(s) and 1 managed block(s)" in report
    assert "!! REMOVED [RULES] IN ACCEPT -source 10.10.10.54/32 -p tcp -dport 22" in report
    assert "(in managed block fleet-pool-fw)" in report
    assert "REFUSED" in report and ALLOW_VARIABLE in report


def test_plan_reports_the_same_refusal_without_ever_writing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Check mode runs `plan`: it must give the real run's answer, and it must be read only."""
    live, stage, backup = _stage(tmp_path, [191, 140, 110])
    before_live, before_stage = _tree(live), _tree(stage)

    code, plan = _run("plan", tmp_path, [191, 140, 110], capsys=capsys)
    apply_code, apply = _run("apply", tmp_path, [191, 140, 110], capsys=capsys)

    assert code == apply_code == guard.EXIT_REFUSED
    assert plan["report"] == apply["report"]
    assert _tree(live) == before_live and _tree(stage) == before_stage and list(backup.iterdir()) == []


def test_an_addition_a_new_file_and_an_unchanged_file_are_allowed_and_backed_up(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    live, stage, backup = _stage(tmp_path, [140, 155, 110])
    original_140, original_110 = (live / "140.fw").read_text(), (live / "110.fw").read_text()

    code, result = _run("apply", tmp_path, [140, 155, 110], capsys=capsys)

    assert code == guard.EXIT_OK and result["refused"] is False
    assert [vm["state"] for vm in result["vms"]] == ["unchanged", "additive", "new"]
    assert result["installed_vmids"] == [140, 155], "an unchanged file is not rewritten"
    assert (live / "140.fw").read_text() == (stage / ".lv3-vm-140.fw").read_text()
    assert (live / "155.fw").read_text() == (stage / ".lv3-vm-155.fw").read_text()
    assert (live / "110.fw").read_text() == original_110
    saved = Path(result["backup_dir"])
    assert saved == backup / "fw-backup-20261030T120000Z"
    assert sorted(path.name for path in saved.iterdir()) == ["140.fw", "restore.sh"], (
        "only files that are replaced and existed"
    )
    assert (saved / "140.fw").read_text() == original_140
    assert "1 comment line(s) not in the render are dropped" in "\n".join(result["report"]), (
        "comment loss is shown, not blocking"
    )
    assert result["restore_command"] in "\n".join(result["install_report"])


def test_restore_script_puts_the_old_files_back_and_removes_the_files_the_run_created(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    live, _, _ = _stage(tmp_path, [140, 155])
    original_140 = (live / "140.fw").read_text()
    _, result = _run("apply", tmp_path, [140, 155], capsys=capsys)
    restore = Path(result["backup_dir"]) / "restore.sh"

    assert stat.S_IMODE(restore.stat().st_mode) == 0o700
    script = restore.read_text()
    assert script.startswith("#!/bin/sh\n") and "set -eu" in script and script.rstrip().endswith("pve-firewall restart")
    # run it with a stub pve-firewall so the file operations are the real ones
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "pve-firewall").write_text("#!/bin/sh\nexit 0\n")
    (stub / "pve-firewall").chmod(0o755)
    subprocess.run(["sh", str(restore)], check=True, env={**os.environ, "PATH": f"{stub}:{os.environ['PATH']}"})

    assert (live / "140.fw").read_text() == original_140
    assert not (live / "155.fw").exists()


def test_a_second_install_changes_nothing_and_takes_no_backup(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _stage(tmp_path, [140, 155])
    _run("apply", tmp_path, [140, 155], capsys=capsys)

    code, again = _run("apply", tmp_path, [140, 155], capsys=capsys)

    assert code == guard.EXIT_OK
    assert again["changed_vmids"] == [] and again["installed_vmids"] == [] and again["backup_dir"] is None
    assert len(list((tmp_path / "backup").iterdir())) == 1


def test_the_operator_variable_allows_the_removal_after_a_backup(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    live, stage, _ = _stage(tmp_path, [191, 140])
    original_191 = (live / "191.fw").read_text()

    code, result = _run("apply", tmp_path, [191, 140], "--allow-rule-removal", capsys=capsys)

    assert code == guard.EXIT_OK and result["refused"] is False
    assert result["removal_vmids"] == [191], "the removal is still reported, it is only allowed"
    assert result["installed_vmids"] == [140, 191]
    assert (live / "191.fw").read_text() == (stage / ".lv3-vm-191.fw").read_text()
    assert (Path(result["backup_dir"]) / "191.fw").read_text() == original_191, "the removed rules are in the backup"
    assert "REMOVAL ALLOWED for VM 191" in "\n".join(result["report"])


@pytest.mark.parametrize(
    ("live", "render", "removes"),
    [
        pytest.param(BASE + "IN ACCEPT -p tcp -dport 80\n", BASE, True, id="rule-removed"),
        pytest.param(BASE, BASE.replace("-dport 443", "-dport 8443"), True, id="rule-changed-removes-the-old-one"),
        pytest.param(BASE + "|IN ACCEPT -p tcp -dport 80\n", BASE, True, id="disabled-rule-removed"),
        pytest.param(BASE + "IN DROP -p tcp -dport 23\n", BASE, True, id="drop-rule-removed"),
        pytest.param(
            BASE.replace("policy_in: DROP\n", "policy_in: DROP\nlog_level_in: nolog\n"), BASE, True, id="option-removed"
        ),
        pytest.param(BASE + "\n[ALIASES]\nprom 10.10.10.14\n", BASE, True, id="other-section-removed"),
        pytest.param(
            BASE + "# BEGIN pool\n# a note\n# END pool\n", BASE, True, id="comment-only-managed-block-removed"
        ),
        pytest.param(
            BASE + "# BEGIN pool\nIN ACCEPT -p tcp -dport 81\n# END pool\n", BASE, True, id="managed-block-removed"
        ),
        pytest.param(BASE, BASE + "IN ACCEPT -p tcp -dport 80\n", False, id="rule-added"),
        pytest.param(BASE + "# hand note\n", BASE, False, id="comment-removed"),
        pytest.param(
            BASE, BASE.replace("IN ACCEPT -p tcp -dport 443", "IN   ACCEPT -p  tcp -dport 443"), False, id="spacing"
        ),
        pytest.param(
            BASE + "IN ACCEPT -p tcp -dport 80 # old note\n",
            BASE + "IN ACCEPT -p tcp -dport 80 # new note\n",
            False,
            id="trailing-comment",
        ),
        pytest.param(
            BASE + "IN ACCEPT -p tcp -dport 80\n",
            "[RULES]\nIN ACCEPT -p tcp -dport 80\nIN ACCEPT -p tcp -dport 443\n[OPTIONS]\nenable: 1\npolicy_in: DROP\n",
            False,
            id="reordered",
        ),
        pytest.param(
            BASE + "IN ACCEPT -p tcp -dport 80\nIN ACCEPT -p tcp -dport 80\n",
            BASE + "IN ACCEPT -p tcp -dport 80\n",
            False,
            id="duplicate-in-live",
        ),
        pytest.param(
            BASE + "# BEGIN pool\nIN ACCEPT -p tcp -dport 81\n# END pool\n",
            BASE + "# BEGIN pool\nIN ACCEPT -p tcp -dport 81\n# END pool\n",
            False,
            id="block-kept-by-the-render",
        ),
    ],
)
def test_what_counts_as_a_removal(tmp_path: Path, live: str, render: str, removes: bool) -> None:
    plan = _plan_text(live, render, tmp_path)

    assert plan.removes is removes
    assert (plan.state == "removes") is removes


def test_a_section_is_part_of_the_identity_of_a_line(tmp_path: Path) -> None:
    """The same text in another section is another line: moving a rule into a group is a removal from [RULES]."""
    plan = _plan_text(
        BASE, "[OPTIONS]\nenable: 1\npolicy_in: DROP\n\n[group web]\nIN ACCEPT -p tcp -dport 443\n", tmp_path
    )

    assert [line.text for line in plan.removed] == ["IN ACCEPT -p tcp -dport 443"]


def test_a_missing_or_empty_render_is_an_error_not_an_empty_desired_state(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    live, stage, _ = _stage(tmp_path, [140])
    (stage / ".lv3-vm-140.fw").write_text("# nothing\n")
    before = _tree(live)

    assert guard.main(["apply", "140", "--live-dir", str(live), "--stage-dir", str(stage)]) == guard.EXIT_ERROR
    assert guard.main(["apply", "999", "--live-dir", str(live), "--stage-dir", str(stage)]) == guard.EXIT_ERROR
    assert "no rule or option line" in capsys.readouterr().err
    assert _tree(live) == before


def test_a_failed_write_puts_the_files_already_written_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    live, stage, _ = _stage(tmp_path, [140, 155])
    original_140 = (live / "140.fw").read_text()
    real_copy = shutil.copyfile
    calls = []

    def flaky(src, dst, *args, **kwargs):
        calls.append(dst)
        if len(calls) == 2:
            raise OSError("pmxcfs went away")
        return real_copy(src, dst, *args, **kwargs)

    monkeypatch.setattr(guard.shutil, "copyfile", flaky)
    plans = [guard.plan_vm(vmid, live, stage) for vmid in (140, 155)]

    with pytest.raises(OSError, match="pmxcfs"):
        guard.install(plans)

    assert (live / "140.fw").read_text() == original_140
    assert not (live / "155.fw").exists()


def test_the_script_runs_standalone_and_exits_2_on_a_removal(tmp_path: Path) -> None:
    """The role runs it as `python3 pve_fw_guard.py ...` on the hypervisor: status and stdout are its whole interface."""
    live, stage, _ = _stage(tmp_path, [191])

    result = subprocess.run(
        [
            sys.executable,
            str(GUARD),
            "plan",
            "191",
            "--live-dir",
            str(live),
            "--stage-dir",
            str(stage),
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2, result.stderr
    assert json.loads(result.stdout)["refused"] is True


# --- the role: what the tasks do ----------------------------------------------------------------------------------------------


def _tasks() -> dict[str, dict]:
    return {task["name"]: task for task in yaml.safe_load(TASKS.read_text(encoding="utf-8"))}


def _task_names() -> list[str]:
    return [task["name"] for task in yaml.safe_load(TASKS.read_text(encoding="utf-8"))]


def test_check_mode_compares_a_fresh_render_with_the_live_directory() -> None:
    tasks = _tasks()
    render = tasks["Render per-guest Proxmox firewall policy to staging files"]
    plan = tasks["Compare per-guest Proxmox firewall policy with the live files"]

    # the render is written even in --check so the comparison tests what the real run would install, not a stale copy
    assert render["check_mode"] is False and render["diff"] is False
    assert plan["check_mode"] is False, "the comparison is read only and must run in --check mode"
    command = plan["ansible.builtin.script"]["cmd"]
    assert "pve_fw_guard.py plan" in command and "--live-dir {{ proxmox_network_firewall_live_dir | quote }}" in command
    assert plan["failed_when"] == "proxmox_network_vm_firewall_plan.rc not in [0, 2]"


def test_check_mode_asks_which_guests_exist_instead_of_assuming_all_do() -> None:
    """A skipped command reports rc 0 (seen with --check on 2026-10-30), so without this a check run plans files for guests the real run skips."""
    read = _tasks()["Read current guest configurations for firewall enablement"]

    assert read["check_mode"] is False
    assert read["ansible.builtin.command"] == "qm config {{ item.vmid }}", "it must stay a read"


def test_the_firewall_file_tasks_use_the_selected_guests_not_every_existing_guest() -> None:
    tasks = _tasks()
    render = tasks["Render per-guest Proxmox firewall policy to staging files"]
    plan = tasks["Compare per-guest Proxmox firewall policy with the live files"]
    install = tasks["Install per-guest Proxmox firewall policy"]

    assert render["loop"] == "{{ proxmox_network_firewall_guests }}"
    for task in (plan, install):
        assert "proxmox_network_firewall_guests | map(attribute='vmid')" in task["ansible.builtin.script"]["cmd"]
        assert task["when"] == "proxmox_network_firewall_guests | length > 0"
    defaults = yaml.safe_load(DEFAULTS.read_text(encoding="utf-8"))
    assert defaults["proxmox_network_firewall_vmids"] == [], "the default manages every existing guest"


def test_the_guard_runs_in_this_order_before_the_install_and_the_install_cannot_run_in_check_mode() -> None:
    names = _task_names()
    tasks = _tasks()
    order = [
        "Render per-guest Proxmox firewall policy to staging files",
        "Compare per-guest Proxmox firewall policy with the live files",
        "Show per-guest Proxmox firewall diff against the live files",
        "Refuse to remove live Proxmox firewall rules without an explicit operator decision",
        "Install per-guest Proxmox firewall policy",
        "Show where the replaced Proxmox firewall files were saved",
        "Compile Proxmox firewall configuration",
    ]
    assert [names.index(name) for name in order] == sorted(names.index(name) for name in order)
    refuse = tasks[order[3]]["ansible.builtin.assert"]
    assert refuse["that"] == ["not (proxmox_network_vm_firewall_plan.stdout | from_json).refused"]
    assert ALLOW_VARIABLE in refuse["fail_msg"] and "nothing was written" in refuse["fail_msg"].lower()
    install = tasks["Install per-guest Proxmox firewall policy"]
    assert "check_mode" not in install, "the script module is skipped in --check mode only while nobody overrides it"
    assert "pve_fw_guard.py apply" in install["ansible.builtin.script"]["cmd"]
    assert (
        "--backup-root {{ proxmox_network_firewall_backup_root | quote }}" in install["ansible.builtin.script"]["cmd"]
    )
    assert install["failed_when"] == "proxmox_network_vm_firewall_install.rc != 0"


def test_both_script_calls_pass_the_operator_variable_and_nothing_else_does() -> None:
    tasks = _tasks()
    for name in (
        "Compare per-guest Proxmox firewall policy with the live files",
        "Install per-guest Proxmox firewall policy",
    ):
        command = tasks[name]["ansible.builtin.script"]["cmd"]
        assert f"'--allow-rule-removal' if {ALLOW_VARIABLE} | bool else ''" in command, name
    defaults = yaml.safe_load(DEFAULTS.read_text(encoding="utf-8"))
    options = yaml.safe_load(SPECS.read_text(encoding="utf-8"))["argument_specs"]["main"]["options"]
    assert defaults[ALLOW_VARIABLE] is False, "removal is never the default"
    assert options[ALLOW_VARIABLE]["default"] is False and options[ALLOW_VARIABLE]["type"] == "bool"
    for variable in (
        "proxmox_network_firewall_live_dir",
        "proxmox_network_firewall_stage_dir",
        "proxmox_network_firewall_backup_root",
    ):
        assert options[variable]["default"] == defaults[variable]
    assert ALLOW_VARIABLE not in "\n".join(
        path.read_text(encoding="utf-8") for path in (REPO / "inventory").rglob("*.yml")
    ), "the variable is passed on the command line for one run, never committed in an inventory"


def test_no_task_copies_a_render_over_a_live_file_any_more() -> None:
    text = TASKS.read_text(encoding="utf-8")

    assert 'cp "$staged"' not in text and "cmp -s" not in text
    for task in yaml.safe_load(text):
        body = json.dumps(task)
        if "proxmox_network_firewall_live_dir" in body or "/etc/pve/firewall" in body:
            assert task["name"] in {
                "Ensure Proxmox firewall configuration directory exists",
                "Compare per-guest Proxmox firewall policy with the live files",
                "Install per-guest Proxmox firewall policy",
            }, f"{task['name']!r} touches the live firewall directory outside the guard"


# --- the whole role, run by ansible-playbook against a temporary "live" directory ------------------------------------------


LIVE_WITH_EXTRAS = """[OPTIONS]
enable: 1
policy_in: DROP
policy_out: ACCEPT

[RULES]
# hand-authored: Prometheus scrape of node_exporter
IN ACCEPT -source 10.10.10.77/32 -p tcp -dport 9100 # prometheus
IN ACCEPT -p tcp -dport 443
IN ACCEPT -source 10.10.10.2/32 -p tcp -dport 22
# BEGIN fleet-pool-fw
IN ACCEPT -source 10.10.10.30/32 -p tcp -dport 8443
# END fleet-pool-fw
"""
LIVE_SUBSET = "[OPTIONS]\nenable: 1\npolicy_in: DROP\npolicy_out: ACCEPT\n\n[RULES]\nIN ACCEPT -p tcp -dport 443\n"

PLAY_VARS = {
    "management_interface": "enp7s0",
    "management_ipv4": "10.250.0.2",
    "management_gateway4": "10.250.0.1",
    "proxmox_wan_bridge": "vmbr0",
    "proxmox_internal_bridge": "vmbr1",
    "proxmox_internal_ipv4": "10.10.10.1",
    "proxmox_internal_network": "10.10.10.0/24",
    "platform_identity": {"config_prefix": "lv3"},
    "platform_config_prefix": "lv3",
    "proxmox_guests": [
        {"name": "edge", "vmid": 191, "ipv4": "10.10.10.91"},
        {"name": "store", "vmid": 155, "ipv4": "10.10.10.55"},
        {"name": "not-created-yet", "vmid": 999, "ipv4": "10.10.10.99"},
    ],
    "network_policy": {
        "host_source": "10.10.10.1/32",
        "guest_management_sources": ["10.10.10.2/32"],
        "guests": {
            "edge": {
                "allowed_inbound": [
                    {"source": "public", "protocol": "tcp", "ports": [443]},
                    {"source": "management", "protocol": "tcp", "ports": [22]},
                ]
            },
            "store": {"allowed_inbound": [{"source": "host", "protocol": "tcp", "ports": [9100]}]},
            "not-created-yet": {"allowed_inbound": [{"source": "public", "protocol": "tcp", "ports": [1]}]},
        },
    },
}

needs_ansible = pytest.mark.skipif(shutil.which("ansible-playbook") is None, reason="ansible-playbook is not installed")


class Hypervisor:
    """A temporary stand-in for the Proxmox host: a live firewall dir, a staging dir, a backup root and `qm`/`pve-firewall` shims."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.live, self.stage, self.backup, self.shims = (root / name for name in ("live", "stage", "backup", "shims"))
        for directory in (self.live, self.stage, self.backup, self.shims):
            directory.mkdir()
        self.log = root / "pve-firewall.log"
        self._write_shim(
            "qm",
            '#!/bin/sh\n[ "$1" = config ] && { [ "$2" = 191 ] || [ "$2" = 155 ]; } && echo "net0: virtio=BC:24:11:00:00:01,bridge=vmbr1,firewall=1" && exit 0\nexit 2\n',
        )
        self._write_shim("pve-firewall", f'#!/bin/sh\necho "$*" >> {self.log}\n')
        (root / "vars.yml").write_text(
            yaml.safe_dump(
                {
                    **PLAY_VARS,
                    "proxmox_network_firewall_live_dir": str(self.live),
                    "proxmox_network_firewall_stage_dir": str(self.stage),
                    "proxmox_network_firewall_backup_root": str(self.backup),
                }
            )
        )
        (root / "play.yml").write_text(
            yaml.safe_dump(
                [
                    {
                        "hosts": "localhost",
                        "connection": "local",
                        "gather_facts": False,
                        "vars_files": ["vars.yml"],
                        "roles": ["lv3.platform.proxmox_network"],
                    }
                ]
            )
        )
        (root / "ansible.cfg").write_text(
            f"[defaults]\ncollections_path = {REPO / 'collections'}\nlocalhost_warning = False\nhost_key_checking = False\n"
            "interpreter_python = auto_silent\nretry_files_enabled = False\ndeprecation_warnings = False\n"
        )

    def _write_shim(self, name: str, body: str) -> None:
        (self.shims / name).write_text(body)
        (self.shims / name).chmod(0o755)

    def firewall_calls(self) -> list[str]:
        return self.log.read_text().splitlines() if self.log.exists() else []

    def play(self, *flags: str) -> subprocess.CompletedProcess[str]:
        env = {
            **os.environ,
            "PATH": f"{self.shims}:{os.environ['PATH']}",
            "ANSIBLE_CONFIG": str(self.root / "ansible.cfg"),
            "ANSIBLE_HOME": str(self.root / "ansible-home"),
            "ANSIBLE_NOCOLOR": "1",
            "ANSIBLE_STDOUT_CALLBACK": "default",
        }
        return subprocess.run(
            ["ansible-playbook", "-i", "localhost,", "play.yml", "--tags", "proxmox-vm-firewall", *flags],
            cwd=self.root,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )

    def live_files(self) -> dict[str, str]:
        return _tree(self.live)


@pytest.fixture
def hypervisor(tmp_path: Path) -> Hypervisor:
    return Hypervisor(tmp_path)


@needs_ansible
def test_check_mode_fails_on_a_removal_shows_the_live_diff_and_writes_nothing(hypervisor: Hypervisor) -> None:
    (hypervisor.live / "191.fw").write_text(LIVE_WITH_EXTRAS)
    before = hypervisor.live_files()

    result = hypervisor.play("--check", "--diff")

    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert "!! REMOVED [RULES] IN ACCEPT -source 10.10.10.77/32 -p tcp -dport 9100 # prometheus" in output
    assert "REMOVED managed block '# BEGIN fleet-pool-fw'" in output
    assert "REFUSED, nothing was written" in output
    assert f"-e {ALLOW_VARIABLE}=true" in output
    assert hypervisor.live_files() == before and not (hypervisor.live / "155.fw").exists()
    assert list(hypervisor.backup.iterdir()) == []
    assert hypervisor.firewall_calls() == []
    # the staging copy is rendered in --check so that the comparison is against what the real run installs
    assert "IN ACCEPT -p tcp -dport 443" in (hypervisor.stage / ".lv3-vm-191.fw").read_text()
    assert not (hypervisor.stage / ".lv3-vm-999.fw").exists(), "a guest that does not exist on the host gets no file"


@needs_ansible
def test_a_real_run_fails_the_same_way_before_it_writes_anything(hypervisor: Hypervisor) -> None:
    (hypervisor.live / "191.fw").write_text(LIVE_WITH_EXTRAS)
    before = hypervisor.live_files()

    result = hypervisor.play()

    assert result.returncode != 0, result.stdout + result.stderr
    assert "REFUSED, nothing was written" in result.stdout + result.stderr
    assert hypervisor.live_files() == before and not (hypervisor.live / "155.fw").exists(), (
        "VM 155 is additive but waits for VM 191"
    )
    assert list(hypervisor.backup.iterdir()) == [] and hypervisor.firewall_calls() == []


@needs_ansible
def test_the_operator_variable_backs_up_installs_and_prints_the_restore_command(hypervisor: Hypervisor) -> None:
    (hypervisor.live / "191.fw").write_text(LIVE_WITH_EXTRAS)

    result = hypervisor.play("-e", f"{ALLOW_VARIABLE}=true")

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    (saved,) = hypervisor.backup.iterdir()
    assert saved.name.startswith("fw-backup-")
    assert (saved / "191.fw").read_text() == LIVE_WITH_EXTRAS
    assert f"sh {saved}/restore.sh" in output
    assert (hypervisor.live / "191.fw").read_text() == (hypervisor.stage / ".lv3-vm-191.fw").read_text()
    assert "hand-authored" not in (hypervisor.live / "191.fw").read_text()
    assert (hypervisor.live / "155.fw").is_file()
    assert hypervisor.firewall_calls() == ["compile", "restart"]


@needs_ansible
def test_an_additive_run_installs_a_new_vm_file_and_a_second_run_changes_nothing(hypervisor: Hypervisor) -> None:
    (hypervisor.live / "191.fw").write_text(LIVE_SUBSET)

    check = hypervisor.play("--check", "--diff")

    assert check.returncode == 0, check.stdout + check.stderr
    assert "VM 155" in check.stdout and "NEW file" in check.stdout
    assert hypervisor.live_files() == {"191.fw": LIVE_SUBSET}, "check mode installs nothing"
    assert list(hypervisor.backup.iterdir()) == []

    first = hypervisor.play()

    assert first.returncode == 0, first.stdout + first.stderr
    assert set(hypervisor.live_files()) == {"155.fw", "191.fw"}
    (saved,) = hypervisor.backup.iterdir()
    assert (saved / "191.fw").read_text() == LIVE_SUBSET and not (saved / "155.fw").exists()
    assert hypervisor.firewall_calls() == ["compile", "restart"]

    second = hypervisor.play()

    assert second.returncode == 0, second.stdout + second.stderr
    assert len(list(hypervisor.backup.iterdir())) == 1, "an unchanged render takes no backup"
    assert hypervisor.firewall_calls() == ["compile", "restart", "compile"], "and does not restart pve-firewall"


@needs_ansible
def test_naming_the_additive_vm_installs_it_while_another_vm_still_holds_extra_live_rules(
    hypervisor: Hypervisor,
) -> None:
    """VM 155's new file goes in through the slice although VM 191's live file is not a subset of its render."""
    (hypervisor.live / "191.fw").write_text(LIVE_WITH_EXTRAS)

    check = hypervisor.play("--check", "--diff", "-e", "proxmox_network_firewall_vmids=155")
    real = hypervisor.play("-e", '{"proxmox_network_firewall_vmids": [155]}')

    assert check.returncode == 0, check.stdout + check.stderr
    assert real.returncode == 0, real.stdout + real.stderr
    assert hypervisor.live_files()["191.fw"] == LIVE_WITH_EXTRAS, "an unnamed VM is not touched, not even looked at"
    assert (hypervisor.live / "155.fw").read_text() == (hypervisor.stage / ".lv3-vm-155.fw").read_text()
    assert not (hypervisor.stage / ".lv3-vm-191.fw").exists()
    (saved,) = hypervisor.backup.iterdir()
    assert sorted(path.name for path in saved.iterdir()) == ["restore.sh"], (
        "VM 155 had no file, so there is only the restore script"
    )
    assert "rm -f" in (saved / "restore.sh").read_text() and "155.fw" in (saved / "restore.sh").read_text()
    assert hypervisor.firewall_calls() == ["compile", "restart"]


@needs_ansible
def test_naming_a_guest_that_does_not_exist_fails_instead_of_doing_nothing(hypervisor: Hypervisor) -> None:
    result = hypervisor.play("-e", "proxmox_network_firewall_vmids=155,999")

    assert result.returncode != 0
    assert "proxmox_network_firewall_vmids names 155,999" in result.stdout + result.stderr
    assert hypervisor.live_files() == {} and list(hypervisor.backup.iterdir()) == []
