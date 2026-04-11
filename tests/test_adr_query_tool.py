from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path


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
) -> None:
    write(
        adr_dir / f"{number}-{slug}.md",
        f"""# ADR {number}: {title}

- Status: {status}
- Implementation Status: {implementation_status}
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Implemented On: N/A
- Date: 2026-04-01
- Tags: {tags}

## Decision

We will keep ADR discovery structured and queryable.
""",
    )


def build_generated_index(tmp_path: Path) -> None:
    discovery = load_module("adr_discovery_query_setup", "scripts/adr_discovery.py")
    adr_dir = tmp_path / "docs" / "adr"
    reservations_path = adr_dir / "index" / "reservations.yaml"

    write_adr(
        adr_dir, "0306", "checkov", "Checkov For IaC", implementation_status="Implemented", tags="security, validation"
    )
    write_adr(adr_dir, "0325", "faceted-adr-index", "Faceted ADR Index", tags="documentation, reservation, sharding")
    write(
        reservations_path,
        """schema_version: 1
reservations:
  - id: future-bundle
    start: "0326"
    end: "0328"
    reason: reserved docs bundle
    reserved_on: 2026-04-03
    status: active
""",
    )

    adrs = discovery.load_adrs(adr_dir, repo_root=tmp_path)
    ledger = discovery.load_reservation_ledger(reservations_path)
    documents = discovery.build_generated_index_documents(adrs, ledger, repo_root=tmp_path, adr_dir=adr_dir)
    discovery.write_generated_index_documents(documents, adr_dir=adr_dir)


def test_list_filters_by_concern_from_shards(tmp_path: Path, monkeypatch, capsys) -> None:
    build_generated_index(tmp_path)
    module = load_module("adr_query_tool_concern", "scripts/adr_query_tool.py")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "ADR_DIR", tmp_path / "docs" / "adr")
    monkeypatch.setattr(module, "INDEX_FILE", tmp_path / "docs" / "adr" / ".index.yaml")
    monkeypatch.setattr(module, "RESERVATIONS_FILE", tmp_path / "docs" / "adr" / "index" / "reservations.yaml")

    exit_code = module.command_list(module.build_parser().parse_args(["list", "--concern", "documentation"]))

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert [entry["adr"] for entry in payload] == ["0325"]


def test_allocate_skips_active_reservation_windows(tmp_path: Path, monkeypatch, capsys) -> None:
    build_generated_index(tmp_path)
    module = load_module("adr_query_tool_allocate", "scripts/adr_query_tool.py")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "ADR_DIR", tmp_path / "docs" / "adr")
    monkeypatch.setattr(module, "INDEX_FILE", tmp_path / "docs" / "adr" / ".index.yaml")
    monkeypatch.setattr(module, "RESERVATIONS_FILE", tmp_path / "docs" / "adr" / "index" / "reservations.yaml")

    exit_code = module.command_allocate(module.build_parser().parse_args(["allocate", "--window-size", "2"]))

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["start"] == "0329"
    assert payload["end"] == "0330"
