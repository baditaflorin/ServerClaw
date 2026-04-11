# build_server

Configures `docker-build` as the repository-managed build cache host.

Managed surfaces:

- `apt-cacher-ng` on TCP `3142`
- a dedicated BuildKit daemon backed by `/opt/builds/.buildkit-cache`
- stable host directories for Packer plugins and Ansible collections
- a persistent Docker named volume for pip downloads

Inputs: `build_server_workspace`, `build_server_packer_plugin_cache`, `build_server_ansible_collection_cache`, `build_server_pip_cache_volume`, `build_server_buildkit_*`.
