"""Guards for the unattended LUKS unlock of the agent-history guest (ADR 0494, amendment 2026-11-12).

The passphrase is read from OpenBao by a boot unit with a dedicated unlock AppRole and piped into the owner's helper. These tests
render the real templates, run the real rendered fetcher against a fake OpenBao on the loopback address, and check that the unit
file uses systemd keys that exist (a wrong key was ignored on the guest and the stack started before the disk was unlocked).
No test uses a real secret: the passphrase below is a made-up value.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import jinja2
import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
ROLE = REPO / "collections" / "ansible_collections" / "lv3" / "platform" / "roles" / "agent_history_runtime"
HOST_VARS = REPO / "inventory" / "host_vars" / "agent-history.yml"

PASSPHRASE = "correct horse battery staple 0494"  # made up for the test
ROLE_ID = "test-role-id"
SECRET_ID = "test-secret-id"
KV_PATH = "kv/data/services/agent-history/luks"
KEY = "passphrase"


def _render(template: str, **overrides: object) -> str:
    env = jinja2.Environment(undefined=jinja2.StrictUndefined, keep_trailing_newline=True)
    env.globals["lookup"] = lambda *_args, **_kwargs: ""
    context = {
        "agent_history_data_mount": "/srv/agent-history",
        "agent_history_luks_name": "agent-history-data",
        "agent_history_helper_dir": "/usr/local/sbin",
        "agent_history_openbao_address": "http://127.0.0.1:1",
        "agent_history_luks_role_id_file": "/opt/agent-history/openbao/luks_role_id",
        "agent_history_luks_secret_id_file": "/opt/agent-history/openbao/luks_secret_id",
        "agent_history_openbao_luks_kv_path": KV_PATH,
        "agent_history_openbao_luks_key": KEY,
        "agent_history_luks_autounlock_http_timeout_seconds": 3,
        "agent_history_luks_autounlock_retry_seconds": 30,
        "agent_history_site_dir": "/opt/agent-history",
        "agent_history_compose_file": "/opt/agent-history/docker-compose.yml",
        "agent_history_run_dir": "/run/lv3-secrets/agent-history",
        "agent_history_data_device": "/dev/disk/by-id/scsi-0QEMU_QEMU_HARDDISK_drive-scsi1",
        "agent_history_pgdata_dir": "/srv/agent-history/postgres",
    }
    context.update(overrides)
    return env.from_string((ROLE / "templates" / template).read_text(encoding="utf-8")).render(**context)


# --- static guards ---------------------------------------------------------------------------------------------------------


def test_compose_unit_uses_a_condition_key_that_exists() -> None:
    unit = _render("agent-history.service.j2")
    # systemd has no ConditionPathIsMount: it was ignored with a warning and the unit ran at boot before the disk was unlocked.
    assert "ConditionPathIsMountPoint=/srv/agent-history" in unit
    assert "ConditionPathIsMount=" not in unit


def test_autounlock_unit_retries_and_is_not_ordered_with_the_compose_unit() -> None:
    unit = _render("agent-history-autounlock.service.j2")
    assert "Type=oneshot" in unit
    assert "Restart=on-failure" in unit
    assert "RestartSec=30" in unit
    assert "StartLimitIntervalSec=0" in unit  # never give up: OpenBao may come up late after a host reboot
    assert "ExecStart=/usr/local/sbin/agent-history-autounlock" in unit
    # the helper runs `systemctl start agent-history.service`; an ordering edge would make that call wait for this unit
    assert "agent-history.service" not in "\n".join(line for line in unit.splitlines() if line.startswith(("Before=", "After=", "Requires=", "Wants=")))
    assert "WantedBy=multi-user.target" in unit


@pytest.mark.parametrize("template", ["agent-history-autounlock.sh.j2", "agent-history-unlock.sh.j2"])
def test_shell_templates_are_valid_bash(template: str, tmp_path: Path) -> None:
    script = tmp_path / "script.sh"
    script.write_text(_render(template), encoding="utf-8")
    assert subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True).returncode == 0


def test_fetcher_template_is_valid_python() -> None:
    compile(_render("agent-history-luks-passphrase.py.j2"), "agent-history-luks-passphrase", "exec")


def test_autounlock_script_pipes_the_passphrase_and_never_prints_it() -> None:
    script = _render("agent-history-autounlock.sh.j2")
    assert '"$fetch" | "$unlock"' in script
    assert "set -euo pipefail" in script  # a failed fetch must fail the unit, so systemd retries
    for forbidden in ("echo \"$pass", "export ", "--key-file=/", "> /"):
        assert forbidden not in script


def test_fetcher_takes_no_secret_from_arguments_or_environment() -> None:
    source = _render("agent-history-luks-passphrase.py.j2")
    assert "sys.argv" not in source
    assert "os.environ" not in source
    assert "ProxyHandler({})" in source  # an environment proxy must never see the login or the value


def test_role_defaults_keep_it_off_and_host_vars_turn_it_on() -> None:
    defaults = yaml.safe_load((ROLE / "defaults" / "main.yml").read_text(encoding="utf-8"))
    assert defaults["agent_history_luks_autounlock_enabled"] is False
    assert defaults["agent_history_openbao_luks_key"] == KEY
    # the entry the owner created when the volume was formatted; the runtime AppRole's policy does not cover it
    assert defaults["agent_history_openbao_luks_kv_path"] == KV_PATH
    assert defaults["agent_history_openbao_luks_kv_path"] != defaults["agent_history_openbao_kv_path"]
    # the unlock has its own AppRole files, never the OpenBao Agent's
    assert defaults["agent_history_luks_role_id_file"] != defaults["agent_history_role_id_file"]
    assert defaults["agent_history_luks_secret_id_file"] != defaults["agent_history_secret_id_file"]
    host_vars = yaml.safe_load(HOST_VARS.read_text(encoding="utf-8"))
    assert host_vars["agent_history_luks_autounlock_enabled"] is True


def test_argument_specs_declare_every_new_variable() -> None:
    specs = yaml.safe_load((ROLE / "meta" / "argument_specs.yml").read_text(encoding="utf-8"))["argument_specs"]["main"]["options"]
    for name in (
        "agent_history_luks_autounlock_enabled",
        "agent_history_openbao_luks_kv_path",
        "agent_history_openbao_luks_key",
        "agent_history_luks_role_id_file",
        "agent_history_luks_secret_id_file",
        "agent_history_luks_autounlock_http_timeout_seconds",
        "agent_history_luks_autounlock_retry_seconds",
    ):
        assert name in specs


# --- the real fetcher against a fake OpenBao -------------------------------------------------------------------------------


class _FakeOpenBao(BaseHTTPRequestHandler):
    """Just enough of the OpenBao API: AppRole login, one KV read, token revoke. Records what it saw."""

    data: dict[str, str] = {KEY: PASSPHRASE}
    seen: list[str] = []

    def log_message(self, *_args: object) -> None:  # keep the test output quiet
        return

    def _send(self, status: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        type(self).seen.append("POST " + self.path)
        if self.path == "/v1/auth/approle/login":
            if body.get("role_id") == ROLE_ID and body.get("secret_id") == SECRET_ID:
                self._send(200, {"auth": {"client_token": "tok-1"}})
            else:
                self._send(403, {"errors": ["permission denied"]})
        elif self.path == "/v1/auth/token/revoke-self":
            self._send(204 if self.headers.get("X-Vault-Token") == "tok-1" else 403, {})
        else:
            self._send(404, {})

    def do_GET(self) -> None:  # noqa: N802
        type(self).seen.append("GET " + self.path)
        if self.path == "/v1/" + KV_PATH and self.headers.get("X-Vault-Token") == "tok-1":
            self._send(200, {"data": {"data": dict(type(self).data)}})
        else:
            self._send(403, {"errors": ["permission denied"]})


@pytest.fixture()
def fake_openbao():
    _FakeOpenBao.data = {KEY: PASSPHRASE}
    _FakeOpenBao.seen = []
    server = HTTPServer(("127.0.0.1", 0), _FakeOpenBao)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()


def _run_fetcher(tmp_path: Path, address: str, secret_id: str = SECRET_ID) -> subprocess.CompletedProcess:
    (tmp_path / "role_id").write_text(ROLE_ID + "\n", encoding="utf-8")
    (tmp_path / "secret_id").write_text(secret_id + "\n", encoding="utf-8")
    script = tmp_path / "fetch.py"
    script.write_text(
        _render(
            "agent-history-luks-passphrase.py.j2",
            agent_history_openbao_address=address,
            agent_history_luks_role_id_file=str(tmp_path / "role_id"),
            agent_history_luks_secret_id_file=str(tmp_path / "secret_id"),
        ),
        encoding="utf-8",
    )
    return subprocess.run([sys.executable, "-I", str(script)], capture_output=True, timeout=30)


def test_fetcher_prints_exactly_the_stored_value_and_revokes_its_token(fake_openbao, tmp_path: Path) -> None:
    result = _run_fetcher(tmp_path, f"http://127.0.0.1:{fake_openbao.server_port}")
    assert result.returncode == 0, result.stderr
    assert result.stdout == PASSPHRASE.encode()  # no trailing newline: cryptsetup would take it as part of the key
    assert PASSPHRASE.encode() not in result.stderr
    assert _FakeOpenBao.seen == ["POST /v1/auth/approle/login", "GET /v1/" + KV_PATH, "POST /v1/auth/token/revoke-self"]


def test_fetcher_fails_closed_on_a_rejected_login(fake_openbao, tmp_path: Path) -> None:
    result = _run_fetcher(tmp_path, f"http://127.0.0.1:{fake_openbao.server_port}", secret_id="wrong")
    assert result.returncode == 1
    assert result.stdout == b""
    assert b"HTTP 403" in result.stderr
    assert b"wrong" not in result.stderr


@pytest.mark.parametrize("data", [{}, {KEY: ""}, {KEY: 5}])
def test_fetcher_fails_closed_on_a_missing_or_empty_key(fake_openbao, tmp_path: Path, data: dict) -> None:
    _FakeOpenBao.data = data
    result = _run_fetcher(tmp_path, f"http://127.0.0.1:{fake_openbao.server_port}")
    assert result.returncode == 1
    assert result.stdout == b""
    assert b"missing or empty" in result.stderr


def test_fetcher_fails_closed_when_openbao_is_unreachable(tmp_path: Path) -> None:
    result = _run_fetcher(tmp_path, "http://127.0.0.1:1")  # nothing listens on port 1
    assert result.returncode == 1
    assert result.stdout == b""
    assert b"AppRole login" in result.stderr


# --- the operator's one-command unlock (scripts/agent-history-unlock-from-openbao.sh) ----------------------------------------

SCRIPTS = REPO / "scripts"
OPS_PASSWORD = "made-up-ops-password"  # made up for the test


class _FakeUserpassOpenBao(BaseHTTPRequestHandler):
    seen: list[str] = []

    def log_message(self, *_args: object) -> None:
        return

    def _send(self, status: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        type(self).seen.append("POST " + self.path)
        if self.path == "/v1/auth/userpass/login/ops":
            ok = body.get("password") == OPS_PASSWORD
            self._send(200 if ok else 400, {"auth": {"client_token": "tok-u"}} if ok else {"errors": ["invalid"]})
        elif self.path == "/v1/auth/token/revoke-self":
            self._send(204, {})
        else:
            self._send(404, {})

    def do_GET(self) -> None:  # noqa: N802
        type(self).seen.append("GET " + self.path)
        if self.path == "/v1/" + KV_PATH and self.headers.get("X-Vault-Token") == "tok-u":
            self._send(200, {"data": {"data": {KEY: PASSPHRASE}}})
        else:
            self._send(403, {})


@pytest.fixture()
def fake_userpass_openbao():
    _FakeUserpassOpenBao.seen = []
    server = HTTPServer(("127.0.0.1", 0), _FakeUserpassOpenBao)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()


def test_operator_unlock_script_is_valid_bash_and_the_reader_valid_python() -> None:
    assert subprocess.run(["bash", "-n", str(SCRIPTS / "agent-history-unlock-from-openbao.sh")], capture_output=True).returncode == 0
    compile((SCRIPTS / "agent-history-openbao-read.py").read_text(encoding="utf-8"), "reader", "exec")


def _fake_ssh(bin_dir: Path, sink: Path, argv_log: Path) -> None:
    """A stand-in for ssh: the OpenBao host runs the remote command locally; the guest host writes its standard input to `sink`."""
    shim = bin_dir / "ssh"
    shim.write_text(
        "#!/bin/bash\n"
        'host=""; cmd=""\n'
        'while [ $# -gt 0 ]; do case "$1" in -T) shift;; -o) shift 2;; *) if [ -z "$host" ]; then host="$1"; else cmd="$1"; fi; shift;; esac; done\n'
        f'printf "%s\\n" "$host $cmd" >> {argv_log}\n'
        f'if [ "$host" = "fake-openbao-host" ]; then exec bash -c "$cmd"; else cat > {sink}; fi\n',
        encoding="utf-8",
    )
    shim.chmod(0o755)


def _run_operator_script(tmp_path: Path, address: str, password: str) -> tuple[subprocess.CompletedProcess, Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    sink, argv_log = tmp_path / "guest-stdin", tmp_path / "argv.log"
    _fake_ssh(bin_dir, sink, argv_log)
    password_file = tmp_path / "ops-password.txt"
    password_file.write_text(password + "\n", encoding="utf-8")
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
        "HOME": str(tmp_path),
        "OPENBAO_SSH_HOST": "fake-openbao-host",
        "AGENT_HISTORY_SSH_HOST": "fake-guest-host",
        "OPENBAO_ADDRESS": address,
    }
    result = subprocess.run(
        ["bash", str(SCRIPTS / "agent-history-unlock-from-openbao.sh"), str(password_file)],
        capture_output=True,
        env=env,
        timeout=60,
    )
    return result, sink, argv_log


def test_operator_unlock_pipes_the_passphrase_to_the_guest_and_leaks_nothing(fake_userpass_openbao, tmp_path: Path) -> None:
    result, sink, argv_log = _run_operator_script(tmp_path, f"http://127.0.0.1:{fake_userpass_openbao.server_port}", OPS_PASSWORD)
    assert result.returncode == 0, result.stderr
    assert sink.read_bytes() == PASSPHRASE.encode()  # exactly the stored value, no trailing newline
    # neither the password nor the passphrase is in any command line, in the script's output or in its errors
    for secret in (OPS_PASSWORD.encode(), PASSPHRASE.encode()):
        assert secret not in argv_log.read_bytes()
        assert secret not in result.stdout
        assert secret not in result.stderr
    assert _FakeUserpassOpenBao.seen == ["POST /v1/auth/userpass/login/ops", "GET /v1/" + KV_PATH, "POST /v1/auth/token/revoke-self"]


def test_operator_unlock_fails_closed_on_a_wrong_password(fake_userpass_openbao, tmp_path: Path) -> None:
    result, sink, _ = _run_operator_script(tmp_path, f"http://127.0.0.1:{fake_userpass_openbao.server_port}", "wrong")
    assert result.returncode != 0  # pipefail: the unlock is reported as failed
    assert (not sink.exists()) or sink.read_bytes() == b""  # nothing that could be mistaken for a passphrase reached the guest
    assert b"HTTP 400" in result.stderr


# --- the one-time setup (scripts/agent-history-setup-unattended-unlock.sh) -------------------------------------------------

POLICY_PATH = "sys/policies/acl/0mcp-service-agent-history-luks"
ROLE_PATH = "auth/approle/role/agent-history-unlock"
ISSUED_ROLE_ID = "issued-role-id-0001"  # made up
ISSUED_SECRET_ID = "issued-secret-id-0002"  # made up


class _FakeAdminOpenBao(BaseHTTPRequestHandler):
    """userpass login, policy and AppRole writes, role_id, secret_id, and the AppRole login plus KV read the guest does afterwards."""

    seen: list[str] = []
    bodies: dict[str, dict] = {}

    def log_message(self, *_args: object) -> None:
        return

    def _send(self, status: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}")

    def _handle(self, method: str) -> None:
        body = self._body() if method in ("POST", "PUT") else {}
        path = self.path[len("/v1/"):]
        type(self).seen.append(method + " " + path)
        type(self).bodies[method + " " + path] = body
        token = self.headers.get("X-Vault-Token", "")
        if path == "auth/userpass/login/ops":
            ok = body.get("password") == OPS_PASSWORD
            self._send(200 if ok else 400, {"auth": {"client_token": "tok-a"}} if ok else {"errors": ["invalid"]})
        elif path == "auth/approle/login":
            ok = body.get("role_id") == ISSUED_ROLE_ID and body.get("secret_id") == ISSUED_SECRET_ID
            self._send(200 if ok else 403, {"auth": {"client_token": "tok-r"}} if ok else {})
        elif path == "kv/data/services/agent-history/luks" and method == "GET":
            self._send(200, {"data": {"data": {KEY: PASSPHRASE}}} if token == "tok-r" else {})
        elif token != "tok-a" and path != "auth/token/revoke-self":
            self._send(403, {})
        elif path == POLICY_PATH and method == "PUT":
            self._send(204, {})
        elif path == ROLE_PATH and method == "POST":
            self._send(204, {})
        elif path == ROLE_PATH + "/role-id":
            self._send(200, {"data": {"role_id": ISSUED_ROLE_ID}})
        elif path == ROLE_PATH + "/secret-id":
            self._send(200, {"data": {"secret_id": ISSUED_SECRET_ID}})
        elif path == "auth/token/revoke-self":
            self._send(204, {})
        else:
            self._send(404, {})

    def do_POST(self) -> None:  # noqa: N802
        self._handle("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._handle("PUT")

    def do_GET(self) -> None:  # noqa: N802
        self._handle("GET")


@pytest.fixture()
def fake_admin_openbao():
    _FakeAdminOpenBao.seen = []
    _FakeAdminOpenBao.bodies = {}
    server = HTTPServer(("127.0.0.1", 0), _FakeAdminOpenBao)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()


def _run_setup(tmp_path: Path, port: int, password: str) -> tuple[subprocess.CompletedProcess, Path, Path]:
    bin_dir, guest_dir = tmp_path / "bin", tmp_path / "guest-openbao"
    bin_dir.mkdir()
    guest_dir.mkdir()
    argv_log = tmp_path / "argv.log"
    # fake ssh: both hosts run the remote command locally; fake sudo: drop `-n` and run the rest
    (bin_dir / "ssh").write_text(
        "#!/bin/bash\n"
        'host=""; cmd=""\n'
        'while [ $# -gt 0 ]; do case "$1" in -T) shift;; -o) shift 2;; *) if [ -z "$host" ]; then host="$1"; else cmd="$1"; fi; shift;; esac; done\n'
        f'printf "%s\\n" "$host $cmd" >> {argv_log}\n'
        'exec bash -c "$cmd"\n',
        encoding="utf-8",
    )
    (bin_dir / "sudo").write_text('#!/bin/bash\n[ "$1" = "-n" ] && shift\nexec "$@"\n', encoding="utf-8")
    fetcher = tmp_path / "fetcher.py"
    fetcher.write_text(
        _render(
            "agent-history-luks-passphrase.py.j2",
            agent_history_openbao_address=f"http://127.0.0.1:{port}",
            agent_history_luks_role_id_file=str(guest_dir / "luks_role_id"),
            agent_history_luks_secret_id_file=str(guest_dir / "luks_secret_id"),
        ),
        encoding="utf-8",
    )
    fetcher_cmd = tmp_path / "fetch"
    fetcher_cmd.write_text(f'#!/bin/bash\nexec {sys.executable} -I {fetcher}\n', encoding="utf-8")
    for tool in (bin_dir / "ssh", bin_dir / "sudo", fetcher_cmd):
        tool.chmod(0o755)
    password_file = tmp_path / "ops-password.txt"
    password_file.write_text(password + "\n", encoding="utf-8")
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
        "HOME": str(tmp_path),
        "OPENBAO_SSH_HOST": "fake-openbao-host",
        "AGENT_HISTORY_SSH_HOST": "fake-guest-host",
        "OPENBAO_ADDRESS": f"http://127.0.0.1:{port}",
        "AGENT_HISTORY_OPENBAO_DIR": str(guest_dir),
        "AGENT_HISTORY_LUKS_FETCHER": str(fetcher_cmd),
    }
    result = subprocess.run(
        ["bash", str(SCRIPTS / "agent-history-setup-unattended-unlock.sh"), str(password_file)],
        capture_output=True,
        env=env,
        timeout=90,
    )
    return result, guest_dir, argv_log


def test_setup_scripts_are_valid() -> None:
    assert subprocess.run(["bash", "-n", str(SCRIPTS / "agent-history-setup-unattended-unlock.sh")], capture_output=True).returncode == 0
    for name in ("agent-history-openbao-admin.py", "agent-history-deliver-approle.py"):
        compile((SCRIPTS / name).read_text(encoding="utf-8"), name, "exec")


def test_setup_creates_policy_and_role_delivers_root_only_files_and_the_guest_can_fetch(fake_admin_openbao, tmp_path: Path) -> None:
    result, guest_dir, argv_log = _run_setup(tmp_path, fake_admin_openbao.server_port, OPS_PASSWORD)
    assert result.returncode == 0, result.stderr
    assert b"fetched" in result.stdout and b"bytes" in result.stdout
    # the policy reads exactly one path; the AppRole is short-lived with a reusable secret id
    policy = _FakeAdminOpenBao.bodies["PUT " + POLICY_PATH]["policy"]
    assert 'path "kv/data/services/agent-history/luks"' in policy and policy.count("path ") == 1 and '["read"]' in policy
    role = _FakeAdminOpenBao.bodies["POST " + ROLE_PATH]
    assert role["token_policies"] == ["0mcp-service-agent-history-luks"]
    assert role["token_ttl"] == "5m" and role["secret_id_num_uses"] == 0 and role["bind_secret_id"] is True
    # the two files hold exactly the issued login, readable by the owner only
    role_file, secret_file = guest_dir / "luks_role_id", guest_dir / "luks_secret_id"
    assert role_file.read_text() == ISSUED_ROLE_ID and secret_file.read_text() == ISSUED_SECRET_ID
    assert oct(role_file.stat().st_mode & 0o777) == "0o400" and oct(secret_file.stat().st_mode & 0o777) == "0o400"
    # no secret anywhere it should not be: command lines, output, errors
    for secret in (OPS_PASSWORD, ISSUED_SECRET_ID, PASSPHRASE):
        assert secret.encode() not in argv_log.read_bytes()
        assert secret.encode() not in result.stdout
        assert secret.encode() not in result.stderr
    # it touched nothing else in OpenBao
    mutating = [entry for entry in _FakeAdminOpenBao.seen if entry.split(" ", 1)[0] in ("PUT", "POST") and "login" not in entry and "revoke" not in entry]
    assert sorted(mutating) == sorted(["PUT " + POLICY_PATH, "POST " + ROLE_PATH, "POST " + ROLE_PATH + "/secret-id"])


def test_setup_fails_closed_on_a_wrong_password_and_writes_nothing(fake_admin_openbao, tmp_path: Path) -> None:
    result, guest_dir, _ = _run_setup(tmp_path, fake_admin_openbao.server_port, "wrong")
    assert result.returncode != 0
    assert not (guest_dir / "luks_role_id").exists() and not (guest_dir / "luks_secret_id").exists()
    assert b"HTTP 400" in result.stderr
    assert not any(entry.startswith(("PUT ", "POST auth/approle/role")) for entry in _FakeAdminOpenBao.seen)
