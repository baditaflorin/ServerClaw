from __future__ import annotations

from pathlib import Path

import generate_diagrams


def test_render_diagrams_matches_committed_outputs() -> None:
    rendered = generate_diagrams.render_diagrams()

    assert sorted(rendered) == [
        "agent-coordination-map.excalidraw",
        "network-topology.excalidraw",
        "service-dependency-graph.excalidraw",
        "trust-tier-model.excalidraw",
    ]
    for filename, content in rendered.items():
        path = generate_diagrams.OUTPUT_DIR / filename
        assert path.read_text(encoding="utf-8") == content


def test_stdout_mode_lists_filenames(capsys) -> None:
    exit_code = generate_diagrams.main(["--stdout"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "network-topology.excalidraw" in captured.out
    assert "agent-coordination-map.excalidraw" in captured.out


def test_outputs_match_detects_stale_directory(tmp_path: Path) -> None:
    output_dir = tmp_path / "diagrams"
    output_dir.mkdir()
    (output_dir / "network-topology.excalidraw").write_text("{}\n", encoding="utf-8")

    exit_code = generate_diagrams.main(["--check", "--output-dir", str(output_dir)])

    assert exit_code != 0
