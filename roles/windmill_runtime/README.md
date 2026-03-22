# windmill_runtime

Deploy Windmill on the Docker runtime VM, mirror the bootstrap secret locally, seed repo-managed scripts, and verify end-to-end execution through the Windmill API.

Inputs: `windmill_workspace_id`, `windmill_workspace_name`, `windmill_compose_file`, `windmill_env_file`, `windmill_database_password_local_file`, `windmill_superadmin_secret_remote_file`, `windmill_superadmin_secret_local_file`, `windmill_seed_scripts`.
