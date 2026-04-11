#!/usr/bin/env python3

import argparse
import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
import urllib.parse
from pathlib import Path

from controller_automation_toolkit import load_json, write_json


def generate_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def load_or_create_secret(state_file: Path) -> str:
    if state_file.exists():
        data = load_json(state_file)
        return data["secret"]

    secret = generate_secret()
    write_json(state_file, {"secret": secret}, indent=2, mode=0o600)
    return secret


def totp_code(secret: str, period: int = 30, digits: int = 6) -> str:
    key = base64.b32decode(secret + "=" * ((8 - len(secret) % 8) % 8))
    counter = int(time.time() // period)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10**digits)).zfill(digits)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-file", required=True)
    parser.add_argument("--issuer", required=True)
    parser.add_argument("--account", required=True)
    args = parser.parse_args()

    state_file = Path(args.state_file)
    secret = load_or_create_secret(state_file)
    issuer = args.issuer
    account = args.account
    label = urllib.parse.quote(f"{issuer}:{account}")
    issuer_q = urllib.parse.quote(issuer)
    uri = f"otpauth://totp/{label}?secret={secret}&issuer={issuer_q}&algorithm=SHA1&digits=6&period=30"

    payload = {
        "secret": secret,
        "issuer": issuer,
        "account": account,
        "uri": uri,
        "code": totp_code(secret),
        "state_file": str(state_file),
    }
    write_json(
        state_file,
        {
            "secret": secret,
            "issuer": issuer,
            "account": account,
            "uri": uri,
        },
        indent=2,
        mode=0o600,
    )
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
