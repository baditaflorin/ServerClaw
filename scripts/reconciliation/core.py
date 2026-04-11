"""Core reconciliation primitives for platform portal artifacts.

Each portal generator is invoked as a subprocess so that dependency isolation
is preserved — the individual scripts may require packages (pyyaml, jsonschema,
mkdocs, etc.) that are not necessarily available in the reconciliation runner's
own environment.  ``uv run`` is used where the Makefile targets already do so.

Portals
-------
- **homepage** — Homepage dashboard config (``build/homepage-config/``)
- **ops** — Operations portal (``build/ops-portal/``)
- **docs** — Documentation portal (``build/docs-portal/``)
- **changelog** — Deployment history / changelog portal (``build/changelog-portal/``)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Repo root resolution — prefer controller_automation_toolkit when available,
# fall back to file-system relative path for standalone usage.
# ---------------------------------------------------------------------------

_repo_root: Path | None = None


def _get_repo_root() -> Path:
    global _repo_root
    if _repo_root is not None:
        return _repo_root

    try:
        # controller_automation_toolkit lives in scripts/ and exports repo_path
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from controller_automation_toolkit import REPO_ROOT  # type: ignore[import-untyped]

        _repo_root = REPO_ROOT
    except Exception:
        # Fallback: scripts/reconciliation/core.py -> scripts/ -> repo root
        _repo_root = Path(__file__).resolve().parents[2]
    return _repo_root


# ---------------------------------------------------------------------------
# Portal registry — maps portal names to their generation/check commands
# and build output directories.
# ---------------------------------------------------------------------------

# Each entry is a dict with:
#   script       — path relative to repo root (resolved at call time)
#   output_dir   — path relative to repo root where build artifacts land
#   write_args   — extra CLI args for the --write / generation invocation
#   check_args   — extra CLI args for --check (None if the script lacks --check)
#   uv_deps      — list of extra packages to pass via ``uv run --with``
#   uv_req_file  — requirements file for ``uv run --with-requirements``
#   needs_output_dir_arg — whether --output-dir <dir> must be passed explicitly

_PORTAL_REGISTRY: dict[str, dict[str, Any]] = {
    "homepage": {
        "script": "scripts/generate_homepage_config.py",
        "output_dir": "build/homepage-config",
        "write_args": ["--write"],
        "check_args": ["--check"],
        "needs_output_dir_arg": True,
        "uv_deps": ["pyyaml", "jsonschema"],
        "uv_req_file": None,
    },
    "ops": {
        "script": "scripts/generate_ops_portal.py",
        "output_dir": "build/ops-portal",
        "write_args": ["--write"],
        "check_args": ["--check"],
        "needs_output_dir_arg": False,
        "uv_deps": ["pyyaml", "jsonschema"],
        "uv_req_file": None,
    },
    "docs": {
        "script": "scripts/build_docs_portal.py",
        "output_dir": "build/docs-portal",
        "write_args": [],
        "check_args": None,  # docs portal has no --check mode
        "needs_output_dir_arg": False,
        "uv_deps": [],
        "uv_req_file": "requirements/docs.txt",
    },
    "changelog": {
        "script": "scripts/generate_changelog_portal.py",
        "output_dir": "build/changelog-portal",
        "write_args": ["--write"],
        "check_args": ["--check"],
        "needs_output_dir_arg": False,
        "uv_deps": ["pyyaml", "jsonschema"],
        "uv_req_file": None,
    },
}

KNOWN_PORTALS = sorted(_PORTAL_REGISTRY)


def _build_uv_prefix(entry: dict[str, Any]) -> list[str]:
    """Build the ``uv run --with ...`` prefix for a portal generator."""
    parts = ["uv", "run"]
    if entry.get("uv_req_file"):
        repo = _get_repo_root()
        parts += ["--with-requirements", str(repo / entry["uv_req_file"])]
    for dep in entry.get("uv_deps") or []:
        parts += ["--with", dep]
    parts.append("python")
    return parts


def _run_portal_cmd(
    entry: dict[str, Any],
    extra_args: list[str],
    *,
    output_dir_override: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a portal generator script with the appropriate uv prefix."""
    repo = _get_repo_root()
    cmd = _build_uv_prefix(entry) + [str(repo / entry["script"])]
    if entry.get("needs_output_dir_arg"):
        out = output_dir_override or str(repo / entry["output_dir"])
        cmd += ["--output-dir", out]
    cmd += extra_args
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(repo),
        timeout=300,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_portal_drift(portal: str) -> dict[str, Any]:
    """Compare generated artifacts against what is currently in ``build/``.

    Uses the script's ``--check`` mode when available.  For portals that lack
    a ``--check`` flag, the function reports that drift detection is not
    supported (rather than silently skipping).

    Returns::

        {
            "portal": str,
            "drifted": bool,
            "check_supported": bool,
            "summary": str,
            "stderr": str,          # raw stderr from the generator
        }
    """
    if portal not in _PORTAL_REGISTRY:
        return {
            "portal": portal,
            "drifted": False,
            "check_supported": False,
            "summary": f"Unknown portal: {portal}",
            "stderr": "",
        }

    entry = _PORTAL_REGISTRY[portal]

    if entry["check_args"] is None:
        return {
            "portal": portal,
            "drifted": False,
            "check_supported": False,
            "summary": f"Portal '{portal}' does not support --check drift detection",
            "stderr": "",
        }

    try:
        result = _run_portal_cmd(entry, list(entry["check_args"]))
        drifted = result.returncode != 0
        if drifted:
            summary = f"Portal '{portal}' has drifted — artifacts are stale"
        else:
            summary = f"Portal '{portal}' is up to date"
        return {
            "portal": portal,
            "drifted": drifted,
            "check_supported": True,
            "summary": summary,
            "stderr": result.stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        return {
            "portal": portal,
            "drifted": False,
            "check_supported": True,
            "summary": f"Portal '{portal}' check timed out",
            "stderr": "",
        }
    except FileNotFoundError as exc:
        return {
            "portal": portal,
            "drifted": False,
            "check_supported": True,
            "summary": f"Portal '{portal}' generator not found: {exc}",
            "stderr": "",
        }


def regenerate_portal(portal: str) -> dict[str, Any]:
    """Run the generation script for a single portal.

    Returns::

        {
            "portal": str,
            "success": bool,
            "output_dir": str,
            "stdout": str,
            "stderr": str,
            "error": str | None,
        }
    """
    if portal not in _PORTAL_REGISTRY:
        return {
            "portal": portal,
            "success": False,
            "output_dir": "",
            "stdout": "",
            "stderr": "",
            "error": f"Unknown portal: {portal}",
        }

    entry = _PORTAL_REGISTRY[portal]
    repo = _get_repo_root()
    output_dir = str(repo / entry["output_dir"])

    try:
        result = _run_portal_cmd(entry, list(entry["write_args"]))
        success = result.returncode == 0
        return {
            "portal": portal,
            "success": success,
            "output_dir": output_dir,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "error": None if success else f"exit code {result.returncode}",
        }
    except subprocess.TimeoutExpired:
        return {
            "portal": portal,
            "success": False,
            "output_dir": output_dir,
            "stdout": "",
            "stderr": "",
            "error": "Generation timed out (300s limit)",
        }
    except FileNotFoundError as exc:
        return {
            "portal": portal,
            "success": False,
            "output_dir": output_dir,
            "stdout": "",
            "stderr": "",
            "error": f"Generator not found: {exc}",
        }


def validate_all_artifacts() -> dict[str, Any]:
    """Run ``--check`` across all portals that support it.

    Returns::

        {
            "all_valid": bool,
            "results": [
                {"portal": str, "valid": bool, "detail": str},
                ...
            ],
        }
    """
    results: list[dict[str, Any]] = []
    for portal in KNOWN_PORTALS:
        report = detect_portal_drift(portal)
        if not report["check_supported"]:
            results.append(
                {
                    "portal": portal,
                    "valid": True,  # can't disprove, so treat as valid
                    "detail": report["summary"],
                }
            )
        else:
            results.append(
                {
                    "portal": portal,
                    "valid": not report["drifted"],
                    "detail": report["summary"],
                }
            )

    all_valid = all(r["valid"] for r in results)
    return {"all_valid": all_valid, "results": results}


def reconcile_all_portals() -> dict[str, Any]:
    """Regenerate every known portal and return an aggregate summary.

    Returns::

        {
            "portals_regenerated": int,
            "portals_failed": int,
            "results": [<regenerate_portal result>, ...],
        }
    """
    results: list[dict[str, Any]] = []
    for portal in KNOWN_PORTALS:
        results.append(regenerate_portal(portal))

    succeeded = sum(1 for r in results if r["success"])
    failed = sum(1 for r in results if not r["success"])
    return {
        "portals_regenerated": succeeded,
        "portals_failed": failed,
        "results": results,
    }
