# lv3.platform

`lv3.platform` is the canonical Ansible collection for this repository.

Collection source of truth lives under `collections/ansible_collections/lv3/platform/`.
Repo-root `roles/`, `filter_plugins/`, and `callback_plugins/` are compatibility symlinks so existing docs, tests, and operator paths keep working.

## Contents

- 54 migrated platform roles under `roles/`
- shared collection plugins under `plugins/filter/` and `plugins/callback/`
- repo playbooks mirrored under `playbooks/` for `ansible-galaxy collection build`

## Development

- `make collection-sync` mirrors the repo playbooks into the collection tree
- `make collection-build` creates `build/collections/lv3-platform-1.0.0.tar.gz`
- `make collection-install` installs the built tarball locally by default
- `make collection-publish` builds and publishes through the configured internal Galaxy server

See `docs/runbooks/ansible-collection-development.md` for the packaging workflow.
