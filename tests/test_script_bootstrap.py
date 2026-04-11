from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"


def _first_line_matching(lines: list[str], needle: str) -> int | None:
    for index, line in enumerate(lines, 1):
        if needle in line:
            return index
    return None


def test_platform_import_scripts_bootstrap_repo_root_first() -> None:
    failures: list[str] = []
    for path in sorted(SCRIPTS_DIR.glob("*.py")):
        lines = path.read_text(encoding="utf-8").splitlines()
        platform_line = None
        for index, line in enumerate(lines, 1):
            if "from platform." in line or "import platform." in line:
                platform_line = index
                break
        if platform_line is None:
            continue
        bootstrap_line = None
        for index, line in enumerate(lines[: platform_line - 1], 1):
            if "ensure_repo_root_on_path(__file__)" in line or "sys.path.insert(" in line:
                bootstrap_line = index
                break
        if bootstrap_line is None or bootstrap_line > platform_line:
            failures.append(
                f"{path.relative_to(SCRIPTS_DIR.parent)}: bootstrap={bootstrap_line}, platform={platform_line}"
            )
    assert not failures, "\n".join(failures)
