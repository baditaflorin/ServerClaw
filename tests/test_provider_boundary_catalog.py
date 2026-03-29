from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module():
    scripts_dir = REPO_ROOT / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    module_path = scripts_dir / "provider_boundary_catalog.py"
    spec = importlib.util.spec_from_file_location("provider_boundary_catalog", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_provider_boundary_catalog_validates_repo_contract() -> None:
    module = load_module()

    _catalog, normalized = module.load_provider_boundary_catalog()

    assert [entry["boundary_id"] for entry in normalized] == [
        "hetzner_dns_single_record",
        "hetzner_dns_zone_records",
    ]


def test_validation_paths_run_provider_boundary_catalog_check() -> None:
    validate_gate = (REPO_ROOT / "config" / "validation-gate.json").read_text(encoding="utf-8")
    validate_script = (REPO_ROOT / "scripts" / "validate_repo.sh").read_text(encoding="utf-8")

    assert "scripts/provider_boundary_catalog.py --validate" in validate_gate
    assert "scripts/provider_boundary_catalog.py\" --validate" in validate_script
