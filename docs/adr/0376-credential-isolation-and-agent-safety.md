# ADR 0376: Credential Isolation and Agent Safety for .local/ Secrets

- Status: Accepted
- Implementation Status: Implemented
- Implemented On: 2026-04-06
- Date: 2026-04-06

## Context

On 2026-04-06 an agent session (AW-22/AW-23, Outline tools) accidentally
committed the `.local` directory entry to git as a self-referencing symlink.
The sequence was:

1. An agent worktree did not have a `.local` directory (worktrees share the
   git index but not untracked/gitignored files).
2. The agent created a symlink `.local -> /Users/.../proxmox_florin_server/.local`
   pointing to the main worktree's real directory so scripts could find
   credentials.
3. The agent ran `git add` and the symlink was committed — `.local/` appears
   in `.gitignore` but a symlink *file* named `.local` (without trailing slash)
   was not covered by that pattern.
4. When the commit was checked out in the main worktree, git replaced the
   **real `.local` directory** with the committed symlink, silently destroying
   ~150 credential files including the bootstrap SSH private key, all Keycloak
   client secrets, database passwords, and OpenBao unseal keys.
5. A subsequent agent session noticed `.local/` was missing and regenerated it
   with **fresh random secrets** that did not match the deployed production
   values, leaving all Ansible converge operations and SSH access broken.

### Impact

- SSH access to all VMs was lost (bootstrap key mismatch)
- No Ansible playbook could run (missing/wrong Keycloak secrets, DB passwords)
- OpenBao unseal keys were temporarily unrecoverable from the local workstation
- Recovery required reading deployed credentials back from VMs via
  `qm guest exec` through the QEMU Guest Agent on the Proxmox hypervisor

### Root cause

Three contributing factors:

1. **`.gitignore` blind spot**: `.local/` ignores only *directories*; a symlink
   *file* named `.local` passes the ignore check.
2. **Agent worktree isolation gap**: Agents operating in git worktrees do not
   inherit the main worktree's `.local/` directory. No guard prevented agents
   from creating symlinks or dummy files to fill the gap.
3. **No pre-commit guard**: The pre-commit hooks detect private keys and
   hardcoded secrets but do not check whether `.local` itself is being tracked.

## Decision

### 1. Gitignore hardening

Add an explicit entry for the `.local` symlink (without trailing slash) to
`.gitignore` so git never tracks it regardless of file type:

```gitignore
.local/
.local
```

### 2. Pre-commit guard

Add a check to the pre-commit hook (or a dedicated hook script) that rejects
any commit containing `.local` in the git index:

```bash
if git diff --cached --name-only | grep -q '^\.local$'; then
  echo "BLOCKED: .local must never be committed"
  exit 1
fi
```

### 3. Agent credential access contract

Agents operating in worktrees **must not**:
- Create symlinks to `.local/` or any credential directory
- Run `git add .local` or `git add -A` in a directory that contains `.local`
- Generate placeholder credentials that could overwrite real ones

Agents that need credentials should:
- Read them from the canonical path `$REPO_ROOT/.local/` where `$REPO_ROOT`
  is the main worktree (not the agent worktree)
- Or use the `--repo-root` flag available on most platform scripts to point
  at the main checkout
- Never write to `.local/` unless explicitly instructed by the operator

### 4. Recovery procedure documentation

The recovery script `scripts/recover_local_secrets.sh` is committed as a
runbook for future incidents. It uses `qm guest exec` via the Proxmox QEMU
Guest Agent to read deployed credentials from `/etc/lv3/` on each VM and
write them back to `.local/`.

Recovery prerequisites:
- SSH access to the Proxmox host (10.10.10.1) as root
- QEMU Guest Agent running on target VMs
- The Proxmox host itself uses a personal SSH key (not the bootstrap key),
  so hypervisor access survives bootstrap key loss

### 5. Bootstrap key rotation procedure

When the bootstrap SSH key is lost or compromised:

1. Generate a new key pair: `ssh-keygen -t ed25519 -f .local/ssh/bootstrap.id_ed25519 -C "bootstrap@proxmox_florin_server"`
2. Deploy the public key to all VMs via `qm guest exec`:
   ```bash
   for VMID in $(qm list | awk 'NR>1 && $3=="running" {print $1}'); do
     qm guest exec $VMID -- bash -c "
       mkdir -p /root/.ssh /home/ops/.ssh
       echo '<NEW_PUBKEY>' > /root/.ssh/authorized_keys
       echo '<NEW_PUBKEY>' > /home/ops/.ssh/authorized_keys
       chown -R ops:ops /home/ops/.ssh
       chmod 600 /root/.ssh/authorized_keys /home/ops/.ssh/authorized_keys"
   done
   ```
3. On hardened VMs with `TrustedUserCAKeys`, add an `AuthorizedKeysFile`
   directive in `/etc/ssh/sshd_config.d/` and reload sshd.
4. Test SSH access to each VM before removing old keys.

### 6. Security implications for server migration

When migrating to a new server or forking this repo:

- `.local/` must be provisioned separately — it is never in git
- The bootstrap key pair must be generated fresh and deployed to all VMs
  before any Ansible playbook can run
- Keycloak client secrets must be extracted from the Keycloak admin API or
  provisioned via the `scripts/provision_operator.py` bootstrap flow
- OpenBao unseal keys must be backed up to the control-plane recovery bundle
  on `backup-lv3` immediately after vault initialization
- Database passwords are managed by OpenBao secret rotation; the initial
  values come from the first Ansible converge

## Consequences

**Positive**
- `.gitignore` now blocks both the directory and any file/symlink named `.local`
- Pre-commit hook prevents accidental commits of `.local` to the index
- Recovery runbook reduces MTTR from "figure it out" to "run the script"
- Agent credential contract is documented and enforceable

**Negative / Trade-offs**
- Agents in worktrees cannot run Ansible playbooks without access to the main
  `.local/` — this is intentional (agents should not deploy to production
  without operator oversight)
- The recovery script depends on `qm guest exec` which requires the QEMU
  Guest Agent; VMs without it (e.g., staging) cannot be recovered this way

## Related ADRs

- ADR 0047: Short-lived credentials and mTLS
- ADR 0092: Unified Platform API Gateway (uses `.local/keycloak/` secrets)
- ADR 0102: Security hardening baseline
- ADR 0166: Control-plane recovery (backup bundle on `backup-lv3`)
