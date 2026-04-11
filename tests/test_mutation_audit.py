from __future__ import annotations

import io
import sys
import types
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

import mutation_audit  # noqa: E402


def test_publish_ntfy_failure_best_effort_builds_governed_command(monkeypatch, tmp_path: Path) -> None:
    publish_script = tmp_path / "ntfy_publish.py"
    publish_script.write_text("print('ok')\n", encoding="utf-8")
    registry_path = tmp_path / "topics.yaml"
    registry_path.write_text("schema_version: '1.0.0'\n", encoding="utf-8")
    dedupe_state_path = tmp_path / "dedupe.json"
    calls: dict[str, object] = {}

    def fake_run(command: list[str], *, text: bool, capture_output: bool, check: bool) -> types.SimpleNamespace:
        calls["command"] = command
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(mutation_audit.subprocess, "run", fake_run)

    event = mutation_audit.build_event(
        actor_class="automation",
        actor_id="ansible-playbook",
        surface="ansible",
        action="render.ntfy_config",
        target="docker-runtime",
        outcome="failure",
        correlation_id="ansible:test-correlation",
        evidence_ref="receipts/live-applies/evidence/test.txt",
    )

    assert (
        mutation_audit.publish_ntfy_failure_best_effort(
            event,
            context="unit test",
            publish_script=publish_script,
            registry_path=registry_path,
            dedupe_state_path=dedupe_state_path,
        )
        is True
    )

    command = calls["command"]
    assert isinstance(command, list)
    assert command[0] == sys.executable
    assert "--publisher" in command
    assert command[command.index("--publisher") + 1] == "ansible"
    assert "--topic" in command
    assert command[command.index("--topic") + 1] == "platform-ansible-critical"
    assert "--sequence-id" in command
    assert command[command.index("--sequence-id") + 1] == "ansible:ansible:test-correlation:failure"
    assert "--dedupe-state-file" in command
    assert command[command.index("--dedupe-state-file") + 1] == str(dedupe_state_path)


def test_publish_ntfy_failure_best_effort_skips_non_failure_events(tmp_path: Path) -> None:
    publish_script = tmp_path / "ntfy_publish.py"
    publish_script.write_text("print('ok')\n", encoding="utf-8")
    registry_path = tmp_path / "topics.yaml"
    registry_path.write_text("schema_version: '1.0.0'\n", encoding="utf-8")
    stderr = io.StringIO()

    event = mutation_audit.build_event(
        actor_class="automation",
        actor_id="ansible-playbook",
        surface="ansible",
        action="render.ntfy_config",
        target="docker-runtime",
        outcome="success",
        correlation_id="ansible:test-correlation",
        evidence_ref="",
    )

    assert (
        mutation_audit.publish_ntfy_failure_best_effort(
            event,
            context="unit test",
            stderr=stderr,
            publish_script=publish_script,
            registry_path=registry_path,
            dedupe_state_path=tmp_path / "dedupe.json",
        )
        is False
    )
    assert stderr.getvalue() == ""
