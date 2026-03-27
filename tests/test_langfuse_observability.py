from pathlib import Path

from platform.llm.observability import load_langfuse_config, trace_url


def test_load_langfuse_config_reads_local_files(tmp_path: Path) -> None:
    local_dir = tmp_path / ".local" / "langfuse"
    local_dir.mkdir(parents=True)
    (local_dir / "project-public-key.txt").write_text("pk-lf-test\n", encoding="utf-8")
    (local_dir / "project-secret-key.txt").write_text("sk-lf-test\n", encoding="utf-8")
    (local_dir / "project-id.txt").write_text("lv3-agent-observability\n", encoding="utf-8")

    config = load_langfuse_config(tmp_path)

    assert config.host == "https://langfuse.lv3.org"
    assert config.public_key == "pk-lf-test"
    assert config.secret_key == "sk-lf-test"
    assert config.project_id == "lv3-agent-observability"


def test_trace_url_uses_project_scoped_path() -> None:
    assert (
        trace_url("https://langfuse.lv3.org", "lv3-agent-observability", "trace-123")
        == "https://langfuse.lv3.org/project/lv3-agent-observability/traces/trace-123"
    )
