from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_configure_edge_publication_builds_shared_static_artifacts_first() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    assert "configure-edge-publication:\n\t$(MAKE) preflight WORKFLOW=configure-edge-publication\n\t$(MAKE) generate-changelog-portal docs\n" in makefile
