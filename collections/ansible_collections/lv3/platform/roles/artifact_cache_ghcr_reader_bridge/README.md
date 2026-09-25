# artifact_cache_ghcr_reader_bridge

Dockerhost-only, forced-command bridge for one private GHCR proxy
configuration read. It issues one five-minute, one-use key for the sole
`artifact-cache-ghcr-config-renderer` identity and revokes it after the cache
renderer acknowledges the fixed read. It has no general read, list, issue, or
shell mode and never receives a proxy configuration value.

The paired SSH private key remains root-only deployment-local artifact-cache
state. This role accepts only its exact labelled public half and one pinned
artifact-cache source address.
