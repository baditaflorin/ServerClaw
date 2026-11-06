#!/bin/bash
# Idempotent installer for the hypervisor-side part of the DomainScope standby on the 0infer host (pve01-0infer). Run as root ON the host from this directory:
#   tar -C config/0infer/tier0-runner/host -cf - . | ssh 0infer_bastion 'd=$(mktemp -d) && tar -C $d -xf - && bash $d/install-host.sh [--runner-pubkey-file F]; rm -rf $d'
# (--runner-pubkey-file: the public half of the runner's standby key; it is then added to root's authorized_keys as a FORCED-COMMAND line that can run only standby-ctl-ssh.)
# Order for every file: validate first, back up what it changes, apply, verify, undo on failure.
set -euo pipefail
cd "$(dirname "$0")"
TS=$(date -u +%Y%m%dT%H%M%SZ)
RUNNER_PUBKEY_FILE=
while [ $# -gt 0 ]; do case "$1" in --runner-pubkey-file) RUNNER_PUBKEY_FILE=$2; shift ;; *) echo "unknown option $1" >&2; exit 2 ;; esac; shift; done
NFT_FILE=/etc/nftables/infer-domainscope-standby.nft; NFT_TABLE=infer_ds_standby_nat; MAIN=/etc/nftables.conf

# 1) nft: the DNAT from the standby edge to VM 8101
nft -c -f infer-domainscope-standby.nft                                   # syntax + semantic check, applies nothing
install -m 644 infer-domainscope-standby.nft "$NFT_FILE"
if ! grep -qF "include \"$NFT_FILE\"" "$MAIN"; then
  cp -a "$MAIN" "$MAIN.bak-ds-standby-$TS"
  printf 'include "%s"\n' "$NFT_FILE" >> "$MAIN"
fi
# load ONLY this table (never the whole ruleset: the other tables hold live NAT/filter state of the VMs)
nft delete table ip "$NFT_TABLE" 2>/dev/null || true
if ! nft -f "$NFT_FILE"; then
  echo "nft load failed: undoing" >&2
  [ -f "$MAIN.bak-ds-standby-$TS" ] && cp -a "$MAIN.bak-ds-standby-$TS" "$MAIN"
  rm -f "$NFT_FILE"; exit 1
fi
nft list table ip "$NFT_TABLE" | grep -q "dnat to 10.70.10.50" || { echo "rule not present after load" >&2; exit 1; }
nft -c -f "$MAIN" >/dev/null || { echo "WARNING: $MAIN no longer validates as a whole; backup $MAIN.bak-ds-standby-$TS" >&2; exit 1; }
echo "nft: $NFT_TABLE loaded and persisted ($NFT_FILE, include in $MAIN)"

# 2) standby-ctl: the controller of VM 8101, its forced-command wrapper, its config, the pinned public database certificate
python3 -m py_compile standby_ctl.py && rm -rf __pycache__
bash -n standby-ctl-ssh
python3 -c "import json; json.load(open('standby-ctl.json'))"
# VM701's server certificate (self-signed, public) is put into the standby's data volume by the controller before its database probe. It is verified here against the sha256 recorded in the
# config before it is installed, and a file that holds a private key is refused.
pin=$(python3 -c "import json; print(json.load(open('standby-ctl.json'))['pg_cert']['sha256'])")
[ "$(sha256sum pg-tls/infer-pg-primary.crt | cut -d' ' -f1)" = "$pin" ] || { echo "pg-tls/infer-pg-primary.crt does not match the sha256 pinned in standby-ctl.json: not installing" >&2; exit 1; }
! grep -q "PRIVATE KEY" pg-tls/infer-pg-primary.crt || { echo "refusing: a private key in the certificate file" >&2; exit 1; }
install -d -m 750 /var/log/standby-ctl /var/lib/standby-ctl /var/lib/standby-ctl/backups
for f in /usr/local/sbin/standby-ctl /usr/local/sbin/standby-ctl-ssh /etc/standby-ctl/config.json; do          # what is replaced is kept (the newest five of each), outside every directory that is loaded
  [ -f "$f" ] && cp -a "$f" "/var/lib/standby-ctl/backups/$(basename "$f").bak-$TS"
  ls -1t /var/lib/standby-ctl/backups/"$(basename "$f")".bak-* 2>/dev/null | tail -n +6 | xargs -r rm -f || true
done
install -d -m 755 /etc/standby-ctl /etc/standby-ctl/pg-tls
install -m 644 pg-tls/infer-pg-primary.crt /etc/standby-ctl/pg-tls/infer-pg-primary.crt
install -m 755 standby_ctl.py /usr/local/sbin/standby-ctl
install -m 755 standby-ctl-ssh /usr/local/sbin/standby-ctl-ssh
install -m 644 standby-ctl.json /etc/standby-ctl/config.json
status=$(/usr/local/sbin/standby-ctl status) || { echo "standby-ctl status failed" >&2; exit 1; }
echo "$status" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["ok"] and d["vm"] in ("stopped","running"), d; print("standby-ctl: status ok, vm", d["vm"], "link", d.get("link"))'
chk=$(/usr/local/sbin/standby-ctl check) || { echo "standby-ctl check failed (the previous controller and config are in /var/lib/standby-ctl/backups/*.bak-$TS)" >&2; echo "$chk" >&2; exit 1; }
echo "$chk" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["ok"], d; print("standby-ctl: check ok:", "; ".join(s["step"] + " " + ("ok" if s["ok"] else "FAIL") for s in d["steps"]))'

# 3) the runner's key: a forced command that can run exactly the standby-ctl verbs, only from the runner VM's address
if [ -n "$RUNNER_PUBKEY_FILE" ]; then
  pub=$(head -1 "$RUNNER_PUBKEY_FILE")
  echo "$pub" | grep -Eq '^ssh-ed25519 [A-Za-z0-9+/=]{40,} ?[^ ]*$' || { echo "not an ssh-ed25519 public key: $RUNNER_PUBKEY_FILE" >&2; exit 2; }
  blob=$(echo "$pub" | awk '{print $2}')
  AK=/root/.ssh/authorized_keys
  if grep -qF "$blob" "$AK"; then
    echo "authorized_keys: the runner key is already present: leaving it alone"
  else
    cp -a "$AK" "$AK.bak-standby-ctl-$TS"
    printf 'restrict,from="10.70.10.40",command="/usr/local/sbin/standby-ctl-ssh" ssh-ed25519 %s t0runner-standby@infer-tier0\n' "$blob" >> "$AK"
    echo "authorized_keys: runner key added (forced command, from 10.70.10.40 only); backup $AK.bak-standby-ctl-$TS"
  fi
fi
