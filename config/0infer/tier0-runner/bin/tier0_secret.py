#!/usr/bin/env python3
"""Print ONE secret from the local vault standby (127.0.0.1) to stdout, nothing else. Root only (reads the standby's .env).
Issues a one-use 60 s key from the standby keystore, reads the secret, revokes the key. The value is never written to disk and never logged.
Usage: tier0_secret.py NAME  ->  value on stdout (no trailing newline)"""
import json, sys, urllib.error, urllib.parse, urllib.request

name = sys.argv[1]
env = dict(l.rstrip("\n").split("=", 1) for l in open("/opt/tier0/vault-standby/.env") if "=" in l)
KS, VAULT = "http://127.0.0.1:18021", "http://127.0.0.1:18140"


def http(m, u, h, b=None):
    r = urllib.request.Request(u, data=b, method=m, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=15) as x:
            return x.status, x.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


s, b = http("POST", KS + "/issue", {"X-Admin-Token": env["KEYSTORE_ADMIN_TOKEN"], "Content-Type": "application/json"},
            json.dumps({"user": "fleet-runner", "scope": "go-fleet-secrets", "tier": "infra-privileged", "ttl_seconds": 60, "use_limit": 1, "note": "tier0 runner: read one secret (one-use)"}).encode())
if s >= 300:
    sys.exit("keystore issue failed HTTP %d" % s)
d = json.loads(b)
key = d.get("data", d)["key"]
h = {"X-Admin-Token": env["SECRETS_ADMIN_TOKEN"], "X-Auth-Tier": "infra-privileged", "X-API-Key": key, "X-Auth-User": "fleet-runner"}
s, b = http("GET", VAULT + "/secrets/" + urllib.parse.quote(name, safe=""), h)
http("POST", KS + "/revoke", {"X-Admin-Token": env["KEYSTORE_ADMIN_TOKEN"], "Content-Type": "application/json"}, json.dumps({"key": key}).encode())
if s != 200:
    sys.exit("vault read failed HTTP %d" % s)
j = json.loads(b)
j = j.get("data", j)
v = j.get("value") if isinstance(j, dict) else None
if not v:
    sys.exit("secret has no value")
sys.stdout.write(v)
