@@ENV_VAR_PREFIX@@_PORT={{ @@VARIABLE_PREFIX@@_container_port }}
@@ENV_VAR_PREFIX@@_ADMIN_TOKEN=[[ with secret "kv/data/{{ @@VARIABLE_PREFIX@@_openbao_secret_path }}" ]][[ .Data.data.@@ENV_VAR_PREFIX@@_ADMIN_TOKEN ]][[ end ]]
