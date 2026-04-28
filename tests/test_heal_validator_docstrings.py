"""Unit tests for scripts/heal_validator_docstrings.py — ADR 0451 phase 6.3.

The synthesiser is a pure function over filenames; the inserter is
file-IO. Tests cover both, plus the catalogue-loading code path that
discovers which validators need backfilling.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "heal_validator_docstrings.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("heal_validator_docstrings", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["heal_validator_docstrings"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def hvd():
    return _load_module()


# ---------------------------------------------------------------------------
# synthesise_title
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("validate_dns_declarations.py", "Validate DNS declarations."),
        ("validate_tls_certs.py", "Validate TLS certs."),
        ("validate_sso_clients.py", "Validate SSO clients."),
        ("validate_nats_topics.py", "Validate NATS topics."),
        ("check_role_argument_specs.sh", "Check role argument specs."),
        ("check_hardcoded_timeouts.py", "Check hardcoded timeouts."),
        ("validate_dependency_direction.py", "Validate dependency direction."),
        # Acronym at end of name
        ("validate_repository_data_models.py", "Validate repository data models."),
        # Single-word case
        ("validate_yaml.py", "Validate YAML."),
        ("validate_json.py", "Validate JSON."),
    ],
)
def test_synthesise_title(hvd, filename, expected):
    assert hvd.synthesise_title(filename) == expected


def test_synthesise_title_handles_unknown_prefix(hvd):
    """A file that doesn't start with validate_/check_ falls back to
    "Run <stem>." rather than crashing."""
    assert hvd.synthesise_title("foo_bar.py") == "Run foo bar."


# ---------------------------------------------------------------------------
# already_has_docstring
# ---------------------------------------------------------------------------


def test_already_has_docstring_python_with_docstring(hvd, tmp_path):
    p = tmp_path / "validate_x.py"
    p.write_text('"""Existing docstring."""\nx = 1\n')
    assert hvd.already_has_docstring(p) is True


def test_already_has_docstring_python_without_docstring(hvd, tmp_path):
    p = tmp_path / "validate_x.py"
    p.write_text("x = 1\n")
    assert hvd.already_has_docstring(p) is False


def test_already_has_docstring_python_syntax_error(hvd, tmp_path):
    """Defensive: a syntax-broken file is not "having a docstring";
    the synthesiser should treat it as eligible for insertion (or the
    caller can choose to skip — current behaviour: returns False)."""
    p = tmp_path / "validate_x.py"
    p.write_text("def broken(\n")
    assert hvd.already_has_docstring(p) is False


def test_already_has_docstring_shell_with_header(hvd, tmp_path):
    p = tmp_path / "validate_x.sh"
    p.write_text("#!/usr/bin/env bash\n# This validator does X.\n# It also does Y.\nset -e\n")
    assert hvd.already_has_docstring(p) is True


def test_already_has_docstring_shell_only_shebang(hvd, tmp_path):
    p = tmp_path / "validate_x.sh"
    p.write_text("#!/usr/bin/env bash\nset -e\n")
    assert hvd.already_has_docstring(p) is False


# ---------------------------------------------------------------------------
# insert_into_python
# ---------------------------------------------------------------------------


def test_insert_into_python_after_shebang(hvd, tmp_path):
    p = tmp_path / "validate_x.py"
    p.write_text("#!/usr/bin/env python3\nimport sys\n")
    hvd.insert_into_python(p, "Validate x.")
    text = p.read_text()
    lines = text.splitlines()
    assert lines[0] == "#!/usr/bin/env python3"
    assert lines[1] == '"""Validate x.'
    assert "import sys" in text


def test_insert_into_python_no_shebang(hvd, tmp_path):
    p = tmp_path / "validate_x.py"
    p.write_text("import sys\n")
    hvd.insert_into_python(p, "Validate x.")
    text = p.read_text()
    assert text.startswith('"""Validate x.\n')
    assert "import sys" in text


def test_insert_into_python_preserves_todo_marker(hvd, tmp_path):
    p = tmp_path / "validate_x.py"
    p.write_text("#!/usr/bin/env python3\nx = 1\n")
    hvd.insert_into_python(p, "Validate x.")
    assert "# TODO: refine" in p.read_text()


def test_insert_into_shell_after_shebang(hvd, tmp_path):
    p = tmp_path / "validate_x.sh"
    p.write_text("#!/usr/bin/env bash\nset -e\necho hi\n")
    hvd.insert_into_shell(p, "Validate x.")
    lines = p.read_text().splitlines()
    assert lines[0] == "#!/usr/bin/env bash"
    assert lines[1] == "# Validate x."
    assert "# TODO: refine" in lines[2]


# ---------------------------------------------------------------------------
# propose / run
# ---------------------------------------------------------------------------


