# NGINX security remediation

## Fixed releases

The official NGINX advisory lists stable 1.30.7 and mainline 1.31.9 as fixed
for the November 2026 NGINX issues. Use the official package repository or
official container digests. Check the advisory before reusing this runbook
for a newer disclosure:

- [NGINX security advisories](https://nginx.org/en/security_advisories.html)
- [NGINX Linux packages](https://nginx.org/en/linux_packages.html)

## Inventory and containment

1. Read the active host and service inventory. Identify system NGINX packages,
   containers using an NGINX image, and application containers that bundle
   NGINX internally.
2. Record each current `nginx -v`, image digest, service owner, and backup path.
3. Before disabling SCTP, verify `CONFIG_IP_SCTP=m` (or that SCTP is disabled)
   and confirm `ss -H -A sctp` returns no sockets. Do not apply the module block
   to a host that requires SCTP.
4. On eligible hosts, install
   `/etc/modprobe.d/zz-nginx2root-disable-sctp.conf` with:

   ```text
   install sctp /bin/false
   blacklist sctp
   ```

   Unload the module when it is present and unused, then verify the modprobe
   rule, empty SCTP socket table, and unloaded module. Remove this temporary
   block only after the kernel fix is installed and SCTP requirements are
   reviewed.

## System package update

Use `playbooks/services/nginx2root-remediation.yml` through
`scripts/ansible_scope_runner.py` with the production inventory. The role pins
the official signing key fingerprints, selects stable 1.30.7 or mainline
1.31.9 based on the current branch, backs up `/etc/nginx`, installs the fixed
package and matching Perl module when required, and validates the final config
before its restart handler runs.

From the repository root, run once for each environment:

```sh
uv run --with pyyaml --with ansible-core python3 scripts/ansible_scope_runner.py run \
  --playbook playbooks/services/nginx2root-remediation.yml \
  --env production

uv run --with pyyaml --with ansible-core python3 scripts/ansible_scope_runner.py run \
  --playbook playbooks/services/nginx2root-remediation.yml \
  --env staging
```

After the apply, confirm:

- `nginx -v` is at least 1.30.7 on stable or at least 1.31.9 on mainline.
- `nginx -t` succeeds.
- `systemctl is-active nginx` reports active.
- Existing edge health checks and listeners still pass.

The package role supports Debian 12/13 and Ubuntu 24.04. The NGINX.org package
repository key must match one of the official fingerprints declared by the
role.

## Container update

For a service that owns its NGINX image, pin the Compose reference to a
verified fixed digest. Validate the rendered Compose config, recreate only the
affected service, then check its NGINX version, config, and health.

For application images that bundle NGINX:

1. Extract a fixed binary from a trusted package or image that is compatible
   with the container's libc and TLS libraries.
2. Test it in a disposable clone that uses the original container's config
   volumes and network. Require both `nginx -v` and `nginx -t` to succeed.
3. Copy the binary to a versioned host path and add it to the owning Compose
   service as a read-only mount at `/usr/sbin/nginx`. Back up the original
   Compose file before editing it.
4. Run `docker compose config --quiet`, recreate only the affected services,
   and verify the live binary, config, running state, and health checks.
5. Keep the prior Compose file, image digest, and binary available for rollback.

### Harbor exception

Harbor 2.15.0 shipped NGINX 1.26.3. The tested fixed executable was extracted
from the official package
`nginx_1.30.7-1~bookworm_amd64.deb` with SHA-256
`0e5325ab48a0995d09650132073920993b0b8949b7af51194240e33105755857`;
the executable SHA-256 is
`4a56e4d221295038a568e7dac10a70fd664844be0e9f004cdb69f72cd03a7fb8`.
The proxy and portal config tests passed in clones that shared each original
network. The live Compose services are named `proxy` and `portal`, even though
their container names are `nginx` and `harbor-portal`. Mount the binary
read-only into both services and retain the installer Compose backup. Harbor's
`prepare` command can regenerate that file, so reapply and verify the mounts
after any Harbor reconfiguration. Use Harbor's documented backup and upgrade
procedure for any full Harbor version change.

## Verification and rollback

For every affected runtime, record the old and new versions, image digest or
binary hash, config-test result, service status, health status, and backup
reference in a live-apply receipt. Do not rely on a successful package or
Compose operation alone.

If config validation or health fails, restore the saved config/Compose file or
previous image digest, recreate the affected service, and verify recovery.
Do not leave a failed or unverified NGINX process in service.

For Dify's separate zlib finding, follow its image-scan receipt and dated
exception; this NGINX runbook does not close that exception.
