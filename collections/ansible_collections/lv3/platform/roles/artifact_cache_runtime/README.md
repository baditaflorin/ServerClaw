# artifact_cache_runtime

Deploys internal pull-through registry mirrors for the container registries the
platform reuses most often, seeds a repo-derived warm set, and leaves the
runtime ready for later migration onto a dedicated `artifact-cache-lv3` guest.
