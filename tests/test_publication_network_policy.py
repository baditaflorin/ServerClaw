"""Public address examples preserve the network policy's existing decisions."""

from __future__ import annotations

import ipaddress
import json
from pathlib import Path
import re
import shutil
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import netpolicy  # noqa: E402
import publish_to_serverclaw as publisher  # noqa: E402

TAILNET = ipaddress.ip_network("100.64.0.0/10")


@pytest.fixture
def private_config():
    if not publisher.CONFIG_PATH.exists():
        pytest.skip("Private sanitization configuration is excluded from the public snapshot")
    return publisher.load_config()


def test_literal_tailnet_examples_keep_their_address_class_and_identity(private_config):
    destinations = []
    public_destinations = set()
    for entry in private_config["string_replacements"]:
        try:
            source = ipaddress.ip_address(entry["pattern"].replace(r"\.", "."))
        except ValueError:
            continue
        destination = ipaddress.ip_address(entry["replacement"])
        if source in TAILNET:
            assert destination in TAILNET, "A Tailnet example became a foreign source"
            destinations.append(destination)
        else:
            assert destination not in TAILNET, "A public example became a Tailnet source"
            public_destinations.add(destination)
    assert destinations
    assert len(set(destinations)) == len(destinations), "Distinct Tailnet identities must stay distinct"
    assert set(destinations).isdisjoint(public_destinations)


@pytest.mark.parametrize("tailnet_example,new_findings", [("100.64.0.3", 0), ("203.0.113.3", 1)])
def test_synthetic_sanitization_retains_foreign_source_enforcement(tmp_path, tailnet_example, new_findings):
    policy = {
        "version": 1,
        "host": "example",
        "ipsets": {},
        "inner_sources": [str(TAILNET)],
        "lan_networks": ["10.10.10.0/24"],
        "vms": {"101": {
            "name": "example",
            "pve": {"enable": "1", "policy_in": "DROP", "policy_out": "ACCEPT"},
            "guest": {"nft": "managed", "input_policy": "drop", "forward_policy": "drop"},
            "groups": [{"from": [source], "proto": "tcp", "ports": ["22"],
                        "layers": ["pve", "input"], "purpose": "Example administrative access"}
                       for source in ("100.120.30.40", "198.51.100.9")],
        }},
    }
    directory = tmp_path / "config" / "network-policy"
    directory.mkdir(parents=True)
    path = directory / "example.yaml"
    path.write_text(yaml.safe_dump(policy, sort_keys=False))
    baseline = path.with_suffix(".baseline.json")
    baseline.write_text(json.dumps([f["id"] for f in netpolicy.check(netpolicy.load_policy(path))
                                    if f["severity"] != "info"]))
    publisher.apply_string_replacements(tmp_path, {"string_replacements": [
        {"pattern": r"100\.120\.30\.40", "replacement": tailnet_example},
        {"pattern": r"198\.51\.100\.9", "replacement": "203.0.113.100"},
    ]})
    findings = netpolicy.check(netpolicy.load_policy(path), set(json.loads(baseline.read_text())))
    unknown = [f for f in findings if f["severity"] != "info" and f["known"] == "no"]
    assert len(unknown) == new_findings
    assert netpolicy.main(["check", "--policy", str(path)]) == int(bool(new_findings))
    assert any(f["known"] == "yes" and f["severity"] == "medium" for f in findings)
    before = baseline.read_bytes()
    if new_findings:
        with pytest.raises(ValueError, match="unaccepted findings"):
            publisher.refresh_network_policy_baselines(tmp_path)
        assert baseline.read_bytes() == before
    else:
        publisher.refresh_network_policy_baselines(tmp_path)
        assert baseline.read_bytes() == before


def test_actual_sanitized_policies_keep_findings_without_expanding_baselines(tmp_path, private_config):
    source = ROOT / "config" / "network-policy"
    before = {path: path.read_bytes() for path in source.iterdir() if path.is_file()}
    exported = tmp_path / "export"
    target = exported / "config" / "network-policy"
    shutil.copytree(source, target)
    publisher.apply_string_replacements(exported, private_config)
    accepted_before = {path: set(json.loads(path.read_text())) for path in target.glob("*.baseline.json")}
    publisher.refresh_network_policy_baselines(exported)
    for path in sorted(target.glob("*.yaml")):
        original = netpolicy.load_policy(source / path.name)
        sanitized = netpolicy.load_policy(path)
        assert netpolicy.main(["check", "--policy", str(path)]) == 0
        accepted = set(json.loads(path.with_suffix(".baseline.json").read_text()))
        assert accepted <= accepted_before[path.with_suffix(".baseline.json")]
        actual = {f["id"] for f in netpolicy.check(sanitized) if f["severity"] != "info"}
        expected = json.dumps([f["id"] for f in netpolicy.check(original) if f["severity"] != "info"])
        for entry in private_config["string_replacements"]:
            expected = re.sub(entry["pattern"], entry["replacement"], expected)
        # Existing LAN-example mapping can collapse old foreign-source findings.
        # Sanitization must not introduce any new security finding.
        assert actual <= set(json.loads(expected))
        assert accepted <= actual, "Fixed findings must still leave the exported baseline"
    assert {path: path.read_bytes() for path in before} == before


