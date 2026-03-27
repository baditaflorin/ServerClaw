---
argument_specs:
  main:
    short_description: Converge the @@DISPLAY_NAME@@ runtime scaffold.
    options:
      @@VARIABLE_PREFIX@@_service_topology:
        type: dict
        required: true
        description:
          - Service topology entry for the scaffolded runtime.
      @@VARIABLE_PREFIX@@_site_dir:
        type: path
        required: true
        description:
          - Base directory for the @@DISPLAY_NAME@@ compose stack.
      @@VARIABLE_PREFIX@@_secret_dir:
        type: path
        required: true
        description:
          - Guest-local directory that stores bootstrap secret material.
      @@VARIABLE_PREFIX@@_compose_file:
        type: path
        required: true
        description:
          - Compose file path for the scaffolded runtime.
      @@VARIABLE_PREFIX@@_env_file:
        type: path
        required: true
        description:
          - Runtime env file rendered for the application container.
      @@VARIABLE_PREFIX@@_image:
        type: str
        required: true
        description:
          - Container image reference for the scaffolded application.
      @@VARIABLE_PREFIX@@_container_name:
        type: str
        required: true
        description:
          - Docker container name for the scaffolded application.
      @@VARIABLE_PREFIX@@_internal_port:
        type: int
        required: true
        description:
          - Host port exposed by the scaffolded runtime.
      @@VARIABLE_PREFIX@@_container_port:
        type: int
        required: true
        description:
          - Container port exposed by the application image.
      @@VARIABLE_PREFIX@@_healthcheck_path:
        type: str
        required: true
        description:
          - HTTP path used by the local verify contract.
      @@VARIABLE_PREFIX@@_bootstrap_admin_token_remote_file:
        type: path
        required: true
        description:
          - Guest-local file that stores the generated bootstrap admin token.
      @@VARIABLE_PREFIX@@_local_artifact_dir:
        type: path
        required: true
        description:
          - Controller-local directory that mirrors the bootstrap admin token.
      @@VARIABLE_PREFIX@@_bootstrap_admin_token_local_file:
        type: path
        required: true
        description:
          - Controller-local mirror path for the bootstrap admin token.
