"""Phase-1 lint — ADR 0438.

Once `platform_identity` exists as a flavor-aware surface, there is no reason
for a root-facts file to reach for `platform_domain | split('.') | first`:
that expression picks the first DNS label with zero regard for the downstream
identifier regime (SQL, PVE, POSIX, DNS). Every one of those raw splits is a
latent fork-breaking bug — it worked for `lv3` by coincidence and failed
silently for `0fork`.

This test scans the Tier 0 root files and fails on any `split('.') | first`
that is not inside a code comment or inside the platform_identity derivation
itself. It is intentionally NARROW: it covers root facts only. Role-scope
prefix literals are a Phase 2 problem and will get their own sweep + lint.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# Files that root-level facts should no longer contain raw split('.') | first.
# The sole exception is the platform_config_prefix legacy alias on line 21 of
# identity.yml — that line IS the `config_prefix` definition, so the raw
# expression is the definition itself. Everything else should flow through
# `platform_identity.<flavor>_prefix`.
ROOT_FILES = [
    REPO_ROOT / "inventory" / "group_vars" / "all" / "identity.yml",
]

# Callsites that are allowed to keep the raw expression. Each entry is
# (relative_path, line_substring_that_anchors_the_exemption). Keep this list
# short and explain each one — a growing allow-list is a smell.
ALLOWED_RAW_SPLITS = [
    (
        "inventory/group_vars/all/identity.yml",
        "platform_config_prefix:",  # IS the definition of config_prefix itself
    ),
]


RAW_SPLIT_RE = re.compile(r"platform_domain\s*\|\s*split\(\s*['\"]\.['\"]\s*\)\s*\|\s*first")


def _is_allowed(rel_path: str, line: str) -> bool:
    for allow_path, allow_anchor in ALLOWED_RAW_SPLITS:
        if rel_path == allow_path and allow_anchor in line:
            return True
    return False


@pytest.mark.parametrize("path", ROOT_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_root_file_has_no_raw_domain_split(path: Path) -> None:
    """Root facts use `platform_identity.<flavor>_prefix`, not raw splits.

    This is the Phase-1 invariant: once the filter plugin exists, every
    prefix derivation goes through it so the flavor is explicit. A raw
    split at Tier 0 is a latent fork-breaker.
    """
    assert path.exists(), f"root file missing: {path}"
    rel = str(path.relative_to(REPO_ROOT))

    violations = []
    for line_no, line in enumerate(path.read_text().splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith("#"):  # full-line comment
            continue
        if not RAW_SPLIT_RE.search(line):
            continue
        if _is_allowed(rel, line):
            continue
        violations.append(f"{rel}:{line_no}: {line.strip()}")

    assert not violations, (
        "Raw `platform_domain | split('.') | first` found at Tier 0. "
        "Replace with `platform_identity.<config|sql|pve|unix>_prefix` or "
        "`platform_identity.dns_label`, choosing the flavor that matches the "
        "downstream consumer's identifier regime (ADR 0438):\n  " + "\n  ".join(violations)
    )
