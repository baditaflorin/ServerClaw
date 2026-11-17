#!/usr/bin/env python3
"""Read the agent-history LUKS passphrase from OpenBao and write it to standard output, with no trailing newline (ADR 0494).

Run ON the OpenBao guest (runtime-control) by scripts/agent-history-unlock-from-openbao.sh: it logs in as a userpass user (the
password arrives on standard input, never in an argument or an environment variable), reads one key of one KV v2 entry, revokes
its token and prints the value. Every message names the step and the HTTP status only, never a value. Exit 0 on success, 1 on any
failure with nothing on standard output.

    python3 agent-history-openbao-read.py [address] [user] [kv_path] [key] < password-file
"""

import json
import sys
import urllib.error
import urllib.request

DEFAULTS = ["http://127.0.0.1:8201", "ops", "kv/data/services/agent-history/luks", "passphrase"]
TIMEOUT_SECONDS = 10
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # no environment proxy may see the login


def fail(step, detail=""):
    sys.stderr.write("agent-history-openbao-read: " + step + (": " + detail if detail else "") + "\n")
    sys.exit(1)


def call(address, step, method, path, body=None, token=""):
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(address + "/v1/" + path, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("X-Vault-Token", token)
    try:
        with OPENER.open(request, timeout=TIMEOUT_SECONDS) as response:
            payload = response.read()
    except urllib.error.HTTPError as error:
        fail(step, "HTTP " + str(error.code))
    except (urllib.error.URLError, OSError) as error:
        fail(step, error.__class__.__name__)
    if not payload:
        return {}
    try:
        return json.loads(payload)
    except ValueError:
        fail(step, "the answer is not JSON")


def main(argv):
    address, user, kv_path, key = (list(argv) + DEFAULTS[len(argv):])[:4]
    address = address.rstrip("/")
    password = sys.stdin.read().strip()
    if not password:
        fail("no password on standard input")

    login = call(address, "login as " + user, "POST", "auth/userpass/login/" + user, {"password": password})
    token = (login.get("auth") or {}).get("client_token", "")
    if not token:
        fail("login as " + user, "no token in the answer")

    answer = call(address, "KV read", "GET", kv_path.strip("/"), token=token)
    value = ((answer.get("data") or {}).get("data") or {}).get(key)
    if not isinstance(value, str) or not value:
        fail("KV read", "the key " + key + " is missing or empty in " + kv_path)

    try:
        call(address, "token revoke", "POST", "auth/token/revoke-self", token=token)
    except SystemExit:
        pass  # best effort: the token is short-lived and the value is in hand

    sys.stdout.buffer.write(value.encode("utf-8"))
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main(sys.argv[1:])
