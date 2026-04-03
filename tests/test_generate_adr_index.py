from __future__ import annotations

import datetime as dt
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


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_adr(
    adr_dir: Path,
    number: str,
    slug: str,
    title: str,
    *,
    status: str = "Accepted",
    implementation_status: str = "Not Implemented",
    tags: str = "documentation, discovery",
    implemented_in_repo_version: str = "N/A",
    implemented_in_platform_version: str = "N/A",
    implemented_on: str = "N/A",
    date: str = "2026-04-01",
    decision_sentence: str = "We will keep ADR discovery structured and queryable.",
) -> None:
    write(
        adr_dir / f"{number}-{slug}.md",
        f"""# ADR {number}: {title}

- Status: {status}
- Implementation Status: {implementation_status}
- Implemented In Repo Version: {implemented_in_repo_version}
- Implemented In Platform Version: {implemented_in_platform_version}
- Implemented On: {implemented_on}
- Date: {date}
- Tags: {tags}

## Decision

{decision_sentence}
""",
    )


def test_build_generated_index_documents_creates_compact_root_and_shards(tmp_path: Path) -> None:
    module = load_module("adr_discovery_root_compact", "scripts/adr_discovery.py")
    adr_dir = tmp_path / "docs" / "adr"
    reservations_path = adr_dir / "index" / "reservations.yaml"

    write_adr(adr_dir, "0001", "bootstrap", "Bootstrap Path", tags="bootstrap, automation")
    write_adr(
        adr_dir,
        "0306",
        "checkov",
        "Checkov For IaC",
        implementation_status="Implemented",
        implemented_in_repo_version="0.177.119",
        implemented_in_platform_version="0.130.75",
        implemented_on="2026-03-31",
        tags="ci, security, validation",
    )
    write_adr(
        adr_dir,
        "0325",
        "faceted-adr-index",
        "Faceted ADR Index",
        tags="documentation, indexing, reservation, sharding",
    )
    module.ensure_reservations_file(reservations_path)

    adrs = module.load_adrs(adr_dir, repo_root=tmp_path)
    ledger = module.load_reservation_ledger(reservations_path)
    documents = module.build_generated_index_documents(
        adrs,
        ledger,
        repo_root=tmp_path,
        adr_dir=adr_dir,
        generated_on=dt.date(2026, 4, 3),
    )

    root_payload = yaml.safe_load(documents[adr_dir / ".index.yaml"])
    assert "adr_index" not in root_payload
    assert root_payload["adr_number_range"] == {
        "first": "0001",
        "last": "0325",
        "next_available": "0326",
    }
    assert any(item["concern"] == "documentation" for item in root_payload["facets"]["by_concern"])
    assert any(item["label"] == "0300-0399" for item in root_payload["facets"]["by_range"])

    status_shard = yaml.safe_load(documents[adr_dir / "index" / "by-status" / "not-implemented.yaml"])
    assert [entry["adr"] for entry in status_shard["adrs"]] == ["0001", "0325"]

    range_shard = yaml.safe_load(documents[adr_dir / "index" / "by-range" / "0300-0399.yaml"])
    assert [entry["adr"] for entry in range_shard["adrs"]] == ["0306", "0325"]


def test_validate_reservation_ledger_rejects_conflicting_active_windows(tmp_path: Path) -> None:
    module = load_module("adr_discovery_reservation_validation", "scripts/adr_discovery.py")
    adr_dir = tmp_path / "docs" / "adr"
    reservations_path = adr_dir / "index" / "reservations.yaml"

    write_adr(adr_dir, "0325", "faceted-adr-index", "Faceted ADR Index")
    write(
        reservations_path,
        """schema_version: 1
reservations:
  - id: bundle-one
    start: "0325"
    end: "0327"
    reason: first reservation
    reserved_on: 2026-04-03
    status: active
  - id: bundle-two
    start: "0327"
    end: "0328"
    reason: overlapping reservation
    reserved_on: 2026-04-03
    status: active
""",
    )

    adrs = module.load_adrs(adr_dir, repo_root=tmp_path)
    ledger = module.load_reservation_ledger(reservations_path)
    issues = module.validate_reservation_ledger(ledger, adrs, today=dt.date(2026, 4, 3))

    assert any("overlaps committed ADR 0325" in issue for issue in issues)
    assert any("bundle-one" in issue and "bundle-two" in issue for issue in issues)


def test_check_generated_index_documents_detects_stale_shard(tmp_path: Path) -> None:
    module = load_module("adr_discovery_drift", "scripts/adr_discovery.py")
    adr_dir = tmp_path / "docs" / "adr"
    reservations_path = adr_dir / "index" / "reservations.yaml"

    write_adr(adr_dir, "0325", "faceted-adr-index", "Faceted ADR Index")
    module.ensure_reservations_file(reservations_path)

    adrs = module.load_adrs(adr_dir, repo_root=tmp_path)
    ledger = module.load_reservation_ledger(reservations_path)
    documents = module.build_generated_index_documents(
        adrs,
        ledger,
        repo_root=tmp_path,
        adr_dir=adr_dir,
        generated_on=dt.date(2026, 4, 3),
    )
    module.write_generated_index_documents(documents, adr_dir=adr_dir)

    stale_path = adr_dir / "index" / "by-range" / "0300-0399.yaml"
    stale_path.write_text("stale: true\n", encoding="utf-8")

    issues = module.check_generated_index_documents(documents, adr_dir=adr_dir)

    assert any("0300-0399.yaml" in issue for issue in issues)


def test_main_uses_utc_generated_date_for_written_index(monkeypatch) -> None:
    module = load_module("generate_adr_index_main_generated_date", "scripts/generate_adr_index.py")
    captured: dict[str, dt.date] = {}

    monkeypatch.setattr(module, "generated_date", lambda: dt.date(2026, 4, 3))
    monkeypatch.setattr(module, "ensure_reservations_file", lambda path: False)
    monkeypatch.setattr(module, "_load_inputs", lambda today: ([], object(), []))

    def fake_build_generated_index_documents(adrs, ledger, *, adr_dir, generated_on):
        captured["generated_on"] = generated_on
        return {module.INDEX_PATH: "schema_version: 2\n"}

    monkeypatch.setattr(module, "build_generated_index_documents", fake_build_generated_index_documents)
    monkeypatch.setattr(module, "write_generated_index_documents", lambda documents, adr_dir: None)

    assert module.main(["--write"]) == 0
    assert captured["generated_on"] == dt.date(2026, 4, 3)
