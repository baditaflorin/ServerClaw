# Initial Access Runbook

Preferred method: Hetzner Rescue System plus `installimage`.

## Current state

Access recovery succeeded on 2026-03-21.

Confirmed working login:

```bash
LOCAL_OVERLAY_ROOT="$(./scripts/resolve_local_overlay_root.sh)"
ssh -i "${LOCAL_OVERLAY_ROOT}/ssh/bootstrap.id_ed25519" -o IdentitiesOnly=yes root@203.0.113.1
```

Confirmed remote system:

```text
Linux proxmox-host 6.12.63+deb13-amd64
```

The remainder of this document is retained as recovery history and fallback procedure.

## Problem

Hetzner Robot explicitly states that the Debian 13 installation was activated but has not started yet:

> To start the installation, you have to reboot your server now.

Until that reboot happens, the server may still be running the previous OS state.

## Recommended path now

Stop using the current VNC installer path.

Use Hetzner Rescue System instead:

1. Activate Rescue System in Hetzner Robot.
2. Reboot/reset the server.
3. Log in to the rescue environment as `root` using the rescue password from Robot.
4. Inspect disks and current state.
5. Run `installimage`.
6. Explicitly choose `Debian 13 base`.
7. Reboot into the installed system.
8. Test SSH with the dedicated bootstrap key.

Rescue login:

```bash
ssh root@203.0.113.1
```

Notes:

- Hetzner rescue credentials and web console URLs are ephemeral operational secrets.
- Do not commit rescue passwords or rescue URLs into this repository.
- If Robot says rescue starts after the next reboot, trigger a hardware reset before testing access.
- If the console shows `No more network devices` followed by `Booting from Hard Disk...`, the machine did not enter the rescue environment and is falling back to the local disk boot path.

Install command inside rescue:

```bash
installimage
```

## Dedicated bootstrap key

A repo-local SSH keypair was generated for LLM-assisted bootstrap work:

- Private key: `.local/ssh/bootstrap.id_ed25519`
- Public key: `.local/ssh/bootstrap.id_ed25519.pub`
- Fingerprint: `SHA256:+wOwI8QKECFX9y2hlFMfBLP1m67PC0y9PYlO8+s0isQ`

Canonical shared-overlay aliases:

- Private key: `.local/ssh/bootstrap.id_ed25519`
- Public key: `.local/ssh/bootstrap.id_ed25519.pub`

If an older controller checkout still only has the legacy
`hetzner_llm_agents_ed25519` filenames, materialize the canonical aliases once:

```bash
python3 scripts/materialize_bootstrap_key_alias.py
```

Public key value:

```text
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOVJGGbg4OQjkLUMokPgKjl9LnBciBCgGHaWvTO3zxer llm-agents@proxmox-host_server
```

Preferred login test with that key:

```bash
LOCAL_OVERLAY_ROOT="$(./scripts/resolve_local_overlay_root.sh)"
ssh -i "${LOCAL_OVERLAY_ROOT}/ssh/bootstrap.id_ed25519" root@203.0.113.1
```

If your SSH agent is offering other keys first, force this key only:

```bash
LOCAL_OVERLAY_ROOT="$(./scripts/resolve_local_overlay_root.sh)"
ssh -i "${LOCAL_OVERLAY_ROOT}/ssh/bootstrap.id_ed25519" -o IdentitiesOnly=yes root@203.0.113.1
```

## Rejected path: VNC install

As of 2026-03-21, Hetzner VNC installation has been activated for the server and a reset request was sent.

VNC endpoint:

```text
203.0.113.1:1
```

This path is currently rejected for this host because it exposed the wrong OS installer.

Once the installer is available over VNC:

1. Confirm the selected OS is Debian 13.
2. Complete the install flow without introducing a password-only SSH setup.
3. Wait for the server to reboot into the installed system.
4. Test SSH using the dedicated bootstrap key first.

Preferred post-install test:

```bash
LOCAL_OVERLAY_ROOT="$(./scripts/resolve_local_overlay_root.sh)"
ssh -i "${LOCAL_OVERLAY_ROOT}/ssh/bootstrap.id_ed25519" -o IdentitiesOnly=yes root@203.0.113.1
```

If the VNC installer does not clearly apply the SSH public key, plan to use Rescue or console immediately after install to place the public key into `/root/.ssh/authorized_keys`.

Most recent reachability check after VNC activation:

- SSH on port 22: `Connection refused`
- VNC on port 5901: `open`

Inference: the machine is currently exposing the temporary VNC installer environment and has not yet reached an installed system with SSH available.

## Critical finding from VNC

The VNC installer currently shows AlmaLinux, not Debian 13.

This install must not be completed for this repository's target state.

Required corrective action:

1. Abort this install path.
2. Return to Hetzner Robot.
3. Activate Rescue System instead.
4. Use `installimage` from the rescue shell to select `Debian 13 base`.

Do not proceed until the rescue-driven install explicitly targets Debian 13.

## What we observed before the reboot

Before the confirmed reboot requirement was known, SSH public-key authentication was rejected for:

- `live@203.0.113.1`
- `debian@203.0.113.1`
- `root@203.0.113.1`

That result is consistent with the server still running the old state before the new install starts.

## What we observed after the hardware reset

After the hardware reset on 2026-03-21:

- The SSH host key changed, so the machine state definitely changed.
- `root` login with the expected ED25519 key is still rejected.
- `root` login with the dedicated bootstrap key is also still rejected and falls through to password authentication.
- The remote SSH banner reports `OpenSSH_9.2p1 Debian-2+deb12u7`.

Inference: the server is back online, but it does not currently present as the expected Debian 13 install with the injected key.

## What this implies

For Hetzner dedicated servers, the first reliable login path after a fresh OS install is normally `root`, using:

- The SSH public key injected during installation

## If root login still fails after the reinstall

Use the Hetzner Robot panel and recover access out of band:

1. Check the installation-complete email from Hetzner and verify which OS was actually provisioned.
2. If the host is not the expected Debian 13 image, reinstall from Robot and reboot again.
3. If the install completed and the key is still missing, boot into Rescue System or open the remote console/VNC from Robot.
4. From Rescue or console, either:
   - add the correct public key to `/root/.ssh/authorized_keys`, or
   - reinstall Debian 13 and make sure the ED25519 key is selected before the reboot

## Key that should be present

Expected local key fingerprint:

```text
SHA256:o7NyN1o8BKkFRIWOECEGp7+oNcb+3gBe0rpO0eSMelI
```

## Minimal repair once logged in

After logging in as `root`, make key-based access explicit before doing anything else:

```bash
install -d -m 700 /root/.ssh
printf '%s\n' 'ssh-ed25519 AAAA...replace-with-real-public-key... oct_2025_macbook_pro_14' >> /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
```

Then verify:

```bash
ssh -o PreferredAuthentications=publickey root@203.0.113.1
```

## Stop point

Do not start the Proxmox install until SSH access is stable and repeatable with a key-only login.
