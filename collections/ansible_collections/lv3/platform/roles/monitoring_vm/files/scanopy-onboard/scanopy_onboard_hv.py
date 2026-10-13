#!/usr/bin/env python3
"""scanopy_onboard_hv - hypervisor side of the Scanopy onboarding job (runs as an SSH forced command on a Proxmox host).

Installed as /usr/local/sbin/scanopy-onboard-hv on every hypervisor and bound to one dedicated key in root's
authorized_keys:

    command="/usr/local/sbin/scanopy-onboard-hv",no-pty,no-port-forwarding,no-agent-forwarding,no-X11-forwarding,from="<monitoring egress>" ssh-ed25519 AAAA... scanopy-onboard

The key can therefore do exactly two things, and nothing else is reachable through it:

  list
      JSON of the running guests: kind (vm/ct), id, name, MAC addresses and the IPv4 addresses on real interfaces (Docker
      bridges and veth pairs left out), and whether the guest can be managed (CT: always; VM: its QEMU guest agent answers).
  install <vm|ct> <vmid> <server-url> <daemon-name> <version>      (the daemon API key is the first line on stdin)
      Downloads the scanopy-daemon release binary inside the guest, installs it as a systemd service in daemon_poll mode
      against <server-url> and reports `RESULT active=yes|no docker=yes|no`. It refuses a guest where a scanopy-daemon
      service is already active. VMs are reached through the guest agent (`qm guest exec`), containers through `pct exec`.

Arguments are validated against strict patterns; the API key only travels on stdin and is never logged or put in argv.
"""
import ipaddress
import json
import os
import re
import shlex
import subprocess
import sys

WRAPPER_VERSION = 1
URL_RE = re.compile(r"^http://(10\.\d{1,3}\.\d{1,3}\.\d{1,3}):60072$")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
VERSION_RE = re.compile(r"^(latest|\d{1,3}\.\d{1,3}\.\d{1,3})$")
KEY_RE = re.compile(r"^[A-Za-z0-9_.=+/-]{8,256}$")
SKIP_IFACE = re.compile(r"^(lo|docker\d*|br-.*|veth.*|virbr.*|cni.*|flannel.*|tailscale\d*)$")

GUEST_SCRIPT = r"""set -eu
KEY={key}
URL={url}
VER={version}
if systemctl is-active --quiet scanopy-daemon 2>/dev/null; then
  echo "RESULT skipped=already-active"; exit 0
fi
[ "$(uname -m)" = x86_64 ] || {{ echo "ERR unsupported architecture $(uname -m)"; exit 3; }}
command -v systemctl >/dev/null || {{ echo "ERR no systemd"; exit 3; }}
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
if [ "$VER" = latest ]; then
  asset=https://github.com/scanopy/scanopy/releases/latest/download/scanopy-daemon-linux-amd64
else
  asset=https://github.com/scanopy/scanopy/releases/download/v$VER/scanopy-daemon-linux-amd64
fi
if command -v curl >/dev/null; then curl -fsSL --max-time 240 -o "$tmp/scanopy-daemon" "$asset"
elif command -v wget >/dev/null; then wget -q -T 240 -O "$tmp/scanopy-daemon" "$asset"
elif command -v python3 >/dev/null; then
  python3 -c 'import sys,urllib.request;urllib.request.urlretrieve(sys.argv[1],sys.argv[2])' "$asset" "$tmp/scanopy-daemon"
else echo "ERR no curl, wget or python3 to download the daemon"; exit 4; fi
[ "$(wc -c < "$tmp/scanopy-daemon")" -gt 5000000 ] || {{ echo "ERR downloaded daemon is too small"; exit 5; }}
chmod 755 "$tmp/scanopy-daemon"
mkdir -p /var/log/scanopy /etc/scanopy/daemon/scanopy-daemon
rm -f /etc/scanopy/daemon/scanopy-daemon/config.json
SCANOPY_DAEMON_API_KEY="$KEY" "$tmp/scanopy-daemon" install --server-url "$URL" --mode daemon_poll \
  --config-dir /etc/scanopy/daemon/scanopy-daemon --log-file /var/log/scanopy/scanopy-daemon.log \
  --bin-dir /usr/local/bin >"$tmp/install.log" 2>&1 || {{ echo "ERR install failed: $(tail -3 "$tmp/install.log" | tr '\n' ' ')"; exit 6; }}
sleep 8
active=no; systemctl is-active --quiet scanopy-daemon && active=yes
docker=no; command -v docker >/dev/null && docker=yes
echo "RESULT active=$active docker=$docker"
[ "$active" = yes ] || {{ journalctl -u scanopy-daemon --no-pager -n 5 -q 2>/dev/null | tail -3; exit 7; }}
"""


def run(cmd, stdin=None, timeout=60):
    p = subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout, p.stderr


def conf_lines(kind, vmid):
    path = f"/etc/pve/{'qemu-server' if kind == 'vm' else 'lxc'}/{vmid}.conf"
    try:
        with open(path) as f:
            text = f.read()
    except OSError:
        return []
    return text.split("\n[")[0].splitlines()  # only the active section, not snapshots


