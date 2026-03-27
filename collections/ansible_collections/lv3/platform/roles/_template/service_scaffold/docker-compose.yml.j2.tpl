services:
  openbao-agent:
    image: {{ @@VARIABLE_PREFIX@@_openbao_agent_image }}
    container_name: {{ @@VARIABLE_PREFIX@@_openbao_agent_container_name }}
    user: "0:0"
    environment:
      BAO_SKIP_DROP_ROOT: "true"
    command:
      - agent
      - -config=/openbao-agent/agent.hcl
    network_mode: host
    restart: unless-stopped
    healthcheck:
      test:
        - CMD-SHELL
        - test -s {{ @@VARIABLE_PREFIX@@_env_file }}
      interval: 10s
      timeout: 3s
      retries: 12
    volumes:
      - {{ @@VARIABLE_PREFIX@@_openbao_agent_dir }}:/openbao-agent:ro
      - {{ @@VARIABLE_PREFIX@@_env_file | dirname }}:{{ @@VARIABLE_PREFIX@@_env_file | dirname }}

  @@SERVICE_NAME@@:
    image: {{ @@VARIABLE_PREFIX@@_image }}
    container_name: {{ @@VARIABLE_PREFIX@@_container_name }}
    restart: unless-stopped
    depends_on:
      openbao-agent:
        condition: service_healthy
    env_file:
      - {{ @@VARIABLE_PREFIX@@_env_file }}
    ports:
      - "{{ ansible_host }}:{{ @@VARIABLE_PREFIX@@_internal_port }}:{{ @@VARIABLE_PREFIX@@_container_port }}"
      - "127.0.0.1:{{ @@VARIABLE_PREFIX@@_internal_port }}:{{ @@VARIABLE_PREFIX@@_container_port }}"
