from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_docs_href_for_source_path_maps_to_published_portal_routes() -> None:
    module = load_module(
        REPO_ROOT / "config" / "windmill" / "scripts" / "command-palette-search.py",
        "command_palette_search",
    )

    assert module.docs_href_for_source_path("docs/runbooks/operator-onboarding.md") == (
        "https://docs.example.com/runbooks/operator-onboarding/"
    )
    assert module.docs_href_for_source_path(
        "docs/adr/0311-global-command-palette-and-universal-open-dialog-via-cmdk.md"
    ) == (
        "https://docs.example.com/architecture/decisions/0311-global-command-palette-and-universal-open-dialog-via-cmdk/"
    )


def test_main_queries_runbooks_and_adrs_from_search_fabric(tmp_path: Path) -> None:
    module = load_module(
        REPO_ROOT / "config" / "windmill" / "scripts" / "command-palette-search.py",
        "command_palette_search",
    )

    (tmp_path / "docs" / "runbooks").mkdir(parents=True)
    (tmp_path / "docs" / "adr").mkdir(parents=True)
    shutil.copytree(REPO_ROOT / "scripts" / "search_fabric", tmp_path / "scripts" / "search_fabric")
    (tmp_path / "config").mkdir(parents=True)
    shutil.copy2(REPO_ROOT / "config" / "search-synonyms.yaml", tmp_path / "config" / "search-synonyms.yaml")
    (tmp_path / "docs" / "runbooks" / "operator-onboarding.md").write_text(
        "# Operator Onboarding\n\nTOTP enrollment and Keycloak access start here.\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "adr" / "0311-global-command-palette.md").write_text(
        "# ADR 0311: Global Command Palette\n\nUniversal open dialog for docs search.\n",
        encoding="utf-8",
    )

    payload = module.main(query="totp", repo_path=str(tmp_path), limit=6)

    assert payload["status"] == "ok"
    assert payload["count"] >= 1
    first = payload["results"][0]
    assert first["kind"] in {"runbook", "adr"}
    assert first["lane"] in {"learn", "recover"}
    assert first["href"].startswith("https://docs.example.com/")
