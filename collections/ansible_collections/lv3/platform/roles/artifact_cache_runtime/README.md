# artifact_cache_runtime

Deploys internal pull-through registry mirrors for the container registries the
platform reuses most often, seeds a repo-derived warm set, and can also shut
down the old cache stack when a previous host is being retired during
consumer migration.