def test_propose_skips_files_with_existing_docstring(hvd, tmp_path):
    p = tmp_path / "validate_x.py"
    p.write_text('"""Existing."""\nx = 1\n')
    assert hvd.propose("validate_x.py", scripts_dir=tmp_path) is None


def test_propose_skips_missing_files(hvd, tmp_path):
    assert hvd.propose("validate_ghost.py", scripts_dir=tmp_path) is None


def test_propose_returns_proposal_for_eligible_file(hvd, tmp_path):
    p = tmp_path / "validate_dns_declarations.py"
    p.write_text("x = 1\n")
    proposal = hvd.propose("validate_dns_declarations.py", scripts_dir=tmp_path)
    assert proposal is not None
    assert proposal.title == "Validate DNS declarations."
    assert proposal.inserted is False


def test_run_dry_run_does_not_mutate(hvd, tmp_path):
    p = tmp_path / "validate_x.py"
    p.write_text("x = 1\n")
    original = p.read_text()
    hvd.run(["validate_x.py"], scripts_dir=tmp_path, apply=False)
    assert p.read_text() == original


def test_run_apply_writes_docstring(hvd, tmp_path):
    p = tmp_path / "validate_dns_declarations.py"
    p.write_text("x = 1\n")
    proposals = hvd.run(["validate_dns_declarations.py"], scripts_dir=tmp_path, apply=True)
    assert len(proposals) == 1
    assert proposals[0].inserted is True
    assert "Validate DNS declarations." in p.read_text()


def test_run_idempotent_after_apply(hvd, tmp_path):
    p = tmp_path / "validate_x.py"
    p.write_text("x = 1\n")
    hvd.run(["validate_x.py"], scripts_dir=tmp_path, apply=True)
    # Second run finds no eligible file (the docstring is now present).
    second = hvd.run(["validate_x.py"], scripts_dir=tmp_path, apply=True)
    assert second == []


# ---------------------------------------------------------------------------
# load_missing_docstring_filenames
# ---------------------------------------------------------------------------


def test_load_missing_docstring_filenames_picks_up_marker(hvd, tmp_path):
    cat = tmp_path / "catalogue.yaml"
    cat.write_text(
        yaml.safe_dump(
            {
                "validators": [
                    {"name": "validate_a.py", "purpose": "Some real docstring."},
                    {"name": "validate_b.py", "purpose": "(no docstring)"},
                    {"name": "validate_c.py", "purpose": "(no docstring)"},
                ]
            }
        )
    )
    out = hvd.load_missing_docstring_filenames(cat)
    assert out == ["validate_b.py", "validate_c.py"]


def test_load_missing_docstring_filenames_handles_missing_file(hvd, tmp_path):
    assert hvd.load_missing_docstring_filenames(tmp_path / "nope.yaml") == []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_no_eligible_emits_clean_message(hvd, tmp_path, capsys):
    cat = tmp_path / "catalogue.yaml"
    cat.write_text(yaml.safe_dump({"validators": []}))
    rc = hvd.main(["--catalogue", str(cat), "--scripts-dir", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "no validators missing docstrings" in out


def test_cli_dry_run_lists_proposals(hvd, tmp_path, capsys):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "validate_dns_declarations.py").write_text("x = 1\n")
    cat = tmp_path / "catalogue.yaml"
    cat.write_text(
        yaml.safe_dump({"validators": [{"name": "validate_dns_declarations.py", "purpose": "(no docstring)"}]})
    )
    rc = hvd.main(["--catalogue", str(cat), "--scripts-dir", str(scripts)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Validate DNS declarations." in out
    assert "would write" in out


def test_cli_apply_writes_docstring(hvd, tmp_path, capsys):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    target = scripts / "validate_dns_declarations.py"
    target.write_text("x = 1\n")
    cat = tmp_path / "catalogue.yaml"
    cat.write_text(
        yaml.safe_dump({"validators": [{"name": "validate_dns_declarations.py", "purpose": "(no docstring)"}]})
    )
    rc = hvd.main(["--catalogue", str(cat), "--scripts-dir", str(scripts), "--apply"])
    assert rc == 0
    assert "Validate DNS declarations." in target.read_text()


def test_cli_filenames_override_catalogue(hvd, tmp_path, capsys):
    """Operators can target a specific file without consulting the
    catalogue — useful when fixing a single new validator."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "validate_x.py").write_text("x = 1\n")
    rc = hvd.main(
        [
            "--scripts-dir",
            str(scripts),
            "--filenames",
            "validate_x.py",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "Validate x." in out


def test_cli_json_output(hvd, tmp_path, capsys):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "validate_x.py").write_text("x = 1\n")
    rc = hvd.main(
        [
            "--scripts-dir",
            str(scripts),
            "--filenames",
            "validate_x.py",
            "--json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "dry_run"
    assert len(payload["proposals"]) == 1
