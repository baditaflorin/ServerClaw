"""Unit tests for scripts/generate_traceability.py — ADR 0447 item 19.

Exercises the join logic against synthetic fixture trees so the live
workstream registry doesn't couple test outcomes to whatever happens to
be in flight on the day the tests run.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "generate_traceability.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("generate_traceability", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["generate_traceability"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gt():
    return _load_module()


# ---------------------------------------------------------------------------
# _normalise_adr_ref
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("0445", "0445"),
        (445, "0445"),
        ("445", "0445"),
        ("adr-0445-phase1-multi-deployment-hardening", "0445"),
        ("adr-0438-generic-by-construction", "0438"),
        ("ADR-0042-x", "0042"),
        ("not-a-ref", None),
        ("", None),
        (None, None),
    ],
)
def test_normalise_adr_ref(gt, raw, expected):
    assert gt._normalise_adr_ref(raw) == expected


# ---------------------------------------------------------------------------
# load_adr_index
# ---------------------------------------------------------------------------


def test_load_adr_index_zero_pads_keys(gt, tmp_path):
    path = tmp_path / "index.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "adrs": [
                    {"adr": 445, "title": "Phase 1"},
                    {"adr": "0042", "title": "Old"},
                ]
            }
        )
    )
    idx = gt.load_adr_index(path)
    assert set(idx) == {"0445", "0042"}
    assert idx["0445"]["title"] == "Phase 1"


def test_load_adr_index_first_wins_on_collision(gt, tmp_path):
    """Two ADR entries sharing a number is a real-world case (the
    0444 collision we hit during ws-0445). The loader picks the first
    deterministically rather than crashing."""
    path = tmp_path / "index.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "adrs": [
                    {"adr": "0444", "title": "first"},
                    {"adr": "0444", "title": "second"},
                ]
            }
        )
    )
    idx = gt.load_adr_index(path)
    assert idx["0444"]["title"] == "first"


def test_load_adr_index_missing_file_raises(gt, tmp_path):
    with pytest.raises(FileNotFoundError):
        gt.load_adr_index(tmp_path / "nope.yaml")


# ---------------------------------------------------------------------------
# load_workstreams
# ---------------------------------------------------------------------------


def test_load_workstreams_skips_underscore_and_dotfiles(gt, tmp_path):
    d = tmp_path / "active"
    d.mkdir()
    (d / "ws-0001-real.yaml").write_text(yaml.safe_dump({"id": "ws-0001-real"}))
    (d / "_README.yaml").write_text(yaml.safe_dump({"id": "should_skip"}))
    (d / ".hidden.yaml").write_text(yaml.safe_dump({"id": "should_skip"}))
    out = gt.load_workstreams(d, repo_root=tmp_path)
    ids = [ws.get("id") for ws in out]
    assert ids == ["ws-0001-real"]


def test_load_workstreams_handles_missing_directory(gt, tmp_path):
    assert gt.load_workstreams(tmp_path / "no-such-dir") == []


def test_load_workstreams_attaches_source_path(gt, tmp_path):
    """Each loaded workstream carries `__source_path` so build_traceability
    can fall back to it when `id:` is missing."""
    d = tmp_path / "active"
    d.mkdir()
    p = d / "ws-x.yaml"
    p.write_text(yaml.safe_dump({}))  # missing id
    out = gt.load_workstreams(d, repo_root=tmp_path)
    assert out[0]["__source_path"] == "active/ws-x.yaml"


# ---------------------------------------------------------------------------
# build_traceability
# ---------------------------------------------------------------------------


def test_build_traceability_resolves_primary_adr(gt, tmp_path):
    workstreams = [
        {
            "id": "ws-0445-phase1",
            "title": "Phase 1",
            "status": "in_progress",
            "ready_to_merge": True,
            "adr": "0445",
            "shared_surfaces": [],
        }
    ]
    adr_index = {
        "0445": {
            "title": "Phase 1 Multi-Deployment Hardening",
            "implementation_status": "Proposed",
            "currently_describes": "goal_state",
            "concern": "multi-deployment-safety",
            "path": "docs/adr/0445-phase1.md",
        }
    }
    traces = gt.build_traceability(workstreams, adr_index, tmp_path)
    assert len(traces) == 1
    t = traces[0]
    assert t.workstream_id == "ws-0445-phase1"
    assert t.primary_adr == "0445"
    assert t.adr_resolved["title"] == "Phase 1 Multi-Deployment Hardening"
    assert t.dangling_dependencies == []


def test_build_traceability_flags_dangling_dependencies(gt, tmp_path):
    workstreams = [
        {
            "id": "ws-x",
            "adr": "0445",
            "depends_on": ["adr-0445-phase1", "adr-9999-not-real"],
        }
    ]
    adr_index = {"0445": {"title": "real"}}
    traces = gt.build_traceability(workstreams, adr_index, tmp_path)
    t = traces[0]
    assert t.dangling_dependencies == ["adr-9999-not-real"]


def test_build_traceability_flags_missing_surfaces(gt, tmp_path):
    """A `shared_surfaces` path that doesn't exist on disk is dangling.
    Glob entries (`**`, `*`) are skipped — they're contracts, not exact
    paths."""
    (tmp_path / "real.yml").write_text("x")
    workstreams = [
        {
            "id": "ws-x",
            "adr": "0001",
            "shared_surfaces": [
                "real.yml",  # exists
                "missing.yml",  # missing
                "roles/**/defaults/main.yml",  # glob — skipped
            ],
        }
    ]
    traces = gt.build_traceability(workstreams, {"0001": {}}, tmp_path)
    t = traces[0]
    assert t.surfaces_total == 2  # glob excluded
    assert t.surfaces_present == 1
    assert t.dangling_surfaces == ["missing.yml"]


@pytest.mark.parametrize(
    "value,expected",
    [
        # Real paths — never prose
        ("inventory/hosts.yml", False),
        ("scripts/check_receipt_freshness.py", False),
        ("Makefile", False),  # bare-name file with no whitespace
        ("VERSION", False),
        # Prose / conceptual surfaces
        ("workflow events", True),
        ("alert events", True),
        ("Loki mutation-audit label", True),
        ("fork bootstrap entry point", True),
        # Edge cases
        ("", True),  # empty string — treat as prose
        ("   ", True),  # whitespace only
    ],
)
def test_looks_like_prose_heuristic(gt, value, expected):
    """The heuristic must distinguish real paths (file/dir refs) from
    prose surface descriptions. The current rule: contains whitespace
    AND has no `/` separator. This keeps `Makefile` eligible (a real
    bare-name file) while skipping `workflow events`."""
    assert gt._looks_like_prose(value) is expected


def test_build_traceability_skips_prose_surfaces(gt, tmp_path):
    """Prose entries in shared_surfaces (e.g. "workflow events") are
    not paths the validator can stat. They must be skipped, not
    flagged as dangling — that was a false-positive class on the live
    workstream registry (10 workstreams hit by it before this filter)."""
    (tmp_path / "real.yml").write_text("x")
    workstreams = [
        {
            "id": "ws-x",
            "adr": "0001",
            "shared_surfaces": [
                "real.yml",  # path → stat'd, exists
                "workflow events",  # prose → skipped
                "Loki mutation-audit label",  # prose → skipped
                "missing.yml",  # path → stat'd, missing
            ],
        }
    ]
    traces = gt.build_traceability(workstreams, {"0001": {}}, tmp_path)
    t = traces[0]
    assert t.surfaces_total == 2  # prose excluded
    assert t.dangling_surfaces == ["missing.yml"]


def test_build_traceability_handles_missing_id_via_source_path(gt, tmp_path):
    workstreams = [{"__source_path": "workstreams/active/ws-no-id.yaml"}]
    traces = gt.build_traceability(workstreams, {}, tmp_path)
    assert traces[0].workstream_id == "workstreams/active/ws-no-id.yaml"


# ---------------------------------------------------------------------------
# render_yaml — output shape
# ---------------------------------------------------------------------------


def test_render_yaml_summary_counts(gt, tmp_path):
    traces = gt.build_traceability(
        [
            {"id": "ws-1", "adr": "0001", "ready_to_merge": True, "shared_surfaces": []},
            {
                "id": "ws-2",
                "adr": "9999",  # dangling
                "ready_to_merge": False,
                "shared_surfaces": [],
            },
        ],
        {"0001": {"title": "Real"}},
        tmp_path,
    )
    rendered = gt.render_yaml(traces)
    # The generator prepends `# GENERATED — ...` comment lines, which YAML
    # tolerates as long as they precede the document content.
    parsed = yaml.safe_load(rendered)
    assert parsed["summary"]["total_workstreams"] == 2
    assert parsed["summary"]["with_resolved_adr"] == 1
    assert parsed["summary"]["ready_to_merge"] == 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_no_args_returns_two(gt, capsys):
    rc = gt.main([])
    assert rc == 2


def test_cli_validate_passes_on_clean_inputs(gt, tmp_path, monkeypatch):
    # Build a minimal repo skeleton.
    (tmp_path / "docs" / "adr").mkdir(parents=True)
    (tmp_path / "workstreams" / "active").mkdir(parents=True)
    (tmp_path / "build").mkdir()
    (tmp_path / "docs" / "adr" / ".index.yaml").write_text(yaml.safe_dump({"adrs": [{"adr": "0001", "title": "x"}]}))
    (tmp_path / "workstreams" / "active" / "ws-x.yaml").write_text(
        yaml.safe_dump({"id": "ws-x", "adr": "0001", "shared_surfaces": []})
    )
    rc = gt.main(["--validate", "--root", str(tmp_path)])
    assert rc == 0


def test_cli_validate_fails_on_dangling_ref(gt, tmp_path):
    (tmp_path / "docs" / "adr").mkdir(parents=True)
    (tmp_path / "workstreams" / "active").mkdir(parents=True)
    (tmp_path / "docs" / "adr" / ".index.yaml").write_text(yaml.safe_dump({"adrs": []}))
    (tmp_path / "workstreams" / "active" / "ws-x.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "ws-x",
                "adr": "0001",  # not in (empty) index
                "depends_on": ["adr-0001-x"],
                "shared_surfaces": [],
            }
        )
    )
    rc = gt.main(["--validate", "--root", str(tmp_path)])
    assert rc == 1


def test_cli_check_detects_drift(gt, tmp_path):
    (tmp_path / "docs" / "adr").mkdir(parents=True)
    (tmp_path / "workstreams" / "active").mkdir(parents=True)
    (tmp_path / "build").mkdir()
    (tmp_path / "docs" / "adr" / ".index.yaml").write_text(yaml.safe_dump({"adrs": [{"adr": "0001"}]}))
    (tmp_path / "workstreams" / "active" / "ws-x.yaml").write_text(
        yaml.safe_dump({"id": "ws-x", "adr": "0001", "shared_surfaces": []})
    )
    (tmp_path / "build" / "traceability.yaml").write_text("# stale content\n")
    rc = gt.main(["--check", "--root", str(tmp_path)])
    assert rc == 1


def test_cli_write_creates_artifact(gt, tmp_path):
    (tmp_path / "docs" / "adr").mkdir(parents=True)
    (tmp_path / "workstreams" / "active").mkdir(parents=True)
    (tmp_path / "docs" / "adr" / ".index.yaml").write_text(yaml.safe_dump({"adrs": [{"adr": "0001", "title": "x"}]}))
    (tmp_path / "workstreams" / "active" / "ws-x.yaml").write_text(
        yaml.safe_dump({"id": "ws-x", "adr": "0001", "shared_surfaces": []})
    )
    rc = gt.main(["--write", "--root", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "build" / "traceability.yaml").is_file()
    parsed = yaml.safe_load((tmp_path / "build" / "traceability.yaml").read_text())
    assert parsed["summary"]["total_workstreams"] == 1
