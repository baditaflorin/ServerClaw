from pathlib import Path

from platform_context_corpus import build_chunks, build_manifest


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_build_chunks_prefers_markdown_sections(tmp_path: Path) -> None:
    write(
        tmp_path / "docs" / "adr" / "0070-example.md",
        "# ADR 0070\n\nIntro\n\n## Decision\nUse step-ca for SSH certificates.\n\n## Notes\nMore detail.\n",
    )
    write(tmp_path / "docs" / "runbooks" / "example.md", "# Runbook\n\n## Verify\nCheck the service.\n")
    write(tmp_path / "receipts" / "live-applies" / "receipt.json", '{"receipt_id":"r1"}')
    write(tmp_path / "config" / "command-catalog.json", '{"commands":{}}')
    write(tmp_path / "config" / "workflow-catalog.json", '{"workflows":{}}')
    write(tmp_path / "config" / "agent-tool-registry.json", '{"tools":[]}')
    write(tmp_path / "versions" / "stack.yaml", "repo_version: 1.0.0\n")
    write(tmp_path / "VERSION", "1.0.0\n")
    write(tmp_path / "changelog.md", "# Changelog\n")

    chunks = build_chunks(tmp_path)
    decision_chunks = [chunk for chunk in chunks if chunk["section_heading"] == "Decision"]
    assert decision_chunks
    assert decision_chunks[0]["adr_number"] == "0070"

    manifest = build_manifest(tmp_path)
    assert manifest["source_count"] >= 6
    assert manifest["chunk_count"] == len(chunks)
