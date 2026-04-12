from __future__ import annotations

from pathlib import Path

from scripts import materialize_shared_edge_portals as portals


def test_materialize_removes_empty_target_before_generation(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    target = repo_root / "build" / "ops-portal"
    target.mkdir(parents=True)

    commands: list[str] = []

    def fake_run(command: str) -> None:
        commands.append(command)
        target.mkdir(parents=True)
        (target / "index.html").write_text("ok\n", encoding="utf-8")

    monkeypatch.setattr(portals, "REPO_ROOT", repo_root)
    monkeypatch.setattr(portals, "PORTAL_GENERATORS", {"ops-portal": "make generate-ops-portal"})
    monkeypatch.setattr(portals, "shared_repo_root", lambda _repo_root: repo_root)
    monkeypatch.setattr(portals, "_run", fake_run)

    portals.materialize()

    assert commands == ["make generate-ops-portal"]
    assert (target / "index.html").read_text(encoding="utf-8") == "ok\n"
