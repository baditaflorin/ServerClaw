#!/usr/bin/env python3
"""Validator catalogue generator — ADR 0449 phase 4.2.

Walks `scripts/validate_*.py` and `scripts/check_*.py`, extracts each
validator's first-line docstring + any ADR reference, and cross-checks
against `scripts/validate_repo.sh` to mark each entry's gate-membership.

Output: `build/validator-catalogue.yaml` — one row per validator. Lets
an LLM (or human) authoring a "we should validate X" review answer
"is this already covered?" via grep instead of trial-and-error.

Solves the postmortem failure mode where the 20-change review proposed
items 13/15 ("schema-validate generated artifacts" /
"service-deployability contract test") that were already shipped via
`validate_repository_data_models.py` and `validate_service_registry.py`.

CLI:

    python3 scripts/generate_validator_catalogue.py --write
    python3 scripts/generate_validator_catalogue.py --check    # exit 1 on diff
    python3 scripts/generate_validator_catalogue.py --print

Exit:
    0  success
    1  drift in --check
    2  invocation error
"""

from __future__ import annotations

import argparse
import ast
import difflib
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
VALIDATE_REPO_SH = SCRIPTS_DIR / "validate_repo.sh"
PRE_PUSH_HOOK = REPO_ROOT / ".githooks" / "pre-push"
OUTPUT_PATH = REPO_ROOT / "build" / "validator-catalogue.yaml"
GENERATED_HEADER = """\
# =============================================================================
# GENERATED — do not edit manually.
# Run: python3 scripts/generate_validator_catalogue.py --write
# Source: scripts/validate_*.py, scripts/check_*.py × scripts/validate_repo.sh
# ADR 0449 phase 4.2 — gate-coverage map for review authors and LLMs.
# =============================================================================
"""

_ADR_RE = re.compile(r"\bADR\s*(\d{3,4})\b")
# `validate_repo.sh` invokes validators by their script filename; we
# match on the script's stem (no path, no .py) to determine membership.
_INVOCATION_RE = re.compile(r"scripts/(?:check|validate)_[a-z0-9_]+(?:\.py|\.sh)?")


@dataclass(frozen=True)
class ValidatorEntry:
    name: str  # script filename (validate_X.py / check_X.py)
    purpose: str  # first paragraph of docstring (cleaned)
    related_adrs: list[str]  # zero-padded ADR numbers found in docstring
    runs_in_validate_repo_sh: bool
    runs_in_pre_push_hook: bool
    path: str  # repo-relative

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def discover_validators(scripts_dir: Path | None = None) -> list[Path]:
    """Return all validate_*.py / check_*.py / validate_*.sh under scripts/."""
    d = scripts_dir or SCRIPTS_DIR
    if not d.is_dir():
        return []
    matches: list[Path] = []
    for path in sorted(d.iterdir()):
        if not path.is_file():
            continue
        name = path.name
        if name.startswith(("validate_", "check_")) and path.suffix in (".py", ".sh"):
            # Skip self-referential generators.
            if name == "validate_repo.sh":
                continue
            matches.append(path)
    return matches


