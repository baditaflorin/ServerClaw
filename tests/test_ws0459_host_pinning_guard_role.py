"""Tests for ADR 0457 Phase 2 — host_pinning_guard role.

Two layers:
  1. Static structure tests that the role exists and exports the
     contract documented in ADR 0457 Phase 2 (defaults + tasks +
     argument_specs all present).
  2. Behavioural tests via ansible-playbook --check on a synthetic
     inventory, asserting that the guard:
       - exits cleanly when both slugs match,
       - exits cleanly when no deployment_owner is set,
       - fails with a remediation message when slugs mismatch,
       - fails strictly when deployment_owner is set but no active
         slug is resolvable.

The behavioural tests pin to `connection: local` and run the role
in-process so they do not require any Ansible infrastructure beyond
ansible-core itself.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_DIR = REPO_ROOT / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / "host_pinning_guard"


# --- structure ------------------------------------------------------------


def test_role_directory_exists():
    assert ROLE_DIR.is_dir(), f"host_pinning_guard role not found at {ROLE_DIR}"


def test_role_has_required_files():
    required = ["tasks/main.yml", "defaults/main.yml", "meta/main.yml", "meta/argument_specs.yml"]
    for rel in required:
        assert (ROLE_DIR / rel).is_file(), f"missing {rel}"


def test_role_referenced_by_public_edge_playbook():
    """Phase 2 only takes effect once a playbook actually invokes the role."""
    playbook = (REPO_ROOT / "playbooks" / "public-edge.yml").read_text()
    assert "lv3.platform.host_pinning_guard" in playbook


def test_role_defaults_kill_switch_present():
    """The kill-switch default must remain `true` to keep the guard
    enforcing by default; an operator who flips it to false in their
    overlay accepts the lv3 ↔ 0fork collision class of bug. Anything
    else is a regression."""
    defaults = (ROLE_DIR / "defaults" / "main.yml").read_text()
    assert "host_pinning_guard_enabled: true" in defaults
    assert "host_pinning_guard_strict: true" in defaults


def test_role_tasks_reference_proxmox_guests():
    tasks = (ROLE_DIR / "tasks" / "main.yml").read_text()
    # Lookup must filter on inventory_hostname against proxmox_guests.
    assert "proxmox_guests" in tasks
    assert "selectattr('name', 'equalto', inventory_hostname)" in tasks


# --- behaviour ------------------------------------------------------------


def _have_ansible_playbook() -> bool:
    return shutil.which("ansible-playbook") is not None


pytestmark = pytest.mark.skipif(
    not _have_ansible_playbook(),
    reason="ansible-playbook not on PATH; behavioural tests skipped",
)


def _write_synthetic_inventory(tmp_path: Path, *, owner: str | None) -> Path:
    """Build a one-host inventory whose proxmox_guests lookup returns
    `owner` (or no entry when owner is None) for the host we converge."""
    guests = []
    if owner is not None:
        guests.append({"name": "fixture", "vmid": 199, "ipv4": "10.10.10.199", "deployment_owner": owner})
    inventory = {
        "all": {
            "hosts": {"fixture": {"ansible_connection": "local", "ansible_host": "localhost"}},
            "vars": {
                "proxmox_guests": guests,
                "repo_shared_local_root": str(tmp_path / "_local"),
            },
        }
    }
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps(inventory))
    (tmp_path / "_local").mkdir(exist_ok=True)
    return path


def _write_playbook(tmp_path: Path) -> Path:
    pb = tmp_path / "play.yml"
    pb.write_text(
        textwrap.dedent(
            """
            - hosts: fixture
              gather_facts: false
              roles:
                - role: lv3.platform.host_pinning_guard
            """
        ).strip()
        + "\n"
    )
    return pb


def _run(tmp_path: Path, *, owner: str | None, active_slug: str | None) -> subprocess.CompletedProcess:
    inventory = _write_synthetic_inventory(tmp_path, owner=owner)
    playbook = _write_playbook(tmp_path)
    extra_vars: dict[str, str] = {}
    if active_slug is not None:
        extra_vars["active_deployment_slug"] = active_slug
    cmd = [
        "ansible-playbook",
        "-i",
        str(inventory),
        str(playbook),
    ]
    if extra_vars:
        cmd.extend(["-e", json.dumps(extra_vars)])
    env = {
        # Both singular and plural names — Ansible accepts both depending on
        # version; setting both keeps the test portable.
        "ANSIBLE_COLLECTIONS_PATH": str(REPO_ROOT / "collections"),
        "ANSIBLE_COLLECTIONS_PATHS": str(REPO_ROOT / "collections"),
        "ANSIBLE_DEPRECATION_WARNINGS": "False",
        "ANSIBLE_LOCALHOST_WARNING": "False",
        "ANSIBLE_INVENTORY_UNPARSED_WARNING": "False",
        "PATH": __import__("os").environ.get("PATH", ""),
        # Make sure DEPLOYMENT env var doesn't leak into the role from
        # the parent test runner.
        "DEPLOYMENT": "",
        "HOME": str(tmp_path),
    }
    return subprocess.run(cmd, cwd=tmp_path, env=env, capture_output=True, text=True)


def test_guard_passes_when_owner_matches_active(tmp_path):
    result = _run(tmp_path, owner="alpha", active_slug="alpha")
    assert result.returncode == 0, f"stderr={result.stderr}\nstdout={result.stdout}"


def test_guard_passes_when_no_owner(tmp_path):
    result = _run(tmp_path, owner=None, active_slug="alpha")
    assert result.returncode == 0, f"stderr={result.stderr}\nstdout={result.stdout}"


def test_guard_fails_when_owner_mismatches_active(tmp_path):
    result = _run(tmp_path, owner="alpha", active_slug="beta")
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "host_pinning_guard" in combined
    assert "pinned to deployment_owner=alpha" in combined
    assert "active deployment slug is beta" in combined


def test_guard_fails_strict_when_owner_set_but_no_active(tmp_path):
    result = _run(tmp_path, owner="alpha", active_slug=None)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "no active deployment slug was resolvable" in combined
