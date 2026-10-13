#!/usr/bin/env python3
"""Install the Scanopy daemon on guests that have none (one provisioned, bound key per daemon).

Usage:  SCANOPY_API_KEY=... [SCANOPY_URL=http://host:60072] [SCANOPY_SITE_ID=...] \
        scanopy_daemon_rollout.py --binary ./scanopy-daemon --targets targets.json [name ...]

targets.json maps the daemon name to its transport:
  {"vm-0mcp-200-0mcp-staging-runtime": {"kind": "ssh", "host": ["0mcp_staging_runtime"],
                                        "url": "http://10.10.10.1:60072", "sudo": true},
   "vm-0own-670-pdm":  {"kind": "ssh", "host": ["-J", "0own_bastion", "debian@10.60.10.70"], "url": "http://10.60.10.1:60072", "sudo": true},
   "ct-0docker-108-0docker-builder": {"kind": "pct", "ct": 108, "hyp": "0docker_bastion", "url": "http://10.10.10.1:60072"}}
`url` is the fleet relay the guest can reach (the hypervisor's gateway address). For each name it provisions the daemon
(POST /api/v1/daemons/provision, which mints a key bound 1:1 to the record), copies the binary, runs
`scanopy-daemon install --server-url ... --daemon-api-key ...` with the key passed through the environment, and re-installs cleanly if a
previous attempt left a config behind. The key is never printed. A guest must also be on the hypervisor's relay allowlist first (see
docs/runbooks/scanopy-service-discovery.md). Re-run is safe: a never-checked-in record with the same name is re-provisioned.
"""
import json, os, subprocess, sys, urllib.request, urllib.error, shlex

B = os.environ.get("SCANOPY_URL", "http://localhost:60072")
K = os.environ.get("SCANOPY_API_KEY", "")
SITE = os.environ.get("SCANOPY_SITE_ID", "")
BIN = ""

TARGETS = {}
SSHO = ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=15"]


def api(method, path, body=None):
    r = urllib.request.Request(B + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                               headers={"Authorization": "Bearer " + K, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=30) as x:
            return x.status, json.load(x)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]


def sh(cmd, stdin=None, timeout=300):
    p = subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout + p.stderr).strip()


def make_key(name):
    """Provision a daemon record + 1:1 bound key. Re-provisions (fresh key) when a never-checked-in record with this name exists."""
    s, r = api("GET", "/api/v1/daemons")
    existing = [d for d in (r["data"] if s == 200 else []) if d["name"] == name]
    body = {"name": name, "site_id": SITE, "mode": "daemon_poll"}
    if existing:
        body = {"daemon_id": existing[0]["id"]}
    s, r = api("POST", "/api/v1/daemons/provision", body)
    if s >= 300:
        raise SystemExit(f"provision failed for {name}: {s} {r}")
    d = r["data"]
    k = d.get("daemon_api_key")
    key = k.get("key") if isinstance(k, dict) else k
    if not key:
        raise SystemExit("no plaintext key in provision response (fields: %s)" % sorted(d.keys()))
    return key


REMOTE = r"""set -e
{sudo}mkdir -p /var/log/scanopy /etc/scanopy/daemon/scanopy-daemon
chmod 755 /tmp/scanopy-daemon
{sudo}systemctl disable --now scanopy-daemon 2>/dev/null || true
{sudo}rm -f /etc/scanopy/daemon/scanopy-daemon/config.json /etc/systemd/system/scanopy-daemon.service
{sudo}systemctl daemon-reload
export SCANOPY_DAEMON_API_KEY={key}
{sudoE}/tmp/scanopy-daemon install --server-url {url} --mode daemon_poll \
  --config-dir /etc/scanopy/daemon/scanopy-daemon --log-file /var/log/scanopy/scanopy-daemon.log --bin-dir /usr/local/bin 2>&1 | tail -4
rm -f /tmp/scanopy-daemon
sleep 8
echo "service: $({sudo}systemctl is-active scanopy-daemon)"
{sudo}journalctl -u scanopy-daemon --no-pager -n 6 -q | sed -E "s/^.*scanopy-daemon\[[0-9]+\]: //" | grep -E "Connected|Daemon ready|rejected|unreachable|ERROR" | tail -3
"""


def install(name, t):
    key = make_key(name)
    sudo = "sudo " if t.get("sudo") else ""
    sudoE = "sudo -E " if t.get("sudo") else ""
    script = REMOTE.format(sudo=sudo, sudoE=sudoE, url=t["url"], site=SITE, name=name, key=shlex.quote(key))
    if t["kind"] == "ssh":
        rc, out = sh(["scp", "-q", *SSHO, *( ["-J", t["host"][1]] if t["host"][0] == "-J" else []), BIN,
                      (t["host"][2] if t["host"][0] == "-J" else t["host"][0]) + ":/tmp/scanopy-daemon"])
        if rc: return f"scp failed: {out[:200]}"
        target = ["ssh", *SSHO, *t["host"], "bash -s"]
        rc, out = sh(target, stdin=script)
    else:
        hyp = t["hyp"]; ct = t["ct"]
        rc, out = sh(["scp", "-q", *SSHO, BIN, f"{hyp}:/tmp/scanopy-daemon"])
        if rc: return f"scp to hypervisor failed: {out[:200]}"
        rc, out = sh(["ssh", *SSHO, hyp, f"pct push {ct} /tmp/scanopy-daemon /tmp/scanopy-daemon && pct exec {ct} -- bash -s"],
                     stdin=script)
        sh(["ssh", *SSHO, hyp, "true"])
    return out[-700:]


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", required=True)
    ap.add_argument("--targets", required=True)
    ap.add_argument("names", nargs="*")
    a = ap.parse_args()
    BIN = os.path.abspath(a.binary)
    TARGETS = json.load(open(a.targets))
    if not SITE or not K:
        raise SystemExit("set SCANOPY_API_KEY and SCANOPY_SITE_ID")
    for n in (a.names or sorted(TARGETS)):
        print("=== " + n)
        print(install(n, TARGETS[n]))
