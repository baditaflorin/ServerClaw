# netbox_sync

Synchronize the canonical repo inventory, topology, and governed service surfaces into the live NetBox API, then verify idempotency with a second pass.

Inputs: `netbox_controller_url`, `netbox_superuser_api_token_local_file`, `netbox_sync_script_path`, `netbox_sync_host_vars_path`, `netbox_sync_stack_path`, `netbox_sync_lane_catalog_path`.
