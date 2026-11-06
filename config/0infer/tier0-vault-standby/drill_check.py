# Runs on infer-tier0 against the standby on 127.0.0.1. Reads the standby's own .env (root) and prints only "records=N". One-use, 60 s key, revoked after.
import json, sys, urllib.request, urllib.error
env = dict(l.rstrip("\n").split("=", 1) for l in open("/opt/tier0/vault-standby/.env") if "=" in l)
KS, VAULT = "http://127.0.0.1:18021", "http://127.0.0.1:18140"
def http(m, u, h, b=None):
    r = urllib.request.Request(u, data=b, method=m, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=15) as x: return x.status, x.read()
    except urllib.error.HTTPError as e: return e.code, e.read()
s, b = http("POST", KS + "/issue", {"X-Admin-Token": env["KEYSTORE_ADMIN_TOKEN"], "Content-Type": "application/json"},
            json.dumps({"user": "fleet-runner", "scope": "go-fleet-secrets", "tier": "infra-privileged", "ttl_seconds": 60, "use_limit": 1, "note": "weekly standby drill (one-use)"}).encode())
if s >= 300: sys.exit("keystore issue failed HTTP %d" % s)
d = json.loads(b); key = d.get("data", d)["key"]
h = {"X-Admin-Token": env["SECRETS_ADMIN_TOKEN"], "X-Auth-Tier": "infra-privileged", "X-API-Key": key, "X-Auth-User": "fleet-runner", "Content-Type": "application/json"}
s, b = http("GET", VAULT + "/secrets", h)
if s != 200: sys.exit("vault list failed HTTP %d" % s)
j = json.loads(b); dd = j.get("data", j); dd = dd.get("secrets", dd) if isinstance(dd, dict) else dd
http("POST", KS + "/revoke", {"X-Admin-Token": env["KEYSTORE_ADMIN_TOKEN"], "Content-Type": "application/json"}, json.dumps({"key": key}).encode())
print("records=%d" % len(dd))
