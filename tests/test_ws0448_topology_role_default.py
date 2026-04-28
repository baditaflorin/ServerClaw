"""Test for ADR 0448 — `proxmox_guests[*].role` defaults to `name`.

A per-deployment `topology.yml` overlay was previously rejected by
`generate_platform_vars.build_guest_catalog` when `role` was missing.
ADR 0448 relaxes the loader so `role` defaults to `name`. This test
locks the behavior in.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATE_SCRIPT = REPO_ROOT / "scripts" / "generate_platform_vars.py"


def _load_generator_module():
    spec = importlib.util.spec_from_file_location("generate_platform_vars_for_ws0448", GENERATE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["generate_platform_vars_for_ws0448"] = module
    spec.loader.exec_module(module)
    return module


def test_role_defaults_to_name_when_missing():
    mod = _load_generator_module()
    host_vars = {
        "proxmox_guests": [
            {"name": "nginx", "vmid": 110, "ipv4": "10.10.10.10"},  # no role
        ]
    }
    catalog, by_name, ipv4_by_name = mod.build_guest_catalog(host_vars)
    # Role auto-filled from name.
    assert catalog["by_role"]["nginx"]["role"] == "nginx"
    assert by_name["nginx"]["role"] == "nginx"
    assert ipv4_by_name["nginx"] == "10.10.10.10"


def test_role_preserved_when_explicit():
    mod = _load_generator_module()
    host_vars = {
        "proxmox_guests": [
            {"name": "edge-1", "role": "nginx", "vmid": 110, "ipv4": "10.10.10.10"},
        ]
    }
    catalog, _, _ = mod.build_guest_catalog(host_vars)
    # Explicit role wins; auto-fill does not overwrite.
    assert catalog["by_role"]["nginx"]["role"] == "nginx"
    # `nginx` indexed by role, not by name.
    assert "edge-1" not in catalog["by_role"]


def test_name_still_required():
    mod = _load_generator_module()
    host_vars = {"proxmox_guests": [{"vmid": 110, "ipv4": "10.10.10.10"}]}
    with pytest.raises((mod.RuntimeError if hasattr(mod, "RuntimeError") else Exception, ValueError)):
        mod.build_guest_catalog(host_vars)
