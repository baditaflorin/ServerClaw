from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_makefile_and_playbook_wire_the_control_loop_target() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    playbook = (REPO_ROOT / "playbooks" / "proxmox-install.yml").read_text(encoding="utf-8")

    assert "configure-host-control-loops" in makefile
    assert "WORKFLOW=configure-host-control-loops" in makefile
    assert "--tags control-loops" in makefile
    assert "lv3.platform.proxmox_host_control_loops" in playbook
    assert "- control-loops" in playbook


def test_workflow_catalog_registers_host_control_loops() -> None:
    workflows = json.loads((REPO_ROOT / "config" / "workflow-catalog.json").read_text(encoding="utf-8"))["workflows"]
    workflow = workflows["configure-host-control-loops"]

    assert workflow["preferred_entrypoint"]["target"] == "configure-host-control-loops"
    assert workflow["owner_runbook"] == "docs/runbooks/configure-host-control-loops.md"
    assert workflow["live_impact"] == "host_live"
    assert "roles/proxmox_host_control_loops/tasks/main.yml" in workflow["implementation_refs"]


def test_role_renders_service_timer_and_path_units() -> None:
    tasks = (REPO_ROOT / "roles" / "proxmox_host_control_loops" / "tasks" / "main.yml").read_text(encoding="utf-8")
    defaults = (REPO_ROOT / "roles" / "proxmox_host_control_loops" / "defaults" / "main.yml").read_text(
        encoding="utf-8"
    )
    service = (
        REPO_ROOT / "roles" / "proxmox_host_control_loops" / "templates" / "lv3-host-control-loop-reconcile.service.j2"
    ).read_text(encoding="utf-8")
    timer = (
        REPO_ROOT / "roles" / "proxmox_host_control_loops" / "templates" / "lv3-host-control-loop-reconcile.timer.j2"
    ).read_text(encoding="utf-8")
    path_unit = (
        REPO_ROOT / "roles" / "proxmox_host_control_loops" / "templates" / "lv3-host-control-loop-reconcile.path.j2"
    ).read_text(encoding="utf-8")
    script = (
        REPO_ROOT / "roles" / "proxmox_host_control_loops" / "templates" / "lv3-host-control-loop-reconcile.py.j2"
    ).read_text(encoding="utf-8")

    assert "proxmox_host_control_loops_timer_on_calendar: \"*:0/30\"" in defaults
    assert "Render the host control-loop systemd path unit" in tasks
    assert "common_systemd_unit_name: \"{{ proxmox_host_control_loops_timer_name }}\"" in tasks
    assert "Type=oneshot" in service
    assert "Restart=on-failure" in service
    assert "TimeoutStartSec={{ proxmox_host_control_loops_timeout_start_seconds }}" in service
    assert "ReadWritePaths={{ proxmox_host_control_loops_root }}" in service
    assert "OnCalendar={{ proxmox_host_control_loops_timer_on_calendar }}" in timer
    assert "Unit={{ proxmox_host_control_loops_service_name }}" in timer
    assert "PathExists={{ proxmox_host_control_loops_reconcile_request_path }}" in path_unit
    assert "path_request" in script
    assert "_write_json(args.status_file, payload)" in script