def extract_docstring(path: Path) -> str:
    """Return the module docstring (Python) or top-comment (Shell)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".py":
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return ""
        return ast.get_docstring(tree) or ""
    # Shell: first contiguous comment block after shebang.
    lines = text.splitlines()
    out: list[str] = []
    started = False
    for ln in lines:
        if ln.startswith("#!"):
            continue
        if ln.startswith("#"):
            out.append(ln.lstrip("# ").rstrip())
            started = True
        elif started:
            break
    return "\n".join(out).strip()


def first_paragraph(docstring: str) -> str:
    """Return the first paragraph — non-empty lines until a blank line.

    Collapses internal newlines into spaces. Caps at 240 chars so the
    catalogue stays grep-able rather than turning into a doc dump.
    """
    if not docstring:
        return ""
    para_lines: list[str] = []
    for line in docstring.splitlines():
        if not line.strip() and para_lines:
            break
        if line.strip():
            para_lines.append(line.strip())
    para = " ".join(para_lines).strip()
    if len(para) > 240:
        para = para[:237] + "..."
    return para


def extract_related_adrs(docstring: str) -> list[str]:
    """Return zero-padded ADR numbers cited in the docstring, deduped."""
    if not docstring:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for m in _ADR_RE.finditer(docstring):
        key = m.group(1).zfill(4)
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


# ---------------------------------------------------------------------------
# Cross-reference against gate
# ---------------------------------------------------------------------------


def _read_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def gate_invocation_set(text: str) -> set[str]:
    """Return the set of validator basenames mentioned in `text`.

    Matches both `scripts/validate_X.py` (full path) and bare
    invocations like `validate_X` inside shell functions.
    """
    out: set[str] = set()
    for m in _INVOCATION_RE.finditer(text):
        # Strip prefix and extension to get a stable key.
        token = m.group(0)
        token = token.removeprefix("scripts/")
        for ext in (".py", ".sh"):
            if token.endswith(ext):
                token = token.removesuffix(ext)
        out.add(token)
    # Also match shell `validate_<word>(` style function definitions —
    # validate_repo.sh wraps each validator in a function before calling.
    for m in re.finditer(r"^\s*(validate_[a-z0-9_]+|check_[a-z0-9_]+)\s*\(\)", text, re.MULTILINE):
        out.add(m.group(1))
    # And bare-name calls within the dispatcher (e.g. `validate_yaml` on
    # a line by itself).
    for m in re.finditer(r"^\s*(validate_[a-z0-9_]+|check_[a-z0-9_]+)\s*$", text, re.MULTILINE):
        out.add(m.group(1))
    return out


def stem_keys(filename: str) -> set[str]:
    """Return alternate keys for matching a validator filename against
    the gate-invocation set. Both `validate_x.py` and the function-name
    `validate_x` should match."""
    if filename.endswith(".py"):
        stem = filename.removesuffix(".py")
    elif filename.endswith(".sh"):
        stem = filename.removesuffix(".sh")
    else:
        stem = filename
    return {filename, stem}


def build_entries(
    *,
    scripts_dir: Path | None = None,
    validate_repo_sh: Path | None = None,
    pre_push_hook: Path | None = None,
) -> list[ValidatorEntry]:
    paths = discover_validators(scripts_dir)
    sh_text = _read_safe(validate_repo_sh or VALIDATE_REPO_SH)
    hook_text = _read_safe(pre_push_hook or PRE_PUSH_HOOK)
    sh_invocations = gate_invocation_set(sh_text)
    hook_invocations = gate_invocation_set(hook_text)
    repo_root = (scripts_dir or SCRIPTS_DIR).parent

    entries: list[ValidatorEntry] = []
    for path in paths:
        doc = extract_docstring(path)
        purpose = first_paragraph(doc)
        adrs = extract_related_adrs(doc)
        keys = stem_keys(path.name)
        in_sh = bool(keys & sh_invocations)
        in_hook = bool(keys & hook_invocations)
        try:
            rel = str(path.relative_to(repo_root))
        except ValueError:
            rel = str(path)
        entries.append(
            ValidatorEntry(
                name=path.name,
                purpose=purpose or "(no docstring)",
                related_adrs=adrs,
                runs_in_validate_repo_sh=in_sh,
                runs_in_pre_push_hook=in_hook,
                path=rel,
            )
        )
    entries.sort(key=lambda e: e.name)
    return entries


def render_yaml(entries: list[ValidatorEntry]) -> str:
    summary = {
        "total": len(entries),
        "in_validate_repo_sh": sum(1 for e in entries if e.runs_in_validate_repo_sh),
        "in_pre_push_hook": sum(1 for e in entries if e.runs_in_pre_push_hook),
        "without_docstring": sum(1 for e in entries if e.purpose == "(no docstring)"),
        "without_related_adr": sum(1 for e in entries if not e.related_adrs),
    }
    body = {
        "schema_version": 1,
        "generator": "scripts/generate_validator_catalogue.py",
        "summary": summary,
        "validators": [e.to_dict() for e in entries],
    }
    return GENERATED_HEADER + yaml.safe_dump(body, sort_keys=False)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--write", action="store_true", help="Write build/validator-catalogue.yaml")
    parser.add_argument("--check", action="store_true", help="Exit 1 if regenerated content drifts")
    parser.add_argument("--print", action="store_true", help="Print to stdout (no file write)")
    parser.add_argument("--root", default=str(REPO_ROOT), help="Repo root override (for tests)")
    args = parser.parse_args(argv)

    if not (args.write or args.check or args.print):
        parser.print_help(sys.stderr)
        return 2

    repo_root = Path(args.root)
    entries = build_entries(
        scripts_dir=repo_root / "scripts",
        validate_repo_sh=repo_root / "scripts" / "validate_repo.sh",
        pre_push_hook=repo_root / ".githooks" / "pre-push",
    )
    rendered = render_yaml(entries)

    if args.print:
        sys.stdout.write(rendered)

    out_path = repo_root / "build" / "validator-catalogue.yaml"

    if args.write:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered)
        print(f"wrote {out_path.relative_to(repo_root)} ({len(entries)} validators)")

    if args.check:
        existing = out_path.read_text() if out_path.is_file() else ""
        if existing != rendered:
            diff = difflib.unified_diff(
                existing.splitlines(keepends=True),
                rendered.splitlines(keepends=True),
                fromfile=f"{out_path.relative_to(repo_root)} (on disk)",
                tofile=f"{out_path.relative_to(repo_root)} (regenerated)",
            )
            sys.stdout.writelines(diff)
            print(
                "\ngenerate_validator_catalogue: drift detected. Run --write to refresh.",
                file=sys.stderr,
            )
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