def macs_of(lines):
    found = set()
    for line in lines:
        if re.match(r"^net\d+:", line):
            found.update(m.lower() for m in re.findall(r"(?:^|[=,\s])([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})", line))
    return sorted(found)


def usable(ip):
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return a.version == 4 and not (a.is_loopback or a.is_link_local)


def vm_ips(vmid):
    rc, out, _ = run(["qm", "agent", str(vmid), "network-get-interfaces"], timeout=15)
    if rc:
        return None
    ips = []
    for iface in json.loads(out):
        if SKIP_IFACE.match(iface.get("name", "")):
            continue
        ips += [a["ip-address"] for a in iface.get("ip-addresses", []) if a.get("ip-address-type") == "ipv4"]
    return sorted({i for i in ips if usable(i)})


def ct_ips(vmid):
    rc, out, _ = run(["pct", "exec", str(vmid), "--", "ip", "-4", "-o", "addr", "show"], timeout=15)
    if rc:
        return None
    ips = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 4 and not SKIP_IFACE.match(parts[1]):
            ips.append(parts[3].split("/")[0])
    return sorted({i for i in ips if usable(i)})


def cmd_list():
    guests = []
    _, out, _ = run(["qm", "list"])
    for line in out.splitlines()[1:]:
        cols = line.split()
        if len(cols) >= 3 and cols[2] == "running" and cols[0].isdigit():
            vmid, name = cols[0], cols[1]
            lines = conf_lines("vm", vmid)
            if any(re.match(r"^template:\s*1", ln) for ln in lines):
                continue
            ips = vm_ips(vmid)
            guests.append({"kind": "vm", "id": int(vmid), "name": name, "macs": macs_of(lines),
                           "ips": ips or [], "manageable": ips is not None})
    _, out, _ = run(["pct", "list"])
    for line in out.splitlines()[1:]:
        cols = line.split()
        if len(cols) >= 3 and cols[1] == "running" and cols[0].isdigit():
            vmid, name = cols[0], cols[-1]
            lines = conf_lines("ct", vmid)
            if any(re.match(r"^template:\s*1", ln) for ln in lines):
                continue
            ips = ct_ips(vmid)
            guests.append({"kind": "ct", "id": int(vmid), "name": name, "macs": macs_of(lines),
                           "ips": ips or [], "manageable": ips is not None})
    print(json.dumps({"wrapper_version": WRAPPER_VERSION, "hostname": os.uname().nodename, "guests": guests}))
    return 0


def cmd_install(args):
    if len(args) != 5:
        print("usage: install <vm|ct> <vmid> <server-url> <daemon-name> <version>", file=sys.stderr)
        return 2
    kind, vmid, url, name, version = args
    if kind not in ("vm", "ct") or not vmid.isdigit() or not URL_RE.match(url) or not NAME_RE.match(name) \
            or not VERSION_RE.match(version):
        print("refused: argument validation failed", file=sys.stderr)
        return 2
    key = sys.stdin.readline().strip()
    if not KEY_RE.match(key):
        print("refused: missing or malformed daemon API key on stdin", file=sys.stderr)
        return 2
    _, out, _ = run(["qm", "list"] if kind == "vm" else ["pct", "list"])
    running = any(ln.split()[:3][0] == vmid and "running" in ln.split() for ln in out.splitlines()[1:] if ln.split())
    if not running:
        print(f"refused: {kind} {vmid} is not a running guest on this host", file=sys.stderr)
        return 2
    script = GUEST_SCRIPT.format(key=shlex.quote(key), url=shlex.quote(url), version=shlex.quote(version))
    if kind == "ct":
        rc, out, err = run(["pct", "exec", vmid, "--", "bash", "-s"], stdin=script, timeout=420)
        sys.stdout.write(out[-2000:])
        sys.stderr.write(err[-500:])
        return rc
    rc, out, err = run(["qm", "guest", "exec", vmid, "--pass-stdin", "1", "--timeout", "400", "--", "bash", "-s"],
                       stdin=script, timeout=450)
    if rc:
        sys.stderr.write(err[-500:])
        return rc
    try:
        res = json.loads(out)
    except ValueError:
        print("ERR guest agent returned no JSON", file=sys.stderr)
        return 1
    sys.stdout.write((res.get("out-data") or "")[-2000:])
    sys.stderr.write((res.get("err-data") or "")[-500:])
    return int(res.get("exitcode", 1))


def main():
    argv = shlex.split(os.environ.get("SSH_ORIGINAL_COMMAND", "") or " ".join(sys.argv[1:]))
    if not argv:
        print("usage: list | install <vm|ct> <vmid> <server-url> <daemon-name> <version>", file=sys.stderr)
        return 2
    if argv[0] == "list" and len(argv) == 1:
        return cmd_list()
    if argv[0] == "install":
        return cmd_install(argv[1:])
    print("refused: unknown command", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
