"""Tests for scripts/woodpecker_activate_repo.sh, which activates a GitHub repository in a Woodpecker plane from the operator's Mac.

The script runs for real, in a sandbox, with shims first on PATH: `ssh` (runs the program the script sends to CT108 locally, with a fake fv.sh and a
fake `curl` standing in for the server) and `gh` (the GitHub repository id). No host is contacted and no real token exists: the fake vault entry holds a
marker string, and the tests assert that it never appears in the script's output, in any command line or in any log.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "woodpecker_activate_repo.sh"
TOKEN = "TOKEN-MARKER-5f1c9e"
HOOK = "HOOK-MARKER-77ab"

needs_tools = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("python3") is None, reason="needs bash and python3"
)

SSH_SHIM = """#!/usr/bin/env python3
import os, re, shlex, subprocess, sys
cmd = sys.argv[-1]
with open(os.environ["SANDBOX"] + "/ssh.args", "a") as f:
    f.write(" ".join(sys.argv[1:]) + "\\n")
m = re.match(r"pct exec 108 -- bash -s -- (.*)$", cmd, re.S)
assert m, cmd
args = shlex.split(m.group(1))
sys.exit(subprocess.run(["bash", "-s", "--", *args], stdin=sys.stdin).returncode)
"""

GH_SHIM = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$SANDBOX/gh.args"
[ "$1 $2 $3" = "api repos/baditaflorin/demo --jq" ] && { echo 123456; exit 0; }
exit 1
"""

FV_SHIM = f"""#!/bin/bash
[ "$1" = raw ] || exit 2
printf '%s\\n' "$2" >> "$SANDBOX/fv.entries"
printf '%s' '{TOKEN}'
"""

CURL_SHIM = f"""#!/usr/bin/env python3
import json, os, sys
sb = os.environ["SANDBOX"]
args = sys.argv[1:]
cfg = sys.stdin.read() if "-K" in args else ""
with open(sb + "/curl.args", "a") as f:
    f.write(" ".join(args) + " proxy=" + os.environ.get("https_proxy", "-") + "\\n")
assert "{TOKEN}" in cfg and "Authorization: Bearer" in cfg, "token not delivered on stdin"
method = args[args.index("-X") + 1]
url = args[-1]
path = url.split("://", 1)[1].split("/", 1)[1]
path = "/" + path
def send(code, body=""):
    sys.stdout.write(body + "\\n" + str(code))
    sys.exit(0)
def have(name): return os.path.exists(sb + "/" + name)
user = {{"login": "x", "avatar_url": "https://avatars.githubusercontent.com/u/1", "admin": True}}
if have("gitea"): user["avatar_url"] = "https://gitea.example.com/avatars/1"
repo = {{"id": 6, "full_name": "baditaflorin/demo", "forge_url": "https://github.com/baditaflorin/demo", "hook": "https://ci.example.com/api/hook?access_token={HOOK}"}}
if method == "GET" and path == "/api/user": send(200, json.dumps(user))
if method == "GET" and path == "/api/repos/lookup/baditaflorin/demo":
    send(200, json.dumps(repo)) if have("activated") else send(404, '{{"message":"not found"}}')
if method == "POST" and path == "/api/repos?forge_remote_id=123456":
    open(sb + "/activated", "w").close(); send(200, json.dumps(repo))
if method == "POST" and path == "/api/repos/6/pipelines":
    assert "-d" in args and json.loads(args[args.index("-d") + 1]) == {{"branch": "main"}}
    send(200, '{{"number": 4, "status": "pending"}}')
if method == "GET" and path == "/api/repos/6/pipelines/4":
    polls = sb + "/polls"; n = int(open(polls).read()) + 1 if have("polls") else 1
    open(polls, "w").write(str(n))
    if n < 2: send(200, '{{"number": 4, "status": "running"}}')
    st = "failure" if have("pipeline_fails") else "success"
    send(200, json.dumps({{"number": 4, "status": st, "workflows": [{{"name": "validate", "state": st, "children": [{{"name": "clone", "state": "success"}}, {{"name": "lint", "state": st}}]}}]}}))
send(404, "{{}}")
"""


@pytest.fixture()
def sandbox(tmp_path: Path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name, text in {"ssh": SSH_SHIM, "gh": GH_SHIM, "curl": CURL_SHIM}.items():
        (bindir / name).write_text(text)
        (bindir / name).chmod(0o755)
    (tmp_path / "fv.sh").write_text(FV_SHIM)
    return tmp_path


def run(sandbox: Path, *args: str, flags: tuple[str, ...] = ()):
    for flag in flags:
        (sandbox / flag).touch()
    env = {
        "PATH": f"{sandbox / 'bin'}:{os.environ['PATH']}",
        "HOME": str(sandbox),
        "SANDBOX": str(sandbox),
        "WOODPECKER_REMOTE_FV": str(sandbox / "fv.sh"),
        "WOODPECKER_POLL_SECONDS": "0",
        "WOODPECKER_RUN_TIMEOUT": "20",
    }
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, env=env, timeout=60)


def log(sandbox: Path, name: str) -> str:
    p = sandbox / name
    return p.read_text() if p.exists() else ""


