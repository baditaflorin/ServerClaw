"""Unit tests for scripts/generate_validator_catalogue.py — ADR 0449 phase 4.2.

Builds synthetic scripts/ trees under tmp_path and confirms the
extraction + cross-reference logic. Live repo behaviour is exercised
once via a smoke test that the generator runs cleanly end-to-end.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from textwrap import dedent

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "generate_validator_catalogue.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("generate_validator_catalogue", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["generate_validator_catalogue"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gvc():
    return _load_module()


# ---------------------------------------------------------------------------
# discover_validators
# ---------------------------------------------------------------------------


def test_discover_validators_picks_up_validate_and_check(gvc, tmp_path):
    d = tmp_path / "scripts"
    d.mkdir()
    (d / "validate_x.py").write_text("'''docstring'''\n")
    (d / "validate_y.sh").write_text("# header\n")
    (d / "check_z.py").write_text("'''docstring'''\n")
    (d / "other.py").write_text("'''not a validator'''\n")
    (d / "validate_repo.sh").write_text("# self — should be excluded")
    out = [p.name for p in gvc.discover_validators(d)]
    assert out == ["check_z.py", "validate_x.py", "validate_y.sh"]


def test_discover_validators_handles_missing_dir(gvc, tmp_path):
    assert gvc.discover_validators(tmp_path / "no-such-dir") == []


# ---------------------------------------------------------------------------
# extract_docstring
# ---------------------------------------------------------------------------


def test_extract_docstring_python(gvc, tmp_path):
    p = tmp_path / "v.py"
    p.write_text(
        dedent('''\
            """First line of purpose.

            Subsequent paragraph that should not appear in the catalogue
            row, only the first paragraph does.
            """
            x = 1
        ''')
    )
    doc = gvc.extract_docstring(p)
    assert doc.startswith("First line of purpose.")


def test_extract_docstring_python_no_docstring(gvc, tmp_path):
    p = tmp_path / "v.py"
    p.write_text("x = 1\n")
    assert gvc.extract_docstring(p) == ""


def test_extract_docstring_python_syntax_error_returns_empty(gvc, tmp_path):
    p = tmp_path / "v.py"
    p.write_text("def broken(\n")  # syntax error
    assert gvc.extract_docstring(p) == ""


def test_extract_docstring_shell(gvc, tmp_path):
    p = tmp_path / "v.sh"
    p.write_text(
        dedent("""\
            #!/usr/bin/env bash
            # Validates the X subsystem against the Y schema.
            # Multiline header.

            set -e
            echo "code"
        """)
    )
    doc = gvc.extract_docstring(p)
    assert "Validates the X" in doc
    assert "echo" not in doc


# ---------------------------------------------------------------------------
# first_paragraph
# ---------------------------------------------------------------------------


def test_first_paragraph_collapses_newlines(gvc):
    para = gvc.first_paragraph("Line one\nstill line one.\n\nSecond paragraph.\n")
    assert para == "Line one still line one."


def test_first_paragraph_handles_empty(gvc):
    assert gvc.first_paragraph("") == ""


def test_first_paragraph_caps_length(gvc):
    long = "x" * 500
    para = gvc.first_paragraph(long)
    assert para.endswith("...")
    assert len(para) <= 240


# ---------------------------------------------------------------------------
# extract_related_adrs
# ---------------------------------------------------------------------------


def test_extract_related_adrs_zero_pads_and_dedupes(gvc):
    text = "Implements ADR 443 and ADR 0445. ADR 443 (again)."
    assert gvc.extract_related_adrs(text) == ["0443", "0445"]


def test_extract_related_adrs_no_match_returns_empty(gvc):
    assert gvc.extract_related_adrs("no references here") == []


# ---------------------------------------------------------------------------
# gate_invocation_set
# ---------------------------------------------------------------------------


def test_gate_invocation_set_picks_up_function_defs_and_calls(gvc):
    sh = dedent("""\
        validate_yaml() {
          echo "yaml"
        }

        validate_no_hardcoded_topology() {
          run scripts/validate_no_hardcoded_topology.py
        }

        case "$mode" in
          all)
            validate_yaml
            validate_no_hardcoded_topology
          ;;
        esac
    """)
    out = gvc.gate_invocation_set(sh)
    # function names + the script reference
    assert "validate_yaml" in out
    assert "validate_no_hardcoded_topology" in out


def test_stem_keys_returns_filename_and_bare_stem(gvc):
    assert gvc.stem_keys("validate_yaml.py") == {"validate_yaml.py", "validate_yaml"}
    assert gvc.stem_keys("check_z.sh") == {"check_z.sh", "check_z"}


# ---------------------------------------------------------------------------
# build_entries — end-to-end on a synthetic tree
# ---------------------------------------------------------------------------


def test_build_entries_marks_membership(gvc, tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "validate_alpha.py").write_text('"""Alpha validator. Implements ADR 0001."""\n')
    (scripts / "validate_beta.py").write_text('"""Beta validator. Implements ADR 0002."""\n')
    sh_path = scripts / "validate_repo.sh"
    sh_path.write_text(
        dedent("""\
            validate_alpha() {
              scripts/validate_alpha.py
            }
            case "$mode" in
              all) validate_alpha ;;
            esac
        """)
    )
    hook_path = tmp_path / ".githooks" / "pre-push"
    hook_path.parent.mkdir()
    hook_path.write_text(
        dedent("""\
        #!/usr/bin/env bash
        scripts/validate_alpha.py
    """)
    )

    entries = gvc.build_entries(
        scripts_dir=scripts,
        validate_repo_sh=sh_path,
        pre_push_hook=hook_path,
    )
    by_name = {e.name: e for e in entries}
    assert by_name["validate_alpha.py"].runs_in_validate_repo_sh is True
    assert by_name["validate_alpha.py"].runs_in_pre_push_hook is True
    assert by_name["validate_alpha.py"].related_adrs == ["0001"]
    assert by_name["validate_beta.py"].runs_in_validate_repo_sh is False
    assert by_name["validate_beta.py"].runs_in_pre_push_hook is False
    assert by_name["validate_beta.py"].related_adrs == ["0002"]


def test_build_entries_handles_no_docstring(gvc, tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "validate_x.py").write_text("x = 1\n")
    entries = gvc.build_entries(
        scripts_dir=scripts,
        validate_repo_sh=tmp_path / "absent.sh",
        pre_push_hook=tmp_path / "absent",
    )
    assert entries[0].purpose == "(no docstring)"
    assert entries[0].related_adrs == []


# ---------------------------------------------------------------------------
# render_yaml + CLI
# ---------------------------------------------------------------------------


def test_render_yaml_summary_counts(gvc):
    Entry = gvc.ValidatorEntry
    entries = [
        Entry("a.py", "Alpha", ["0001"], True, True, "scripts/a.py"),
        Entry("b.py", "Beta", [], False, False, "scripts/b.py"),
        Entry("c.py", "(no docstring)", [], True, False, "scripts/c.py"),
    ]
    rendered = gvc.render_yaml(entries)
    parsed = yaml.safe_load(rendered)
    assert parsed["summary"]["total"] == 3
    assert parsed["summary"]["in_validate_repo_sh"] == 2
    assert parsed["summary"]["in_pre_push_hook"] == 1
    assert parsed["summary"]["without_docstring"] == 1
    assert parsed["summary"]["without_related_adr"] == 2


def test_cli_no_args_returns_two(gvc, capsys):
    rc = gvc.main([])
    assert rc == 2


def test_cli_write_creates_artifact(gvc, tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "validate_x.py").write_text('"""X validator."""\n')
    (tmp_path / "build").mkdir()
    rc = gvc.main(["--write", "--root", str(tmp_path)])
    assert rc == 0
    out = tmp_path / "build" / "validator-catalogue.yaml"
    assert out.is_file()
    parsed = yaml.safe_load(out.read_text())
    assert parsed["summary"]["total"] == 1


def test_cli_check_detects_drift(gvc, tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "validate_x.py").write_text('"""X validator."""\n')
    out = tmp_path / "build" / "validator-catalogue.yaml"
    out.parent.mkdir()
    out.write_text("# stale content\n")
    rc = gvc.main(["--check", "--root", str(tmp_path)])
    assert rc == 1


# ---------------------------------------------------------------------------
# Live repo smoke
# ---------------------------------------------------------------------------


def test_live_repo_generates_at_least_25_validators(gvc):
    """The validator catalogue should pick up at least 25 validators
    against the live repo (gate evidence). Catches accidental
    regressions to the discovery logic — fewer than 25 would be a
    drop from the 25+ already wired into validate_repo.sh today.
    """
    entries = gvc.build_entries()
    assert len(entries) >= 25, (
        f"only {len(entries)} validators discovered; expected >=25. "
        f"Either the discovery logic broke or the catalogue is right "
        f"and the platform lost coverage — investigate before merging."
    )
