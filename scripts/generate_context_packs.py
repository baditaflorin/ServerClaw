#!/usr/bin/env python3
"""Pre-render per-workstream context packs — ADR 0473 phase 11.4.

For every active workstream, materialise a single
`build/context-packs/<ws-id>.md` containing the workstream YAML body
and the referenced ADR Markdown. A cold-start agent reads ONE file and
has full context on the workstream, instead of opening the workstream
file, the ADR, and the changelog separately.

Sources:
  workstreams/active/<ws-id>.yaml      → primary
  docs/adr/<adr>-*.md                  → linked ADR (resolved by id)
  changelog.md                         → bullets that mention <ws-id>

Outputs:
  build/context-packs/<ws-id>.md       one per active workstream
  build/context-packs/index.md         link list

Idempotent. `--check` reports drift instead of writing.

Exit:
  0  wrote (or `--check` passed)
  1  `--check` reported drift
  2  invocation error
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSTREAMS_DIR = REPO_ROOT / "workstreams" / "active"
ADR_DIR = REPO_ROOT / "docs" / "adr"
CHANGELOG_PATH = REPO_ROOT / "changelog.md"
OUTPUT_DIR = REPO_ROOT / "build" / "context-packs"


def discover_workstreams(workstreams_dir: Path = WORKSTREAMS_DIR) -> list[Path]:
    if not workstreams_dir.is_dir():
        return []
    return sorted(p for p in workstreams_dir.glob("ws-*.yaml") if p.is_file())


def load_workstream(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: top-level must be a mapping")
    return payload


def find_adr_path(adr_number: str | None, adr_dir: Path = ADR_DIR) -> Path | None:
    if not adr_number:
        return None
    number = str(adr_number).zfill(4)
    matches = sorted(adr_dir.glob(f"{number}-*.md"))
    return matches[0] if matches else None


def changelog_bullets_mentioning(ws_id: str, changelog_path: Path = CHANGELOG_PATH) -> list[str]:
    if not changelog_path.is_file():
        return []
    text = changelog_path.read_text(encoding="utf-8")
    bullets: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.startswith("- "):
            if current:
                bullets.append(" ".join(current).strip())
            current = [line.lstrip("- ").rstrip()]
        elif line.startswith("  ") and current:
            current.append(line.strip())
        elif line.strip() == "":
            if current:
                bullets.append(" ".join(current).strip())
                current = []
    if current:
        bullets.append(" ".join(current).strip())
    return [b for b in bullets if ws_id in b]


def render_pack(*, workstream_path: Path, ws_payload: dict[str, Any], adr_path: Path | None, bullets: list[str]) -> str:
    ws_id = ws_payload.get("id") or workstream_path.stem
    title = ws_payload.get("title") or ""
    status = ws_payload.get("status") or "(unknown)"
    adr_ref = ws_payload.get("adr") or ""
    branch = ws_payload.get("branch") or ""

    lines: list[str] = []
    lines.append(f"# Context pack — {ws_id}")
    lines.append("")
    lines.append(f"- **Title:** {title}")
    lines.append(f"- **Status:** {status}")
    if adr_ref:
        lines.append(f"- **ADR:** {adr_ref}")
    if branch:
        lines.append(f"- **Branch:** {branch}")
    lines.append(f"- **Source:** [{workstream_path.as_posix()}]({workstream_path.as_posix()})")
    if adr_path:
        lines.append(f"- **ADR doc:** [{adr_path.as_posix()}]({adr_path.as_posix()})")
    lines.append("")

    lines.append("## Workstream registry entry")
    lines.append("")
    lines.append("```yaml")
    lines.append(yaml.safe_dump(ws_payload, sort_keys=False).rstrip())
    lines.append("```")
    lines.append("")

    if adr_path and adr_path.is_file():
        lines.append("## ADR")
        lines.append("")
        lines.append(adr_path.read_text(encoding="utf-8").rstrip())
        lines.append("")

    if bullets:
        lines.append("## Recent changelog mentions")
        lines.append("")
        for bullet in bullets:
            lines.append(f"- {bullet}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_index(packs: list[tuple[str, str]]) -> str:
    lines = ["# Context packs", "", f"{len(packs)} active workstreams.", ""]
    for ws_id, title in packs:
        lines.append(f"- [{ws_id}]({ws_id}.md) — {title}")
    lines.append("")
    return "\n".join(lines)


def write_or_check(*, output_dir: Path, workstreams_dir: Path, adr_dir: Path, changelog_path: Path, check: bool) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    rendered: dict[Path, str] = {}
    summary: list[tuple[str, str]] = []
    for ws_path in discover_workstreams(workstreams_dir):
        try:
            payload = load_workstream(ws_path)
        except (yaml.YAMLError, ValueError) as exc:
            print(f"generate_context_packs: skip {ws_path.name}: {exc}", file=sys.stderr)
            continue
        ws_id = payload.get("id") or ws_path.stem
        adr_path = find_adr_path(payload.get("adr"), adr_dir)
        bullets = changelog_bullets_mentioning(ws_id, changelog_path)
        body = render_pack(workstream_path=ws_path, ws_payload=payload, adr_path=adr_path, bullets=bullets)
        rendered[output_dir / f"{ws_id}.md"] = body
        summary.append((ws_id, payload.get("title") or ""))
    summary.sort()
    rendered[output_dir / "index.md"] = render_index(summary)

    drift: list[Path] = []
    for path, body in rendered.items():
        existing = path.read_text(encoding="utf-8") if path.is_file() else None
        if existing != body:
            if check:
                drift.append(path)
            else:
                path.write_text(body, encoding="utf-8")

    if check:
        if drift:
            for path in drift:
                print(f"generate_context_packs: stale {path.as_posix()}", file=sys.stderr)
            return 1
        return 0

    print(f"generate_context_packs: wrote {len(rendered)} files under {output_dir.as_posix()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--workstreams-dir", default=str(WORKSTREAMS_DIR))
    parser.add_argument("--adr-dir", default=str(ADR_DIR))
    parser.add_argument("--changelog-path", default=str(CHANGELOG_PATH))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    return write_or_check(
        output_dir=Path(args.output_dir),
        workstreams_dir=Path(args.workstreams_dir),
        adr_dir=Path(args.adr_dir),
        changelog_path=Path(args.changelog_path),
        check=args.check,
    )


if __name__ == "__main__":
    sys.exit(main())