def assert_no_secret(sandbox: Path, proc) -> None:
    everything = proc.stdout + proc.stderr + log(sandbox, "ssh.args") + log(sandbox, "curl.args") + log(sandbox, "gh.args")
    assert TOKEN not in everything
    assert HOOK not in everything
    assert "access_token" not in everything


@needs_tools
def test_already_activated_is_a_noop(sandbox):
    proc = run(sandbox, "ci.0mcp", "baditaflorin/demo", flags=("activated",))
    assert proc.returncode == 0, proc.stderr
    assert "forge=github admin=True" in proc.stdout
    assert "already activated" in proc.stdout
    assert "POST" not in log(sandbox, "curl.args")
    assert not (sandbox / "gh.args").exists()  # no need for the GitHub id
    assert_no_secret(sandbox, proc)


@needs_tools
def test_activation_posts_the_github_id_and_hides_the_response(sandbox):
    proc = run(sandbox, "ci.0mcp", "baditaflorin/demo")
    assert proc.returncode == 0, proc.stderr
    assert "activated baditaflorin/demo on ci.0mcp (Woodpecker repo id 6)" in proc.stdout
    curl = log(sandbox, "curl.args")
    assert "-X POST" in curl and "forge_remote_id=123456" in curl
    assert "repos/baditaflorin/demo --jq .id" in log(sandbox, "gh.args")
    assert (sandbox / "fv.entries").read_text().split() == ["woodpecker-ci-0mcp-api-token"] * 4  # user, lookup, activate, lookup
    assert "proxy=-" in curl  # ci.0mcp needs no proxy
    assert_no_secret(sandbox, proc)
    # a second run finds it activated and posts nothing more
    before = log(sandbox, "curl.args").count("-X POST")
    again = run(sandbox, "ci.0mcp", "baditaflorin/demo")
    assert again.returncode == 0 and "already activated" in again.stdout
    assert log(sandbox, "curl.args").count("-X POST") == before


@needs_tools
def test_ci_0exec_uses_its_vault_entry_and_the_proxy(sandbox):
    proc = run(sandbox, "ci.0exec", "baditaflorin/demo", flags=("activated",))
    assert proc.returncode == 0, proc.stderr
    assert set((sandbox / "fv.entries").read_text().split()) == {"woodpecker_ci_admin_pat_for_ci_0exec_com"}
    curl = log(sandbox, "curl.args")
    assert "https://ci.0exec.com/api/user" in curl
    assert all(line.endswith("proxy=http://127.0.0.1:1056") for line in curl.splitlines())
    assert_no_secret(sandbox, proc)


@needs_tools
def test_non_github_forge_is_refused_before_anything_else(sandbox):
    proc = run(sandbox, "ci.0mcp", "baditaflorin/demo", flags=("gitea",))
    assert proc.returncode == 1
    assert "forge=unknown" in proc.stdout and "refused" in proc.stderr
    curl = log(sandbox, "curl.args")
    assert curl.count("\n") == 1 and "/api/user" in curl  # nothing but the user call
    assert not (sandbox / "activated").exists() and not (sandbox / "gh.args").exists()
    assert_no_secret(sandbox, proc)


@needs_tools
def test_run_waits_and_prints_each_step(sandbox):
    proc = run(sandbox, "ci.0mcp", "baditaflorin/demo", "--run", "main", flags=("activated",))
    assert proc.returncode == 0, proc.stderr
    assert "pipeline #4 started on main" in proc.stdout
    assert "step clone: success" in proc.stdout and "step lint: success" in proc.stdout
    assert "pipeline #4: success" in proc.stdout
    assert (sandbox / "polls").read_text() == "2"  # one 'running' answer, then the final one
    assert_no_secret(sandbox, proc)


@needs_tools
def test_failed_pipeline_exits_nonzero(sandbox):
    proc = run(sandbox, "ci.0mcp", "baditaflorin/demo", "--run", "main", flags=("activated", "pipeline_fails"))
    assert proc.returncode == 1
    assert "step lint: failure" in proc.stdout and "pipeline #4: failure" in proc.stdout
    assert_no_secret(sandbox, proc)


@needs_tools
@pytest.mark.parametrize(
    "args",
    [
        (),
        ("ci.0mcp",),
        ("ci.example.com", "baditaflorin/demo"),
        ("ci.0mcp", "not-a-repo"),
        ("ci.0mcp", "a/b;rm -rf"),
        ("ci.0mcp", "baditaflorin/demo", "--run"),
        ("ci.0mcp", "baditaflorin/demo", "--run", "main; id"),
        ("ci.0mcp", "baditaflorin/demo", "--go", "main"),
    ],
)
def test_bad_usage_exits_2_without_calling_anything(sandbox, args):
    proc = run(sandbox, *args)
    assert proc.returncode == 2
    assert "Usage" in proc.stderr or "refused" in proc.stderr
    assert not (sandbox / "ssh.args").exists()


@needs_tools
def test_script_never_handles_the_token_itself():
    text = SCRIPT.read_text()
    assert "curl -K -" in text  # the token reaches curl on stdin only
    assert "Authorization" in text and text.count("Authorization") == 1
    assert "set -x" not in text and "xtrace" not in text
