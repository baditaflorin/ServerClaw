#!/bin/bash
# Idempotent installer for the Tier-0 runner on infer-tier0 (VM704). Run as root from this directory. Re-running updates the files and leaves keys and state alone.
# Keys are created only when missing and only on this VM; their PUBLIC halves are printed at the end for authorization (see README, "Authorize the keys").
set -euo pipefail
cd "$(dirname "$0")"
id t0runner >/dev/null 2>&1 || useradd --system --create-home --home-dir /var/lib/t0runner --shell /bin/bash t0runner
install -d -m 700 -o t0runner -g t0runner /var/lib/t0runner/.ssh
install -d -m 755 /opt/tier0-runner /opt/tier0-runner/bin /opt/tier0-runner/controller
install -d -m 750 -o root -g t0runner /etc/tier0-runner /etc/tier0-standby
install -d -m 755 /var/lib/tier0-controller
install -d -m 700 /var/lib/tier0-dns
command -v dig >/dev/null || DEBIAN_FRONTEND=noninteractive apt-get install -y -qq bind9-dnsutils >/dev/null

# 1) sealed standby key: second recipient of every encrypted tier-0 artifact; the private half never leaves this VM
if [ ! -f /etc/tier0-standby/standby.key ]; then
  openssl req -x509 -newkey rsa:4096 -nodes -keyout /etc/tier0-standby/standby.key -out /etc/tier0-standby/standby.crt -subj "/CN=tier0-standby-infer-tier0" -days 3650 2>/dev/null
fi
chgrp t0runner /etc/tier0-standby/standby.key; chmod 640 /etc/tier0-standby/standby.key; chmod 644 /etc/tier0-standby/standby.crt
# 2) runner ssh key + config (host keys must be pinned by hand: README)
[ -f /var/lib/t0runner/.ssh/id_ed25519 ] || runuser -u t0runner -- ssh-keygen -q -t ed25519 -N "" -C t0runner@infer-tier0 -f /var/lib/t0runner/.ssh/id_ed25519
[ -f /var/lib/t0runner/.ssh/id_ed25519_standby ] || runuser -u t0runner -- ssh-keygen -q -t ed25519 -N "" -C t0runner-standby@infer-tier0 -f /var/lib/t0runner/.ssh/id_ed25519_standby
[ -f /var/lib/t0runner/.ssh/config ] || { install -m 600 -o t0runner -g t0runner t0runner-ssh-config /var/lib/t0runner/.ssh/config; }
# an existing config predates the hypervisor Host block: insert it (before the catch-all) instead of replacing a file that holds this VM's pinned choices
grep -q '^Host infer_host_standby' /var/lib/t0runner/.ssh/config || python3 - <<'PY'
import re
src = open("t0runner-ssh-config").read()
block = src[src.index("# the hypervisor's standby controller"):src.index("Host *\n")]
p = "/var/lib/t0runner/.ssh/config"; cur = open(p).read()
i = cur.index("Host *\n")
open(p, "w").write(cur[:i] + block + cur[i:])
PY
# 3) read-only GitHub deploy key for fleet-state
[ -f /etc/tier0-runner/deploy_key ] || ssh-keygen -q -t ed25519 -N "" -C tier0-runner-deploy@infer-tier0 -f /etc/tier0-runner/deploy_key
chmod 600 /etc/tier0-runner/deploy_key; chmod 644 /etc/tier0-runner/deploy_key.pub
[ -f /etc/tier0-runner/known_hosts ] || echo "NOTE: put github.com's ssh-ed25519 host key into /etc/tier0-runner/known_hosts (README)" >&2

# 4) files
install -m 755 bin/tier0-run /usr/local/bin/tier0-run
for f in tier0-runner-sync tier0-rehearsal-daily tier0-rehearsal-metrics tier0-domainscope-rehearsal tier0-edge-compat tier0-vault-handback-rehearsal; do install -m 755 bin/$f /usr/local/sbin/$f; done
for f in tier0-secret tier0_secret.py tier0-dns tier0-dns-drill; do install -m 755 bin/$f /opt/tier0-runner/bin/$f; done
ln -sf /opt/tier0-runner/bin/tier0-dns /usr/local/sbin/tier0-dns; ln -sf /opt/tier0-runner/bin/tier0-dns-drill /usr/local/sbin/tier0-dns-drill
install -m 755 controller/tier0_controller.py /opt/tier0-runner/controller/tier0_controller.py
install -d -m 755 /opt/tier0-runner/executor /var/lib/tier0-executor /var/lib/tier0-sim /var/lib/tier0-runner /etc/tier0-executor
install -m 755 executor/tier0_executor.py executor/tier0_sim.py /opt/tier0-runner/executor/
install -m 644 gateway-extra.json /etc/tier0-runner/gateway-extra.json      # extra vhosts + upstream remap for the standby edge (DomainScope), see the file
[ -f /etc/tier0-executor/mode ] || echo shadow > /etc/tier0-executor/mode      # shadow until the promotion gate is met AND a person/agent switches it (README)
ln -sf /opt/tier0-runner/executor/tier0_executor.py /usr/local/sbin/tier0-executor
install -m 644 systemd/*.service systemd/*.timer /etc/systemd/system/
systemctl daemon-reload
if [ -f /etc/tier0-runner/known_hosts ] && [ ! -d /opt/tier0-runner/fleet-state/.git ]; then
  GIT_SSH_COMMAND="ssh -i /etc/tier0-runner/deploy_key -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/etc/tier0-runner/known_hosts -o BatchMode=yes" \
    git clone -q --depth 50 --filter=blob:none --no-checkout git@github.com:baditaflorin/fleet-state.git /opt/tier0-runner/fleet-state \
    && git -C /opt/tier0-runner/fleet-state sparse-checkout init --cone && git -C /opt/tier0-runner/fleet-state sparse-checkout set scripts/tier0 brownout dns docs/runbooks \
    && git -C /opt/tier0-runner/fleet-state checkout -q master || echo "NOTE: the deploy key is not authorized on the repo yet; re-run after authorizing it" >&2
fi
systemctl enable --now tier0-controller.timer tier0-runner-sync.timer tier0-rehearsal-daily.timer tier0-dns-drill.timer tier0-executor.timer tier0-sim-clean.timer tier0-sim-abort.timer tier0-domainscope-rehearsal.timer tier0-edge-compat.timer tier0-vault-handback-rehearsal.timer
echo "installed. Public keys to authorize (README, 'Authorize the keys'):"
echo "--- runner ssh key (t0jump on the bastion, ops/debian on the three VMs):"; cat /var/lib/t0runner/.ssh/id_ed25519.pub
echo "--- runner STANDBY key (root on the 0infer hypervisor, forced command standby-ctl-ssh; host/install-host.sh --runner-pubkey-file):"; cat /var/lib/t0runner/.ssh/id_ed25519_standby.pub
echo "--- GitHub read-only deploy key (fleet-state):"; cat /etc/tier0-runner/deploy_key.pub
echo "--- sealed standby certificate (add to TIER0_EXTRA_CERTS on the builder, /etc/tier0/tier0.env):"; openssl x509 -in /etc/tier0-standby/standby.crt -noout -fingerprint -sha256
