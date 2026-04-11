# portainer_runtime

Deploys Portainer on `docker-runtime` and persists the controller-local bootstrap auth used by the repo-managed Portainer wrapper.

Inputs: `portainer_image`, `portainer_compose_file`, `portainer_data_dir`, `portainer_admin_username`, `portainer_admin_password_local_file`, `portainer_admin_auth_local_file`, `portainer_controller_url`.
