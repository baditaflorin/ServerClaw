# Fleet-runner image-publisher identity

## Purpose

The dedicated Builder LXC108 needs one stable, non-secret local attestation so
the fleet runner can distinguish the approved image-publishing builder from
other build or runtime machines. The contract intentionally contains no
credential, registry endpoint, image reference, network address, or fallback
token.

## Controlled converge

Use an inventory that exposes the dedicated builder under the exact hostname
`0docker_builder`, then invoke the governed entrypoint:

```bash
ansible-playbook -i <dedicated-builder-inventory> playbooks/fleet-runner-image-publisher.yml
```

The playbook and role both reject any other inventory hostname. They write the
following exact JSON to `/etc/fleet-runner/image-publisher.json`:

```json
{"version":1,"identity":"builder-lxc-108"}
```

The parent directory is `root:root` mode `0700`; the contract file is
`root:root` mode `0600`. The role verifies that the parent is a real directory
and that the final file is a regular, root-owned file. It never reads a shell
environment variable, registry credential, or secret store.

## Verification

After a controlled converge, verify only non-sensitive metadata:

```bash
sudo stat -c '%U:%G %a %F' /etc/fleet-runner /etc/fleet-runner/image-publisher.json
sudo cmp -s /etc/fleet-runner/image-publisher.json <(printf '%s' '{"version":1,"identity":"builder-lxc-108"}')
```

The expected modes are `0700` for the directory and `0600` for the file. A
different host, symlink parent, symlink file, non-root ownership, or relaxed
mode is a failed converge and must be corrected through this playbook rather
than by an ad hoc host edit.

## Boundaries

This contract is an identity assertion, not authorization. The inventory
hostname `0docker_builder` selects the sole approved host; the contract payload
identity remains `builder-lxc-108`. Image allowlists,
immutable-digest policy, package access, registry authentication, and broker
mTLS continue to be enforced by their respective fleet-runner, cache, secret,
and broker contracts.