def baseline_fixture(root):
    directory = root / "config" / "network-policy"
    directory.mkdir(parents=True)
    policy = directory / "example.yaml"
    policy.write_text("version: 1\nhost: example\nipsets: {}\nvms: {}\n")
    baseline = policy.with_suffix(".baseline.json")
    baseline.write_text('["101:foreign-source:198.51.100.1"]\n')
    return baseline


def test_baseline_pruning_is_idempotent_and_does_not_write_private_bytes(tmp_path):
    private = tmp_path / "private"
    original = baseline_fixture(private)
    before = original.read_bytes()
    exported = tmp_path / "export"
    shutil.copytree(private, exported)
    target = exported / original.relative_to(private)
    publisher.refresh_network_policy_baselines(exported)
    assert json.loads(target.read_text()) == []
    first = target.read_bytes()
    publisher.refresh_network_policy_baselines(exported)
    assert target.read_bytes() == first
    assert original.read_bytes() == before


@pytest.mark.parametrize("alias", ["ancestor", "baseline_symlink", "baseline_hardlink", "source_root"])
def test_baseline_refresh_refuses_private_aliases(tmp_path, monkeypatch, alias):
    private = tmp_path / "private"
    original = baseline_fixture(private)
    before = original.read_bytes()
    exported = tmp_path / "export"
    if alias == "ancestor":
        exported.mkdir()
        (exported / "config").symlink_to(private / "config", target_is_directory=True)
    elif alias == "source_root":
        monkeypatch.setattr(publisher, "REPO_ROOT", private)
        exported = private
    else:
        shutil.copytree(private, exported)
        target = exported / original.relative_to(private)
        target.unlink()
        if alias == "baseline_symlink":
            target.symlink_to(original)
        else:
            import os
            os.link(original, target)
    with pytest.raises(ValueError):
        publisher.refresh_network_policy_baselines(exported)
    assert original.read_bytes() == before


@pytest.mark.parametrize("malformed", [{}, [1], ["duplicate", "duplicate"]])
def test_all_baselines_validate_before_any_pruning(tmp_path, malformed):
    first = baseline_fixture(tmp_path)
    before = first.read_bytes()
    second = first.parent / "later.yaml"
    # Ensure the valid/prunable policy is visited before the invalid baseline.
    first.rename(first.with_name("a.baseline.json"))
    first.with_name("example.yaml").rename(first.with_name("a.yaml"))
    first = first.with_name("a.baseline.json")
    second.write_text("version: 1\nhost: example\nipsets: {}\nvms: {}\n")
    second.with_suffix(".baseline.json").write_text(json.dumps(malformed))
    with pytest.raises(ValueError, match="Invalid public network baseline"):
        publisher.refresh_network_policy_baselines(tmp_path)
    assert first.read_bytes() == before


@pytest.mark.parametrize("problem", ["new_finding", "missing_policy", "missing_baseline", "malformed_policy"])
def test_later_policy_failure_prevents_earlier_pruning(tmp_path, problem):
    first = baseline_fixture(tmp_path)
    before = first.read_bytes()
    later = first.parent / "z.yaml"
    baseline = later.with_suffix(".baseline.json")
    later.write_text("version: 1\nhost: example\nipsets: {}\nvms: {}\n")
    baseline.write_text("[]\n")
    if problem == "new_finding":
        later.write_text("version: 1\nhost: example\nipsets: {}\nvms:\n  '102':\n    name: later\n    pve: {}\n    guest: {nft: absent}\n    groups: []\n")
    elif problem == "missing_policy":
        later.unlink()
    elif problem == "missing_baseline":
        baseline.unlink()
    else:
        later.write_text("not: [valid\n")
    with pytest.raises((ValueError, yaml.YAMLError)):
        publisher.refresh_network_policy_baselines(tmp_path)
    assert first.read_bytes() == before
