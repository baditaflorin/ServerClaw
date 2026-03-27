import json
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path


def _run_command(argv: list[str]) -> dict[str, object]:
    try:
        result = subprocess.run(
            argv,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        return {
            "argv": argv,
            "returncode": 127,
            "stdout": "",
            "stderr": str(exc),
        }

    return {
        "argv": argv,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def docker_volume_mountpoint(volume_name: str) -> Path | None:
    result = _run_command(["docker", "volume", "inspect", volume_name])
    if result["returncode"] != 0:
        return None
    payload = json.loads(str(result["stdout"]))
    mountpoint = payload[0].get("Mountpoint", "")
    return Path(mountpoint) if mountpoint else None


def path_size_mb(path: Path | None) -> int:
    if path is None or not path.exists():
        return 0
    total_bytes = 0
    for candidate in path.rglob("*"):
        if candidate.is_file():
            total_bytes += candidate.stat().st_size
    return total_bytes // (1024 * 1024)


def parse_apt_cacher_report(report: str) -> dict[str, object]:
    cache_size = None
    cache_limit = None
    size_match = re.search(r"Data in cache:\s*</span>\s*([^<]+)", report)
    limit_match = re.search(r"Max size:\s*</span>\s*([^<]+)", report)
    if size_match:
        cache_size = size_match.group(1).strip()
    if limit_match:
        cache_limit = limit_match.group(1).strip()
    return {
        "cache_size": cache_size,
        "cache_limit": cache_limit,
        "reachable": True,
    }


def fetch_apt_cacher_report(url: str) -> dict[str, object]:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        return {
            "reachable": False,
            "error": str(exc),
        }
    return parse_apt_cacher_report(body)


def main(
    pip_cache_volume: str = "pip-cache",
    pip_image: str = "python:3.12-slim",
    apt_cacher_report_url: str = "http://10.10.10.30:3142/acng-report.html",
):
    pip_cache_before = path_size_mb(docker_volume_mountpoint(pip_cache_volume))
    pip_purge = _run_command(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{pip_cache_volume}:/root/.cache/pip",
            pip_image,
            "pip",
            "cache",
            "purge",
        ]
    )
    pip_cache_after = path_size_mb(docker_volume_mountpoint(pip_cache_volume))
    apt_report = fetch_apt_cacher_report(apt_cacher_report_url)

    warnings: list[str] = []
    if pip_purge["returncode"] != 0:
        warnings.append("pip cache purge failed")
    if not apt_report.get("reachable", False):
        warnings.append("apt-cacher-ng report endpoint unreachable")

    return {
        "status": "ok" if not warnings else "warning",
        "pip_cache_volume": pip_cache_volume,
        "pip_cache_size_mb_before": pip_cache_before,
        "pip_cache_size_mb_after": pip_cache_after,
        "pip_cache_purge": pip_purge,
        "apt_cacher_report": apt_report,
        "warnings": warnings,
    }


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, sort_keys=True))
