#!/usr/bin/env python3
"""Write the unlock AppRole's two files on the agent-history guest from a JSON object on standard input (ADR 0494).

Run ON the guest as root by scripts/agent-history-setup-unattended-unlock.sh, with the output of agent-history-openbao-admin.py piped in.
Writes <dir>/luks_role_id and <dir>/luks_secret_id, owner root, mode 0400, atomically (a temporary file, then a rename). The values
are never printed, never in an argument or an environment variable. Prints "delivered" and nothing else on success.

    python3 agent-history-deliver-approle.py [dir]            (default dir: /opt/agent-history/openbao)
"""

import json
import os
import sys

DEFAULT_DIR = "/opt/agent-history/openbao"


def write_secret(path, value):
    temporary = path + ".tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o400)
    try:
        os.write(descriptor, value.encode("utf-8"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    if os.geteuid() == 0:
        os.chown(temporary, 0, 0)
    os.chmod(temporary, 0o400)
    os.replace(temporary, path)


def main(argv):
    target = argv[0] if argv else DEFAULT_DIR
    try:
        material = json.load(sys.stdin)
    except ValueError:
        sys.stderr.write("agent-history-deliver-approle: standard input is not JSON (the admin step failed?)\n")
        sys.exit(1)
    role_id, secret_id = material.get("role_id"), material.get("secret_id")
    if not isinstance(role_id, str) or not role_id or not isinstance(secret_id, str) or not secret_id:
        sys.stderr.write("agent-history-deliver-approle: role_id or secret_id missing\n")
        sys.exit(1)
    if not os.path.isdir(target):
        sys.stderr.write("agent-history-deliver-approle: no such directory: " + target + "\n")
        sys.exit(1)
    write_secret(os.path.join(target, "luks_role_id"), role_id)
    write_secret(os.path.join(target, "luks_secret_id"), secret_id)
    print("delivered")


if __name__ == "__main__":
    main(sys.argv[1:])
