#!/usr/bin/env python3
"""Workstream → ADR → role traceability generator — ADR 0447 item 19.

Joins three sources of truth that today live in three trees:

  - workstreams/active/*.yaml      → workstream → ADRs implemented
  - docs/adr/.index.yaml           → ADR → status, keywords, concern
  - workstream::shared_surfaces    → workstream → role/file paths

Emits a single `build/traceability.yaml` that lets an LLM (or operator)
answer "what is the state of multi-deployment work?" in one read,
instead of crawling three trees and reconstructing the join.

Each output entry pairs an active workstream with the resolved ADR
metadata it implements, the dependency ADRs, and the surfaces it touches.
Dangling references (workstream `adr:` field that doesn't resolve to a
real ADR; `shared_surfaces` paths that don't exist on disk) are
reported as `dangling_*` lists per workstream — the validator surfaces
those as advisory warnings.

CLI:

    python3 scripts/generate_traceability.py --write       # write build/traceability.yaml
    python3 scripts/generate_traceability.py --check       # exit 1 on diff
    python3 scripts/generate_traceability.py --validate    # exit 1 on dangling refs

Exit codes:
    0  success (or no dangling refs in --validate)
    1  drift in --check, dangling refs in --validate
    2  invocation error
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ADR_INDEX_PATH = REPO_ROOT / "docs" / "adr" / ".index.yaml"
WORKSTREAMS_DIR = REPO_ROOT / "workstreams" / "active"
OUTPUT_PATH = REPO_ROOT / "build" / "traceability.yaml"
GENERATED_HEADER = """\
# =============================================================================
# GENERATED — do not edit manually.
# Run: python3 scripts/generate_traceability.py --write
# Source: workstreams/active/*.yaml × docs/adr/.index.yaml
# ADR 0447 — workstream → ADR → role traceability matrix.
# =============================================================================
"""


@dataclass(frozen=True)
class WorkstreamTrace:
    workstream_id: str
    title: str
    status: str
    ready_to_merge: bool
    primary_adr: str | None
    adr_resolved: dict[str, Any] | None  # entry from .index.yaml or None
    depends_on: list[str]
    dangling_dependencies: list[str]  # depends_on entries that don't resolve
    surfaces_total: int
    surfaces_present: int
    dangling_surfaces: list[str]  # paths that don't exist on disk

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "workstream_id": self.workstream_id,
            "title": self.title,
            "status": self.status,
            "ready_to_merge": self.ready_to_merge,
            "primary_adr": self.primary_adr,
            "depends_on": self.depends_on,
            "surfaces": {
                "total": self.surfaces_total,
                "present_on_disk": self.surfaces_present,
            },
        }
        if self.adr_resolved is not None:
            out["adr"] = {
                k: self.adr_resolved.get(k)
                for k in (
                    "title",
                    "implementation_status",
                    "currently_describes",
                    "concern",
                    "path",
                )
                if k in self.adr_resolved
            }
        if self.dangling_dependencies:
            out["dangling_dependencies"] = self.dangling_dependencies
        if self.dangling_surfaces:
            out["dangling_surfaces"] = self.dangling_surfaces
        return out


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def load_adr_index(path: Path) -> dict[str, dict[str, Any]]:
    """Return {adr_number_str: entry_dict} from the ADR index.

    The full ADR set isn't in `.index.yaml` itself — that file just
    points at shards. `.index.yaml` carries `latest_adrs` for top-of-mind
    entries, and the canonical full list lives at
    `docs/adr/index/by-range/*.yaml`. This loader reads both shapes:

      1. legacy: top-level `adrs` list (synthetic test fixtures)
      2. real:   walk `<index_dir>/index/by-range/*.yaml` if present, plus
                 `latest_adrs` from the root index for completeness.

    Keys are normalised to zero-padded 4-digit strings ("0443") so
    callers can look up by either the canonical ADR number or a
    workstream's `adr:` field (which may be int or string).
    """
    if not path.is_file():
        raise FileNotFoundError(f"missing ADR index at {path}")
    out: dict[str, dict[str, Any]] = {}

    def _ingest(entries: Any) -> None:
        if not isinstance(entries, list):
            return
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            number = entry.get("adr") or entry.get("number")
            if number is None:
                continue
            key = str(number).zfill(4)
            # First wins — the by-range shards are the authoritative
            # source; latest_adrs is best-effort.
            out.setdefault(key, entry)

    # Walk shards if present (real repo layout).
    by_range_dir = path.parent / "index" / "by-range"
    if by_range_dir.is_dir():
        for shard_path in sorted(by_range_dir.glob("*.yaml")):
            try:
                shard = yaml.safe_load(shard_path.read_text()) or {}
            except yaml.YAMLError:
                continue
            _ingest(shard.get("adrs"))

    # Also read the root index (legacy `adrs` list AND `latest_adrs`).
    data = yaml.safe_load(path.read_text()) or {}
    _ingest(data.get("adrs"))
    _ingest(data.get("latest_adrs"))
    return out


def load_workstreams(
    directory: Path,
    *,
    repo_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Return a list of parsed active workstream dicts.

    Files starting with `_` or `.` are skipped to allow the directory to
    carry README-style siblings without polluting the join.

    Each loaded dict carries `__source_path` relative to `repo_root`
    (defaults to the module-level REPO_ROOT). Falls back to an absolute
    path if the file is outside the supplied root — which only happens
    in tests using `tmp_path`, never in production.

    Each loaded dict also carries `__pending_surfaces` — a set of
    `shared_surfaces` values whose source line carried a
    `# pending: <reason>` marker (ADR 0455 phase 7.1). The build pass
    uses that to skip the dangling-existence check for forward-looking
    references.
    """
    if not directory.is_dir():
        return []
    root = repo_root if repo_root is not None else REPO_ROOT
    out: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.yaml")):
        if path.name.startswith(("_", ".")):
            continue
        try:
            text = path.read_text()
            data = yaml.safe_load(text) or {}
        except (yaml.YAMLError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        try:
            data["__source_path"] = str(path.relative_to(root))
        except ValueError:
            data["__source_path"] = str(path)
        data["__pending_surfaces"] = extract_pending_markers(text)
        out.append(data)
    return out


_PENDING_MARKER_RE = re.compile(
    r"""
    ^\s*-\s+                    # YAML list-item dash + space
    (?P<value>\S+?)             # the entry value (greedy non-whitespace)
    \s*\#\s*pending\s*:\s*      # the # pending: marker
    (?P<reason>\S.*?)           # the reason (non-empty)
    $
    """,
    re.VERBOSE,
)


def extract_pending_markers(yaml_text: str) -> set[str]:
    """Return the set of `shared_surfaces` values annotated with
    `# pending: <reason>` in the raw YAML text.

    Forward-looking surfaces (a generated artifact that doesn't exist
    yet, the archive path a workstream will move to once archived,
    blocked-on-decision targets) need a way to live in
    `shared_surfaces` without being false-positive dangling hits.
    Mirrors the `# late-bound-allow:` pattern in ADR 0445's late-bound
    topology lint — same shape, same audit semantics.

    The marker is parsed from the raw YAML text rather than via YAML
    metadata because PyYAML's safe_load discards comments. The match
    is anchored at start-of-line dash to avoid catching prose
    mentions in `summary:` or `notes:` blocks that happen to contain
    `# pending:`.

    A reason is required. `# pending:` (empty reason) does not match —
    the marker only fires when there's content after the colon.
    """
    out: set[str] = set()
    for line in yaml_text.splitlines():
        m = _PENDING_MARKER_RE.match(line)
        if m:
            value = m.group("value").strip("\"'")
            if value:
                out.add(value)
    return out


def _looks_like_prose(value: str) -> bool:
    """Return True if `value` is a conceptual surface, not a file path.

    Workstream YAMLs sometimes list `shared_surfaces` entries like
    "workflow events" or "fork bootstrap entry point" — descriptions of
    a surface area, not paths the validator can stat. The heuristic:
    contains whitespace AND has no path separator. That keeps "Makefile"
    and "VERSION" (real bare-name files) eligible while skipping prose.
    """
    s = value.strip()
    if not s:
        return True
    if "/" in s:
        return False
    return any(ch.isspace() for ch in s)


def _normalise_adr_ref(value: Any) -> str | None:
    """Return a 4-digit ADR key or None.

    Accepts integer, "0445", "445", "adr-0445-something" — the
    workstream YAMLs are inconsistent.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    # Strip "adr-" prefix and any trailing "-slug".
    if s.lower().startswith("adr-"):
        s = s[4:]
    head = s.split("-", 1)[0]
    if not head.isdigit():
        return None
    return head.zfill(4)


# ---------------------------------------------------------------------------
# Join
# ---------------------------------------------------------------------------


def build_traceability(
    workstreams: list[dict[str, Any]],
    adr_index: dict[str, dict[str, Any]],
    repo_root: Path,
) -> list[WorkstreamTrace]:
    """Compute one WorkstreamTrace per active workstream."""
    traces: list[WorkstreamTrace] = []
    for ws in workstreams:
        ws_id = str(ws.get("id") or ws.get("__source_path") or "(unknown)")
        title = str(ws.get("title") or "")
        status = str(ws.get("status") or "")
        ready = bool(ws.get("ready_to_merge") or False)

        primary_key = _normalise_adr_ref(ws.get("adr"))
        adr_resolved = adr_index.get(primary_key) if primary_key else None

        depends_on_raw = ws.get("depends_on") or []
        if not isinstance(depends_on_raw, list):
            depends_on_raw = []
        depends_on: list[str] = [str(d) for d in depends_on_raw]
        dangling_deps: list[str] = []
        for dep in depends_on:
            key = _normalise_adr_ref(dep)
            if key is None or key not in adr_index:
                dangling_deps.append(dep)

        surfaces_raw = ws.get("shared_surfaces") or []
        if not isinstance(surfaces_raw, list):
            surfaces_raw = []
        # Filter out entries that aren't path-shaped:
        #   - globs (`**`, `*`)         — contracts, not exact paths
        #   - prose with whitespace     — workstreams sometimes list
        #                                 conceptual surfaces ("workflow
        #                                 events", "fork bootstrap entry
        #                                 point") under shared_surfaces.
        #                                 The traceability validator can't
        #                                 stat those, so flagging them as
        #                                 dangling is a false positive.
        # ADR 0455 phase 7.1 — also exclude entries annotated with a
        # `# pending: <reason>` comment in the source YAML. These are
        # forward-looking surfaces (artifacts not yet generated, archive
        # paths a workstream will move to, blocked-on-decision targets)
        # whose absence is intentional. The reason lives in-line so a
        # monthly audit can re-evaluate whether the marker still
        # applies.
        pending_surfaces = ws.get("__pending_surfaces") or set()
        surface_paths = [
            str(s)
            for s in surfaces_raw
            if "*" not in str(s) and not _looks_like_prose(str(s)) and str(s) not in pending_surfaces
        ]
        present = sum(1 for s in surface_paths if (repo_root / s).exists())
        dangling_surfaces = [s for s in surface_paths if not (repo_root / s).exists()]

        traces.append(
            WorkstreamTrace(
                workstream_id=ws_id,
                title=title,
                status=status,
                ready_to_merge=ready,
                primary_adr=primary_key,
                adr_resolved=adr_resolved,
                depends_on=depends_on,
                dangling_dependencies=dangling_deps,
                surfaces_total=len(surface_paths),
                surfaces_present=present,
                dangling_surfaces=dangling_surfaces,
            )
        )
    return traces


def render_yaml(traces: list[WorkstreamTrace]) -> str:
    summary = {
        "total_workstreams": len(traces),
        "with_resolved_adr": sum(1 for t in traces if t.adr_resolved is not None),
        "with_dangling_dependencies": sum(1 for t in traces if t.dangling_dependencies),
        "with_dangling_surfaces": sum(1 for t in traces if t.dangling_surfaces),
        "ready_to_merge": sum(1 for t in traces if t.ready_to_merge),
    }
    body = {
        "schema_version": 1,
        "generator": "scripts/generate_traceability.py",
        "summary": summary,
        "workstreams": [t.to_dict() for t in traces],
    }
    return GENERATED_HEADER + yaml.safe_dump(body, sort_keys=False)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _generate(repo_root: Path) -> str:
    adr_index = load_adr_index(repo_root / "docs" / "adr" / ".index.yaml")
    workstreams = load_workstreams(repo_root / "workstreams" / "active", repo_root=repo_root)
    traces = build_traceability(workstreams, adr_index, repo_root)
    return render_yaml(traces)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--write", action="store_true", help="Write build/traceability.yaml")
    parser.add_argument("--check", action="store_true", help="Exit 1 if generated content drifts from on-disk file")
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Exit 1 if any workstream has dangling ADR refs or dangling shared_surfaces",
    )
    parser.add_argument("--root", default=str(REPO_ROOT), help="Repo root (default: this script's repo)")
    args = parser.parse_args(argv)

    if not (args.write or args.check or args.validate):
        parser.print_help(sys.stderr)
        return 2

    repo_root = Path(args.root)
    try:
        rendered = _generate(repo_root)
    except FileNotFoundError as exc:
        print(f"generate_traceability: {exc}", file=sys.stderr)
        return 2

    out_path = repo_root / "build" / "traceability.yaml"

    if args.write:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered)
        print(f"wrote {out_path.relative_to(repo_root)}")

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
                "\ngenerate_traceability: drift detected. Run --write to refresh.",
                file=sys.stderr,
            )
            return 1

    if args.validate:
        adr_index = load_adr_index(repo_root / "docs" / "adr" / ".index.yaml")
        workstreams = load_workstreams(repo_root / "workstreams" / "active", repo_root=repo_root)
        traces = build_traceability(workstreams, adr_index, repo_root)
        broken = [t for t in traces if t.dangling_dependencies or t.dangling_surfaces]
        if broken:
            print(
                f"generate_traceability: {len(broken)} workstream(s) have dangling refs:",
                file=sys.stderr,
            )
            for t in broken:
                print(f"  {t.workstream_id}", file=sys.stderr)
                for dep in t.dangling_dependencies:
                    print(f"    dangling dependency: {dep}", file=sys.stderr)
                for surface in t.dangling_surfaces:
                    print(f"    missing surface:     {surface}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
