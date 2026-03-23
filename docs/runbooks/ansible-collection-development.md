# Ansible Collection Development

## Purpose

ADR 0086 packages the repo-managed Ansible automation as the `lv3.platform` collection.

Canonical collection source now lives under `collections/ansible_collections/lv3/platform/`.
Repo-root `roles/`, `filter_plugins/`, and `callback_plugins/` remain compatibility symlinks for existing operator paths.

## Workflow

1. Edit roles or plugins through the collection path.
2. Keep root playbooks authoritative for controller execution.
3. Run `make collection-sync` after changing playbooks so the collection copy stays current.
4. Run `make collection-build` to create a distributable tarball.
5. Run `make collection-install` to test installation locally from the built tarball.
6. Run `make collection-publish` when a server token is available and the build should be published to `internal_galaxy`.

## Paths

- collection root: `collections/ansible_collections/lv3/platform/`
- collection tarballs: `build/collections/`
- compatibility role path: `roles/`
- compatibility filter plugin path: `filter_plugins/`
- compatibility callback plugin path: `callback_plugins/`

## Validation

- `make validate`
- `make collection-build`
- `make collection-install`
- `ansible-playbook -i inventory/hosts.yml playbooks/site.yml --syntax-check`

## Publishing

`config/windmill/scripts/collection-publish.py` builds the collection and publishes it through the `internal_galaxy` server configured in `ansible.cfg`.

Required environment:

- `ANSIBLE_GALAXY_SERVER_TOKEN`

Dry-run example:

```bash
python3 config/windmill/scripts/collection-publish.py --repo-root "$PWD" --dry-run
```
