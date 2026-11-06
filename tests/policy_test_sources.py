"""Keep portable fake-world tests independent of the excluded deployment policy.

Existing private inputs are read byte-for-byte. Only the two intentionally
excluded policy files have synthetic substitutes; other missing files fail.
"""
import shutil
from pathlib import Path

from standby_edge_grants_job import DESTINATIONS, EDGE_SRC


_RUNTIME_ROLES = dict(DESTINATIONS)


def source_bytes(root: Path, relative: str) -> bytes:
    path = root / relative
    if path.exists():
        return path.read_bytes()
    fixtures = root / "tests" / "fixtures" / "tailscale"
    if relative == "config/tailscale/policy.hujson":
        text = (fixtures / "standby-job-policy.hujson").read_text()
        runtime = next(ip for ip, alias in _RUNTIME_ROLES.items() if alias == "lv3-docker-runtime")
        return text.replace("192.0.2.10", EDGE_SRC.removesuffix("/32")).replace("192.0.2.11", runtime).encode()
    if relative == "config/tailscale/lockout-guard.json" and not (root / "config/tailscale/policy.hujson").exists():
        return (fixtures / "lockout-guard.json").read_bytes()
    return path.read_bytes()


def copy_source(root: Path, relative: str, destination: Path) -> None:
    path = root / relative
    if path.exists():
        shutil.copy(path, destination)
    else:
        destination.write_bytes(source_bytes(root, relative))
