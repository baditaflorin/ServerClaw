"""Behaviour tests for the Scanopy Docker bridge subnet tagging job.

The job must only ever add the docker-bridge tag to DockerBridge subnets: it must not touch other subnet types, remove
tags, or run away when something is wrong. A fake in-memory Scanopy replaces the HTTP layer; nothing here touches a
network or a real host.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    REPO_ROOT
    / "collections/ansible_collections/lv3/platform/roles/monitoring_vm/files/scanopy-retag/scanopy_retag.py"
)
TAG_ID = "tag-docker-bridge"


@pytest.fixture()
def retag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    spec = importlib.util.spec_from_file_location("scanopy_retag_under_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    key_file = tmp_path / "api-key"
    key_file.write_text("test-key\n")
    monkeypatch.setitem(module.CONF, "key_file", str(key_file))
    monkeypatch.setitem(module.CONF, "textfile", str(tmp_path / "scanopy_retag.prom"))
    return module


class FakeScanopy:
    """Just enough of the Scanopy API for the job: tags list, subnets list, bulk tag assignment."""

    def __init__(self, subnets: list[dict], tags: list[dict] | None = None) -> None:
        self.subnets = subnets
        self.tags = [{"id": TAG_ID, "name": "docker-bridge"}] if tags is None else tags
        self.writes: list[dict] = []

    def __call__(self, key: str, method: str, path: str, body: dict | None = None) -> dict:
        assert key == "test-key"
        if method == "GET" and path.startswith("/api/v1/tags"):
            return {"success": True, "data": self.tags, "meta": {}}
        if method == "GET" and path.startswith("/api/v1/subnets"):
            return {"success": True, "data": self.subnets, "meta": {}}
        if method == "POST" and path == "/api/v1/tags/assign/bulk-add":
            assert body is not None
            self.writes.append(body)
            for subnet in self.subnets:
                if subnet["id"] in body["entity_ids"]:
                    subnet["tags"] = [*subnet["tags"], body["tag_id"]]
            return {"success": True, "data": None}
        raise AssertionError(f"unexpected call {method} {path}")


def subnet(sid: str, kind: str = "DockerBridge", tags: list[str] | None = None) -> dict:
    return {"id": sid, "cidr": "172.20.0.0/24", "name": sid, "subnet_type": kind, "tags": tags or []}


def run(retag: ModuleType, fake: FakeScanopy, monkeypatch: pytest.MonkeyPatch, *argv: str) -> int:
    monkeypatch.setattr(retag, "call", fake)
    monkeypatch.setattr(sys, "argv", ["scanopy_retag.py", *argv])
    with pytest.raises(SystemExit) as exit_info:
        retag.main()
    return int(exit_info.value.code)


def metrics(retag: ModuleType) -> dict[str, float]:
    text = Path(retag.CONF["textfile"]).read_text()
    return {line.split()[0]: float(line.split()[1]) for line in text.splitlines() if line and not line.startswith("#")}


def test_only_untagged_docker_bridge_subnets_are_tagged(retag, monkeypatch) -> None:
    fake = FakeScanopy(
        [
            subnet("new-1"),
            subnet("done", tags=[TAG_ID]),
            subnet("lan", kind="Lan"),
            subnet("unknown", kind="Unknown"),
            subnet("new-2", tags=["some-other-tag"]),
        ]
    )

    assert run(retag, fake, monkeypatch) == 0

    assert fake.writes == [{"entity_type": "Subnet", "entity_ids": ["new-1", "new-2"], "tag_id": TAG_ID}]
    by_id = {s["id"]: s for s in fake.subnets}
    assert by_id["new-2"]["tags"] == ["some-other-tag", TAG_ID]  # existing tags are kept, never replaced
    assert by_id["lan"]["tags"] == [] and by_id["unknown"]["tags"] == []
    assert metrics(retag)["scanopy_retag_tagged_this_run"] == 2
    assert metrics(retag)["scanopy_retag_docker_bridge_subnets"] == 3  # new-1, done, new-2


def test_a_second_run_with_nothing_to_do_writes_nothing(retag, monkeypatch) -> None:
    fake = FakeScanopy([subnet("a", tags=[TAG_ID]), subnet("b", tags=[TAG_ID])])

    assert run(retag, fake, monkeypatch) == 0

    assert fake.writes == []
    assert metrics(retag)["scanopy_retag_untagged_found"] == 0
    assert metrics(retag)["scanopy_retag_last_attempt_success"] == 1


def test_assignments_are_sent_in_batches_of_one_hundred(retag, monkeypatch) -> None:
    fake = FakeScanopy([subnet(f"n{i}") for i in range(250)])

    assert run(retag, fake, monkeypatch) == 0

    assert [len(write["entity_ids"]) for write in fake.writes] == [100, 100, 50]
    assert all(TAG_ID in s["tags"] for s in fake.subnets)


def test_dry_run_reports_but_neither_writes_nor_publishes_metrics(retag, monkeypatch) -> None:
    fake = FakeScanopy([subnet("new-1")])

    assert run(retag, fake, monkeypatch, "--dry-run") == 0

    assert fake.writes == [] and fake.subnets[0]["tags"] == []
    assert not Path(retag.CONF["textfile"]).exists()


def test_runaway_guard_refuses_to_tag_more_than_the_limit(retag, monkeypatch) -> None:
    monkeypatch.setitem(retag.CONF, "max_per_run", 5)
    fake = FakeScanopy([subnet(f"n{i}") for i in range(6)])

    assert run(retag, fake, monkeypatch) == 1

    assert fake.writes == []
    assert metrics(retag)["scanopy_retag_last_attempt_success"] == 0
    assert "scanopy_retag_last_success_timestamp_seconds" not in metrics(retag)


@pytest.mark.parametrize("tags", [[], [{"id": "a", "name": "docker-bridge"}, {"id": "b", "name": "docker-bridge"}]])
def test_a_missing_or_ambiguous_tag_fails_instead_of_creating_one(retag, monkeypatch, tags) -> None:
    fake = FakeScanopy([subnet("new-1")], tags=tags)

    assert run(retag, fake, monkeypatch) == 1

    assert fake.writes == []
    assert metrics(retag)["scanopy_retag_last_attempt_success"] == 0


def test_a_missing_or_empty_key_file_fails_without_calling_scanopy(retag, monkeypatch, tmp_path) -> None:
    fake = FakeScanopy([subnet("new-1")])
    empty = tmp_path / "empty-key"
    empty.write_text("\n")

    for key_file in (tmp_path / "does-not-exist", empty):
        monkeypatch.setitem(retag.CONF, "key_file", str(key_file))
        assert run(retag, fake, monkeypatch) == 1

    assert fake.writes == []
    assert metrics(retag)["scanopy_retag_last_attempt_success"] == 0


def test_the_job_has_no_remove_or_delete_calls() -> None:
    source = MODULE_PATH.read_text()

    assert "bulk-remove" not in source and "bulk-delete" not in source
    assert '"DELETE"' not in source and '"PUT"' not in source
