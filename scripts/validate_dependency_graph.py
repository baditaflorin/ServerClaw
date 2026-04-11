#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys

from controller_automation_toolkit import emit_cli_error
from dependency_graph import load_dependency_graph


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description="Validate the service dependency graph.")


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    try:
        load_dependency_graph(validate_schema=True)
        print("Dependency graph OK")
        return 0
    except Exception as exc:
        return emit_cli_error("dependency graph", exc)


if __name__ == "__main__":
    sys.exit(main())
