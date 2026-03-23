---
@@VARIABLE_PREFIX@@_service_topology: "{{ hostvars['proxmox_florin'].lv3_service_topology | service_topology_get('@@SERVICE_ID@@') }}"
@@VARIABLE_PREFIX@@_site_dir: /opt/@@SERVICE_NAME@@
@@VARIABLE_PREFIX@@_secret_dir: /etc/lv3/@@SERVICE_NAME@@
@@VARIABLE_PREFIX@@_compose_file: "{{ @@VARIABLE_PREFIX@@_site_dir }}/docker-compose.yml"
@@VARIABLE_PREFIX@@_env_file: "{{ compose_runtime_secret_root }}/@@SERVICE_NAME@@/runtime.env"
@@VARIABLE_PREFIX@@_legacy_env_file: "{{ @@VARIABLE_PREFIX@@_site_dir }}/@@SERVICE_NAME@@.env"
@@VARIABLE_PREFIX@@_openbao_agent_dir: "{{ @@VARIABLE_PREFIX@@_site_dir }}/openbao"
@@VARIABLE_PREFIX@@_openbao_agent_image: "{{ openbao_agent_image }}"
@@VARIABLE_PREFIX@@_openbao_agent_container_name: @@SERVICE_NAME@@-openbao-agent
@@VARIABLE_PREFIX@@_openbao_secret_path: @@OPENBAO_SECRET_PATH@@
@@VARIABLE_PREFIX@@_openbao_policy_name: @@OPENBAO_POLICY_NAME@@
@@VARIABLE_PREFIX@@_openbao_approle_name: @@OPENBAO_APPROLE_NAME@@
@@VARIABLE_PREFIX@@_image: @@IMAGE_REF@@
@@VARIABLE_PREFIX@@_container_name: @@CONTAINER_NAME@@
@@VARIABLE_PREFIX@@_internal_port: @@PORT@@
@@VARIABLE_PREFIX@@_container_port: @@PORT@@
@@VARIABLE_PREFIX@@_healthcheck_path: /health
@@VARIABLE_PREFIX@@_bootstrap_admin_token_remote_file: "{{ @@VARIABLE_PREFIX@@_secret_dir }}/admin-token"
@@VARIABLE_PREFIX@@_local_artifact_dir: @@LOCAL_ARTIFACT_DIR@@
@@VARIABLE_PREFIX@@_bootstrap_admin_token_local_file: "{{ @@VARIABLE_PREFIX@@_local_artifact_dir }}/admin-token.txt"
@@VARIABLE_PREFIX@@_private_url: @@PRIVATE_URL@@
