"""IoC validation — prevent hardcoded operator identity from creeping back.

ADR 0385 requires all operator-specific values to derive from
inventory/group_vars/all/identity.yml.  This test catches regressions by
scanning deployable files for the concrete identity values (e.g. the actual
domain, email, operator name) in places where the template expression should
appear instead.

The test is domain-agnostic: it reads the *current* identity.yml values
and flags any file that uses them literally instead of the Jinja2 / env-var
indirection.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Directories and files exempt from scanning
# ---------------------------------------------------------------------------
EXCLUDED_PATHS = {
    ".git",
    ".claude",
    "build",
    "config/generated",       # output of generators — resolved values expected
    "docs",
    "reference-deployments",
    "tests",                  # tests can reference the concrete domain
    "versions",               # protected integration surface
    "workstreams",
    ".local",
}

EXCLUDED_FILES = {
    "inventory/group_vars/all/identity.yml",  # the source of truth itself
    "changelog.md",
    "RELEASE.md",
    "README.md",
    "workstreams.yaml",
}


def _is_excluded(path: Path) -> bool:
    rel = path.relative_to(REPO_ROOT)
    parts = rel.parts
    for exc in EXCLUDED_PATHS:
        exc_parts = Path(exc).parts
        if parts[: len(exc_parts)] == exc_parts:
            return True
    return str(rel) in EXCLUDED_FILES


# ---------------------------------------------------------------------------
# Scan helpers
# ---------------------------------------------------------------------------

SCANNABLE_EXTENSIONS = {
    ".yml", ".yaml", ".j2", ".py", ".conf", ".json", ".toml", ".sh",
}


def _scannable_files() -> Iterator[Path]:
    for f in REPO_ROOT.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix not in SCANNABLE_EXTENSIONS:
            continue
        if _is_excluded(f):
            continue
        yield f


def _load_identity_anchors() -> dict[str, str]:
    """Return identity anchor values that must NOT appear literally in code."""
    import yaml

    identity_path = REPO_ROOT / "inventory" / "group_vars" / "all" / "identity.yml"
    if not identity_path.exists():
        pytest.skip("identity.yml not found")
    with identity_path.open() as fh:
        data = yaml.safe_load(fh) or {}
    anchors = {}
    for key in ("platform_domain", "platform_operator_email", "platform_operator_name"):
        val = data.get(key)
        if isinstance(val, str) and "{{" not in val and len(val) > 3:
            anchors[key] = val
    if not anchors:
        pytest.skip("No identity anchors to validate")
    return anchors


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestNoHardcodedIdentity:
    """Scan the codebase for literal identity values that should be templated."""

    @pytest.fixture(autouse=True, scope="class")
    def identity_anchors(self):
        self.__class__._anchors = _load_identity_anchors()

    def _violations_for(self, anchor_key: str) -> list[str]:
        value = self._anchors.get(anchor_key)
        if not value:
            return []
        pattern = re.compile(re.escape(value))
        violations = []
        for f in _scannable_files():
            try:
                text = f.read_text(errors="replace")
            except Exception:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    rel = f.relative_to(REPO_ROOT)
                    violations.append(f"{rel}:{i}: {line.strip()[:120]}")
        return violations

    def test_no_hardcoded_domain(self):
        """No deployable file should contain the literal platform_domain value."""
        violations = self._violations_for("platform_domain")
        if violations:
            msg = (
                f"Found {len(violations)} file(s) with hardcoded platform_domain "
                f"({self._anchors['platform_domain']}). "
                "Use '{{{{ platform_domain }}}}' or env vars instead:\n"
            )
            # Show first 20
            msg += "\n".join(violations[:20])
            if len(violations) > 20:
                msg += f"\n... and {len(violations) - 20} more"
            pytest.fail(msg)

    def test_no_hardcoded_operator_email(self):
        """No deployable file should contain the literal operator email."""
        violations = self._violations_for("platform_operator_email")
        if violations:
            msg = (
                f"Found {len(violations)} file(s) with hardcoded operator email "
                f"({self._anchors['platform_operator_email']}). "
                "Use '{{{{ platform_operator_email }}}}' instead:\n"
            )
            msg += "\n".join(violations[:20])
            if len(violations) > 20:
                msg += f"\n... and {len(violations) - 20} more"
            pytest.fail(msg)

    def test_no_hardcoded_operator_name(self):
        """No deployable file should contain the literal operator name."""
        violations = self._violations_for("platform_operator_name")
        if violations:
            msg = (
                f"Found {len(violations)} file(s) with hardcoded operator name "
                f"({self._anchors['platform_operator_name']}). "
                "Use '{{{{ platform_operator_name }}}}' instead:\n"
            )
            msg += "\n".join(violations[:20])
            if len(violations) > 20:
                msg += f"\n... and {len(violations) - 20} more"
            pytest.fail(msg)
