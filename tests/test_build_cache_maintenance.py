import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "config" / "windmill" / "scripts" / "build-cache-maintenance.py"
SPEC = importlib.util.spec_from_file_location("build_cache_maintenance", SCRIPT_PATH)
build_cache_maintenance = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_cache_maintenance)


def test_parse_apt_cacher_report_extracts_size_fields() -> None:
    report = """
<span class=\"c0\">Data in cache:</span> 1.5 GiB
<span class=\"c0\">Max size:</span> 10 GiB
"""
    parsed = build_cache_maintenance.parse_apt_cacher_report(report)

    assert parsed["reachable"] is True
    assert parsed["cache_size"] == "1.5 GiB"
    assert parsed["cache_limit"] == "10 GiB"


def test_path_size_mb_returns_zero_for_missing_paths(tmp_path: Path) -> None:
    assert build_cache_maintenance.path_size_mb(tmp_path / "missing") == 0
