"""Tests for config/0mcp/docker-build-lv3: the host-local configuration of the CI build VM (VM 130), kept in git because the VM is no longer backed up.

The files must match their manifest, hold no secret, and every unit and script must be explained in the README (so a rebuild does not miss one).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

DIR = Path(__file__).resolve().parents[1] / "config" / "0mcp" / "docker-build-lv3"
FILES = DIR / "files"


def manifest() -> dict:
    out = {}
    for line in (DIR / "files.sha256").read_text().splitlines():
        digest, path = line.split(None, 1)
        out[path.strip()] = digest
    return out


def test_every_captured_file_is_in_the_manifest_with_the_right_checksum_and_nothing_else_is_listed():
    m = manifest()
    on_disk = {str(p.relative_to(FILES)) for p in FILES.rglob("*") if p.is_file()}
    assert on_disk == set(m), (sorted(on_disk - set(m)), sorted(set(m) - on_disk))
    for path, digest in m.items():
        assert hashlib.sha256((FILES / path).read_bytes()).hexdigest() == digest, path


def test_no_captured_file_holds_a_secret():
    """2026-10-22: the live /opt/gitea-runner/docker-compose.yml held the Gitea runner registration token as a literal (revoked and removed 2026-10-23); no copy may hold one."""
    pem = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
    gh = re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")
    jwt = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}")
    url = re.compile(r"[a-z]+://[^/\s:@]+:[^/\s@]{4,}@")
    assign = re.compile(r"(?i)(pass(?:word)?|secret|token|api[_-]?key|credential)[A-Za-z0-9_]*\s*[:=]\s*['\"]?([A-Za-z0-9+/=_.-]{20,})")
    for p in FILES.rglob("*"):
        if not p.is_file():
            continue
        for n, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
            for rx in (pem, gh, jwt, url):
                assert not rx.search(line), f"{p.relative_to(FILES)}:{n} looks like a secret"
            m = assign.search(line)
            if m:
                v = m.group(2)
                assert v.startswith("/") or v.startswith("${") or "/" in v[:6], f"{p.relative_to(FILES)}:{n} assigns a literal that looks like a secret"
    compose = (FILES / "opt" / "gitea-runner" / "docker-compose.yml").read_text()
    live = [l for l in compose.splitlines() if "GITEA_RUNNER_REGISTRATION_TOKEN" in l and not l.lstrip().startswith("#")]
    assert not live, "the runner is registered through its .runner file: no registration token belongs in the compose file, not even as a variable"


def test_the_readme_explains_every_unit_and_script_and_lists_what_is_not_in_git():
    readme = (DIR / "README.md").read_text()
    for p in sorted(FILES.rglob("*")):
        if p.is_file() and (p.suffix in (".service", ".timer") or "/usr/local/" in str(p)):
            stem = p.name.rsplit(".", 1)[0] if p.suffix in (".service", ".timer") else p.name
            stem = stem.replace("0mcp-", "").replace("0mpc-", "")  # the two platform names share one README row
            assert stem in readme or p.name in readme, f"{p.name} is not mentioned in the README"
    for needle in ("not backed up", "fleet-nightly-0mcp", "registration token", "agent-90.token", "Rebuild recipe", "verify-live.sh"):
        assert needle in readme, needle
    assert (DIR / "verify-live.sh").is_file() and "ssh -n" in (DIR / "verify-live.sh").read_text(), "ssh inside a read loop must be ssh -n or it eats the manifest"
