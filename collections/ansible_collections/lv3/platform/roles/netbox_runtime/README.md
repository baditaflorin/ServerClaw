# netbox_runtime

Deploy NetBox on the Docker runtime VM, keep its bootstrap credentials mirrored locally, and verify the private API with the managed superuser token.

Inputs: `netbox_compose_file`, `netbox_env_file`, `netbox_database_password_local_file`, `netbox_superuser_password_local_file`, `netbox_superuser_api_token_local_file`, `netbox_controller_url`.
