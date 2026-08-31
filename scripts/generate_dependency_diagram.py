#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

import yaml

from controller_automation_toolkit import emit_cli_error, repo_path
from dependency_graph import load_dependency_graph, render_dependency_page
from ops_portal.contextual_help import build_docs_page_help


DEFAULT_OUTPUT = repo_path("docs", "site-generated", "architecture", "dependency-graph.md")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate the dependency graph markdown page.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Destination markdown file.",
    )
    parser.add_argument("--write", action="store_true", help="Write the rendered markdown.")
    parser.add_argument("--check", action="store_true", help="Verify the rendered markdown is current.")
    parser.add_argument("--stdout", action="store_true", help="Print the rendered markdown.")
    return parser


def render() -> str:
    graph = load_dependency_graph(validate_schema=True)
    target_path = Path("architecture", "dependency-graph.md")
    content = render_dependency_page(graph)
    content = re.sub(r"\A---\n.*?\n---\n+", "", content, count=1, flags=re.DOTALL)
    content = re.sub(
        r'\A!!! (?:note|warning|danger) "Sensitivity: [^"]+"\n(?: {4}.*\n)+\n*',
        "",
        content,
        count=1,
    )
    metadata = {
        "sensitivity": "INTERNAL",
        "portal_display": "full",
        "tags": ["architecture", "dependency-graph"],
        "pagefind_section": "architecture",
        "pagefind_audience": ["contributors", "operators"],
        "contextual_help": build_docs_page_help(target_path=target_path, title="Dependency Graph"),
    }
    frontmatter = yaml.safe_dump(metadata, sort_keys=False, default_flow_style=False).strip()
    notice = '!!! note "Sensitivity: INTERNAL"\n    This page is intended for authenticated operators and internal collaborators.\n'
    return f"---\n{frontmatter}\n---\n\n{notice}\n{content.lstrip()}"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if sum(bool(flag) for flag in (args.write, args.check, args.stdout)) != 1:
        parser.error("choose exactly one of --write, --check, or --stdout")

    try:
        rendered = render()
        if args.stdout:
            print(rendered, end="")
            return 0
        if args.write:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered)
            print(f"Updated dependency diagram: {args.output}")
            return 0
        current = args.output.read_text() if args.output.exists() else ""
        if current != rendered:
            with tempfile.NamedTemporaryFile("w", delete=False, suffix=".md") as handle:
                handle.write(rendered)
            raise ValueError(f"{args.output} is stale. Run 'python3 scripts/generate_dependency_diagram.py --write'.")
        print("Dependency diagram OK")
        return 0
    except Exception as exc:
        return emit_cli_error("dependency diagram", exc)


if __name__ == "__main__":
    sys.exit(main())
