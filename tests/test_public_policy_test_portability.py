"""Exercise the public test boundary without copying any deployment policy."""
from __future__ import annotations

import ipaddress
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

from policy_test_sources import copy_source, source_bytes


ROOT = Path(__file__).resolve().parents[1]
MODULES = (
    "test_tier0_domainscope_path.py", "test_dockerhost_pbs_relay.py",
    "test_standby_edge_grants_job.py", "test_standby_edge_grants.py",
    "test_tier0_edge_grants_wrapper.py", "test_tier0_edge_grants_install.py",
)


def test_existing_deployment_inputs_remain_byte_identical(tmp_path: Path) -> None:
    for name in ("policy.hujson", "lockout-guard.json"):
        relative = f"config/tailscale/{name}"
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        contents = f"existing deployment {name}\n".encode()
        path.write_bytes(contents)
        path.chmod(0o640)
        assert source_bytes(tmp_path, relative) == contents
        destination = tmp_path / f"copied-{name}"
        copy_source(tmp_path, relative, destination)
        assert destination.read_bytes() == contents
        assert destination.stat().st_mode & 0o777 == 0o640
    with pytest.raises(FileNotFoundError):
        source_bytes(tmp_path, "unrelated-missing-file")


def test_standby_fixture_contains_documentation_addresses_only() -> None:
    text = (ROOT / "tests/fixtures/tailscale/standby-job-policy.hujson").read_text()
    networks = [ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")]
    addresses = re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text)
    assert addresses
    assert all(any(ipaddress.ip_address(address) in network for network in networks) for address in addresses)


@pytest.mark.parametrize("has_policy,private_source,expected", [(True, True, 0), (False, False, 0), (False, True, 1)])
def test_ci_keeps_private_policy_check_and_public_fixture_checks(tmp_path: Path, has_policy: bool, private_source: bool, expected: int) -> None:
    commands = yaml.safe_load((ROOT / ".woodpecker.yml").read_text())["steps"]["validate-tailscale-policy"]["commands"]
    check = next(command for command in commands if "scripts/tailscale_policy_sync.py check" in command)
    assert any("tests/test_tailscale_policy_sync.py tests/test_tailscale_policy_reconcile.py" in command for command in commands)
    (tmp_path / "config/tailscale").mkdir(parents=True)
    if has_policy:
        (tmp_path / "config/tailscale/policy.hujson").write_text("fixture")
    if private_source:
        (tmp_path / "config/publication-sanitization.yaml").write_text("fixture")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    python = bin_dir / "python3"
    python.write_text('#!/bin/sh\nprintf "%s\\n" "$*" > "$POLICY_CHECK_CALLS"\n')
    python.chmod(0o755)
    calls = tmp_path / "calls"
    result = subprocess.run(["sh", "-c", check], cwd=tmp_path, capture_output=True, text=True,
                            env=dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}", POLICY_CHECK_CALLS=str(calls)))
    assert result.returncode == expected, result.stdout + result.stderr
    assert calls.exists() == has_policy
    if has_policy:
        assert calls.read_text().strip() == "scripts/tailscale_policy_sync.py check"


def test_without_deployment_policy_portable_cases_execute_and_only_deployment_checks_skip(tmp_path: Path) -> None:
    paths = [f"tests/{name}" for name in MODULES] + [
        "tests/policy_test_sources.py", "tests/fixtures/tailscale",
        "scripts/standby_edge_grants.py", "scripts/standby_edge_grants_job.py",
        "scripts/tailscale_policy_sync.py", "scripts/tailscale_policy_reconcile.py",
        "scripts/tier0-edge-grants-install.sh", "config/ct108/tier0-edge-grants",
        "config/0infer/tier0-runner/host/infer-domainscope-standby.nft",
        "config/0infer/tier0-runner/gateway-extra.json", "config/0infer/tier0-runner/install.sh",
        "config/0infer/tier0-runner/host/standby-ctl.json", "config/0docker/dockerhost-pbs-relay",
        "config/0docker/dockerhost-state-backup/config.json",
    ]
    for relative in paths:
        source, destination = ROOT / relative, tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            shutil.copy(source, destination)
    (tmp_path / "tests/conftest.py").write_text(
        "import sys\nfrom pathlib import Path\nr=Path(__file__).resolve().parents[1]\n"
        "sys.path[:0]=[str(r/'scripts'),str(r/'tests')]\n"
    )
    assert not (tmp_path / "config/tailscale").exists()
    collect = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *[f"tests/{name}" for name in MODULES]],
        cwd=tmp_path, capture_output=True, text=True, timeout=120,
    )
    assert collect.returncode == 0, collect.stdout + collect.stderr
    portable = (
        "test_tier0_domainscope_path.py::test_nft_is_one_dnat_rule_from_one_address_to_one_vm_on_two_ports",
        "test_dockerhost_pbs_relay.py::test_the_unit_loads_and_removes_only_its_own_table",
        "test_standby_edge_grants_job.py::test_listening_means_reachable_over_the_tailnet_not_bound_to_loopback",
        "test_standby_edge_grants_job.py::test_a_port_closed_for_two_runs_and_listening_becomes_a_merged_pr_with_additions_only",
        "test_standby_edge_grants.py::test_consecutive_needed_ports_become_ranges_and_nothing_else_does",
        "test_tier0_edge_grants_wrapper.py::test_the_installed_job_runs_against_a_sparse_clone_and_its_result_and_exit_code_come_through",
        "test_tier0_edge_grants_install.py::test_install_puts_the_files_identical_to_main_in_place_with_the_right_modes_and_reloads_systemd",
    )
    deployment = (
        "test_tier0_domainscope_path.py::test_the_tailnet_grant_covers_exactly_the_nft_rule",
        "test_dockerhost_pbs_relay.py::test_the_hypervisors_tailnet_identity_still_has_the_grant_the_relay_depends_on",
        "test_standby_edge_grants_job.py::test_the_real_policy_in_this_repo_has_exactly_one_of_each_marker_and_both_sit_inside_their_arrays",
        "test_standby_edge_grants.py::test_the_committed_policy_grants_every_port_the_measurement_found_closed_and_tests_each_one",
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--junitxml=result.xml", *[f"tests/{case}" for case in portable + deployment]],
        cwd=tmp_path, capture_output=True, text=True, timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    cases = ET.parse(tmp_path / "result.xml").findall(".//testcase")
    skipped = [case for case in cases if case.find("skipped") is not None]
    assert len(cases) == len(portable) + len(deployment)
    assert len(skipped) == len(deployment)
    assert {case.attrib["name"] for case in skipped} == {case.split("::")[1] for case in deployment}
