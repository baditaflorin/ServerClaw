#!/usr/bin/env python3

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PLATFORM_ROOT = REPO_ROOT / "platform"
SCRIPTS_ROOT = REPO_ROOT / "scripts"
LOADER_FUNCTIONS = {"spec_from_file_location", "load_module_from_repo"}


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    code: str
    detail: str


def load_script_module_names(repo_root: Path) -> set[str]:
    scripts_root = repo_root / "scripts"
    names: set[str] = set()
    if not scripts_root.exists():
        return names
    for path in scripts_root.iterdir():
        if path.name.startswith("."):
            continue
        if path.is_file() and path.suffix == ".py" and path.stem != "__init__":
            names.add(path.stem)
            continue
        if path.is_dir() and (path / "__init__.py").exists():
            names.add(path.name)
    return names


def iter_platform_files(repo_root: Path) -> list[Path]:
    return sorted(path for path in (repo_root / "platform").rglob("*.py") if path.is_file())


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _constant_strings(node: ast.AST) -> set[str]:
    values: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            values.add(child.value)
    return values


def _module_targets_scripts(module_name: str, script_modules: set[str]) -> bool:
    normalized = module_name.strip()
    if not normalized:
        return False
    if normalized == "scripts" or normalized.startswith("scripts."):
        return True
    return normalized.split(".", 1)[0] in script_modules


def _line_numbers_for(source: str, needle: str) -> list[int]:
    return [index for index, line in enumerate(source.splitlines(), start=1) if needle in line]


def _import_violations(
    path: Path,
    tree: ast.AST,
    *,
    script_modules: set[str],
) -> list[Violation]:
    violations: list[Violation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _module_targets_scripts(alias.name, script_modules):
                    violations.append(
                        Violation(
                            path=path,
                            line=node.lineno,
                            code="outward-import",
                            detail=f"platform code imports script module '{alias.name}'",
                        )
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.level != 0 or node.module is None:
                continue
            if _module_targets_scripts(node.module, script_modules):
                violations.append(
                    Violation(
                        path=path,
                        line=node.lineno,
                        code="outward-import",
                        detail=f"platform code imports from script module '{node.module}'",
                    )
                )
    return violations


def _dynamic_loader_violations(
    path: Path,
    source: str,
    tree: ast.AST,
    *,
    script_modules: set[str],
) -> list[Violation]:
    violations: list[Violation] = []
    has_script_path_marker = bool(re.search(r"""['"]scripts['"]|scripts/[^'"]+\.py""", source))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        call_name = _call_name(node.func)
        string_args = _constant_strings(node)

        if call_name.endswith("import_module") and node.args:
            target = node.args[0]
            if isinstance(target, ast.Constant) and isinstance(target.value, str):
                if _module_targets_scripts(target.value, script_modules):
                    violations.append(
                        Violation(
                            path=path,
                            line=node.lineno,
                            code="dynamic-import",
                            detail=f"platform code dynamically imports script module '{target.value}'",
                        )
                    )

        if call_name == "sys.path.insert" and has_script_path_marker:
            violations.append(
                Violation(
                    path=path,
                    line=node.lineno,
                    code="scripts-path",
                    detail="platform code mutates sys.path to reach repo scripts/",
                )
            )
            continue

        if call_name.split(".")[-1] in LOADER_FUNCTIONS and has_script_path_marker:
            detail = "platform code dynamically loads a script file"
            if "scripts" in string_args:
                detail = "platform code dynamically loads from repo scripts/"
            violations.append(
                Violation(
                    path=path,
                    line=node.lineno,
                    code="dynamic-script-load",
                    detail=detail,
                )
            )
    return violations


def _dedupe(violations: list[Violation]) -> list[Violation]:
    seen: set[tuple[Path, int, str, str]] = set()
    unique: list[Violation] = []
    for violation in sorted(violations, key=lambda item: (str(item.path), item.line, item.code, item.detail)):
        key = (violation.path, violation.line, violation.code, violation.detail)
        if key in seen:
            continue
        seen.add(key)
        unique.append(violation)
    return unique


def validate_dependency_direction(repo_root: Path | None = None) -> list[Violation]:
    resolved_root = (repo_root or REPO_ROOT).resolve()
    script_modules = load_script_module_names(resolved_root)
    violations: list[Violation] = []
    for path in iter_platform_files(resolved_root):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        violations.extend(_import_violations(path, tree, script_modules=script_modules))
        violations.extend(_dynamic_loader_violations(path, source, tree, script_modules=script_modules))
    return _dedupe(violations)


def format_violations(violations: list[Violation], *, repo_root: Path | None = None) -> str:
    resolved_root = (repo_root or REPO_ROOT).resolve()
    lines = ["ADR 0208 dependency-direction violations:"]
    for violation in violations:
        try:
            display_path = violation.path.resolve().relative_to(resolved_root)
        except ValueError:
            display_path = violation.path
        lines.append(f"- {display_path}:{violation.line}: {violation.detail}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate that reusable platform code does not depend outward on scripts/ composition roots."
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)

    violations = validate_dependency_direction(args.repo_root)
    if violations:
        print(format_violations(violations, repo_root=args.repo_root), file=sys.stderr)
        return 1
    print("Dependency direction OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
