#!/usr/bin/env python3
"""Create the OpenBao policy and AppRole that unlock the agent-history data volume, and print a fresh login for it (ADR 0494).

Run ON the OpenBao guest (runtime-control) by scripts/agent-history-setup-unattended-unlock.sh. The administrator's userpass
password arrives on standard input (never an argument or an environment variable). It writes exactly two things in OpenBao and
nothing else:

  * the policy  <prefix>-service-agent-history-luks   : read on kv/data/services/agent-history/luks only
  * the AppRole agent-history-unlock                  : that policy, a 5 minute token, a reusable secret_id

and prints one JSON object {"role_id": ..., "secret_id": ...} to standard output for the delivery step to pipe into the guest. It
never prints a password or the passphrase (it does not read the passphrase at all). Progress goes to standard error, step names only.
Re-running is safe: the policy and the AppRole are overwritten with the same settings and a NEW secret_id is issued (the older ones
stay valid until revoked).

    python3 agent-history-openbao-admin.py [address] [admin_user] [policy_prefix] < password-file
"""

import json
import sys
import urllib.error
import urllib.request

DEFAULTS = ["http://127.0.0.1:8201", "ops", "0mcp"]
LUKS_PATH = "kv/data/services/agent-history/luks"
ROLE = "agent-history-unlock"
TIMEOUT_SECONDS = 15
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def say(message):
    sys.stderr.write("agent-history-openbao-admin: " + message + "\n")


def fail(step, detail=""):
    say(step + (": " + detail if detail else ""))
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
    address, user, prefix = (list(argv) + DEFAULTS[len(argv):])[:3]
    address = address.rstrip("/")
    password = sys.stdin.read().strip()
    if not password:
        fail("no password on standard input")

    login = call(address, "login as " + user, "POST", "auth/userpass/login/" + user, {"password": password})
    token = (login.get("auth") or {}).get("client_token", "")
    if not token:
        fail("login as " + user, "no token in the answer")
    say("logged in as " + user)

    policy_name = prefix + "-service-agent-history-luks"
    policy = 'path "' + LUKS_PATH + '" {\n  capabilities = ["read"]\n}\n'
    call(address, "write policy", "PUT", "sys/policies/acl/" + policy_name, {"policy": policy}, token)
    say("policy " + policy_name + " written (read on " + LUKS_PATH + " only)")

    call(
        address,
        "write AppRole",
        "POST",
        "auth/approle/role/" + ROLE,
        {
            "token_policies": [policy_name],
            "token_ttl": "5m",
            "token_max_ttl": "10m",
            "token_num_uses": 0,
            "secret_id_ttl": "0",
            "secret_id_num_uses": 0,
            "bind_secret_id": True,
        },
        token,
    )
    say("AppRole " + ROLE + " written")

    role_id = ((call(address, "read role_id", "GET", "auth/approle/role/" + ROLE + "/role-id", token=token)).get("data") or {}).get("role_id")
    secret_id = ((call(address, "issue secret_id", "POST", "auth/approle/role/" + ROLE + "/secret-id", {}, token)).get("data") or {}).get("secret_id")
    if not role_id or not secret_id:
        fail("AppRole login material", "role_id or secret_id missing in the answer")
    say("a new secret_id was issued (older ones stay valid until revoked)")

    try:
        call(address, "token revoke", "POST", "auth/token/revoke-self", token=token)
    except SystemExit:
        pass  # best effort: the token is short-lived

    sys.stdout.write(json.dumps({"role_id": role_id, "secret_id": secret_id}))
    sys.stdout.flush()


if __name__ == "__main__":
    main(sys.argv[1:])
