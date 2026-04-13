from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    module_path = REPO_ROOT / relative_path
    scripts_dir = REPO_ROOT / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_load_adr_index_prefers_canonical_entry_over_auxiliary_duplicates(tmp_path: Path, monkeypatch) -> None:
    module = load_module("adr_implementation_scanner_test", "scripts/adr_implementation_scanner.py")
    adr_dir = tmp_path / "docs" / "adr"
    shard_dir = adr_dir / "index" / "by-range"
    shard_dir.mkdir(parents=True)
    (adr_dir / ".index.yaml").write_text("schema_version: 2\n", encoding="utf-8")
    payload = {
        "schema_version": 2,
        "adrs": [
            {
                "adr": "0025",
                "title": "Compose-Managed Runtime Stacks",
                "status": "Accepted",
                "implementation_status": "Implemented",
                "filename": "0025-compose-managed-runtime-stacks.md",
                "path": "docs/adr/0025-compose-managed-runtime-stacks.md",
                "implemented_in_repo_version": "0.178.126",
                "implemented_in_platform_version": "0.178.78",
                "implemented_on": "2026-04-12",
            },
            {
                "adr": "0025",
                "title": "Gap Analysis Matrix",
                "status": "Proposed",
                "implementation_status": "Proposed",
                "filename": "0025-gap-analysis-matrix.md",
                "path": "docs/adr/0025-gap-analysis-matrix.md",
            },
            {
                "adr": "0025",
                "title": "Implementation Roadmap: Compose-Managed Runtime Stacks",
                "status": "Proposed",
                "implementation_status": "Proposed",
                "filename": "0025-implementation-roadmap.md",
                "path": "docs/adr/0025-implementation-roadmap.md",
            },
        ],
    }
    (shard_dir / "0000-0099.yaml").write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    monkeypatch.setattr(module, "ADR_DIR", adr_dir)
    monkeypatch.setattr(module, "INDEX_PATH", adr_dir / ".index.yaml")

    metadata = module.load_adr_index()

    adr = metadata["0025"]
    assert adr.title == "Compose-Managed Runtime Stacks"
    assert adr.filename == "0025-compose-managed-runtime-stacks.md"
    assert adr.status == "Accepted"
    assert adr.implementation_status == "Implemented"
    assert adr.implemented_in_repo_version == "0.178.126"
    assert adr.implemented_in_platform_version == "0.178.78"


def test_generate_report_distinguishes_decision_and_implementation_status() -> None:
    module = load_module("adr_implementation_scanner_status_report", "scripts/adr_implementation_scanner.py")
    metadata = module.ADRMetadata(
        adr_number="0374",
        title="Cross-Cutting Service Manifest",
        filename="0374-cross-cutting-service-manifest.md",
        path="docs/adr/0374-cross-cutting-service-manifest.md",
        status="Accepted",
        implementation_status="Implemented",
        implemented_in_repo_version="0.178.126",
        implemented_in_platform_version="0.178.126",
        implemented_on="2026-04-12",
    )
    markers = [
        module.ImplementationMarker(
            marker_type="live-apply-receipt",
            adr_number="0374",
            location="receipts/live-applies/2026-04-12-adr-0374-cross-cutting-service-manifest-live-apply.json",
            evidence="Committed live-apply evidence references the ADR",
            confidence=1.0,
        )
    ]

    report = module.generate_report(metadata, markers)
    markdown = module.generate_markdown_report(report)

    assert report.inferred_implementation_status == "Likely Implemented"
    assert report.status_match is True
    assert "Canonical Decision Status: Accepted" in report.summary
    assert "Canonical Implementation Status: Implemented" in report.summary
    assert "Inferred Implementation Status: Likely Implemented" in report.summary
    assert "| Canonical Decision Status | Accepted |" in markdown
    assert "| Canonical Implementation Status | Implemented |" in markdown
    assert "| Inferred Implementation Status | Likely Implemented |" in markdown
