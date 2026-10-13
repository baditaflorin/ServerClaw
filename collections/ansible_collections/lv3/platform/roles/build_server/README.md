# build_server

Configures `docker-build` as the repository-managed build cache host.

Managed surfaces:

- `apt-cacher-ng` on TCP `3142`
- a dedicated BuildKit daemon backed by `/opt/builds/.buildkit-cache`
- a systemd-managed BuildKit container whose name is distinct from the legacy daemon container name during guarded migrations
- stable host directories for Packer plugins and Ansible collections
- a persistent Docker named volume for pip downloads
- optional private registry host aliases, applied to both the host and BuildKit daemon
- By default, the platform registry hostname maps to the environment-specific private NGINX edge address; override `build_server_registry_hosts` only when the deployment uses a different registry route.

Inputs: `build_server_workspace`, `build_server_packer_plugin_cache`, `build_server_ansible_collection_cache`, `build_server_pip_cache_volume`, `build_server_buildkit_*`.
