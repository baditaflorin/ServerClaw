---
- name: Validate @@DISPLAY_NAME@@ runtime scaffold inputs
  ansible.builtin.assert:
    that:
      - @@VARIABLE_PREFIX@@_site_dir | length > 0
      - @@VARIABLE_PREFIX@@_secret_dir | length > 0
      - @@VARIABLE_PREFIX@@_compose_file | length > 0
      - @@VARIABLE_PREFIX@@_env_file | length > 0
      - @@VARIABLE_PREFIX@@_image | length > 0
      - @@VARIABLE_PREFIX@@_container_name | length > 0
      - @@VARIABLE_PREFIX@@_internal_port | int > 0
      - @@VARIABLE_PREFIX@@_container_port | int > 0
      - @@VARIABLE_PREFIX@@_bootstrap_admin_token_remote_file | length > 0
      - @@VARIABLE_PREFIX@@_bootstrap_admin_token_local_file | length > 0
    fail_msg: "@@ROLE_NAME@@ requires runtime paths, port metadata, and bootstrap token paths."

- name: Ensure @@DISPLAY_NAME@@ runtime packages are present
  ansible.builtin.apt:
    name:
      - openssl
    state: present
    update_cache: true
    force_apt_get: true

- name: Ensure the @@DISPLAY_NAME@@ runtime directories exist
  ansible.builtin.file:
    path: "{{ item.path }}"
    state: directory
    owner: root
    group: root
    mode: "{{ item.mode }}"
  loop:
    - path: "{{ @@VARIABLE_PREFIX@@_site_dir }}"
      mode: "0755"
    - path: "{{ @@VARIABLE_PREFIX@@_secret_dir }}"
      mode: "0700"

- name: Generate the @@DISPLAY_NAME@@ bootstrap admin token
  ansible.builtin.shell: |
    set -euo pipefail
    if [ ! -s "{{ @@VARIABLE_PREFIX@@_bootstrap_admin_token_remote_file }}" ]; then
      umask 077
      openssl rand -hex 32 > "{{ @@VARIABLE_PREFIX@@_bootstrap_admin_token_remote_file }}"
      echo changed
    fi
  args:
    executable: /bin/bash
  register: @@VARIABLE_PREFIX@@_token_generation
  changed_when: "'changed' in @@VARIABLE_PREFIX@@_token_generation.stdout"
  no_log: true

- name: Read the @@DISPLAY_NAME@@ bootstrap admin token
  ansible.builtin.slurp:
    src: "{{ @@VARIABLE_PREFIX@@_bootstrap_admin_token_remote_file }}"
  register: @@VARIABLE_PREFIX@@_token_raw
  no_log: true

- name: Record the @@DISPLAY_NAME@@ runtime secrets
  ansible.builtin.set_fact:
    @@VARIABLE_PREFIX@@_bootstrap_admin_token: "{{ @@VARIABLE_PREFIX@@_token_raw.content | b64decode | trim }}"
    @@VARIABLE_PREFIX@@_runtime_secret_payload:
      @@ENV_VAR_PREFIX@@_ADMIN_TOKEN: "{{ @@VARIABLE_PREFIX@@_token_raw.content | b64decode | trim }}"
  no_log: true

- name: Ensure the local @@DISPLAY_NAME@@ artifact directory exists
  ansible.builtin.file:
    path: "{{ @@VARIABLE_PREFIX@@_local_artifact_dir }}"
    state: directory
    mode: "0700"
  delegate_to: localhost
  become: false

- name: Mirror the @@DISPLAY_NAME@@ bootstrap admin token to the control machine
  ansible.builtin.copy:
    dest: "{{ @@VARIABLE_PREFIX@@_bootstrap_admin_token_local_file }}"
    content: "{{ @@VARIABLE_PREFIX@@_bootstrap_admin_token }}\n"
    mode: "0600"
  delegate_to: localhost
  become: false
  no_log: true

- name: Prepare OpenBao agent runtime secret injection for @@DISPLAY_NAME@@
  ansible.builtin.include_role:
    name: lv3.platform.common
    tasks_from: openbao_compose_env
  vars:
    common_openbao_compose_env_service_name: @@SERVICE_NAME@@
    common_openbao_compose_env_agent_dir: "{{ @@VARIABLE_PREFIX@@_openbao_agent_dir }}"
    common_openbao_compose_env_runtime_dir: "{{ @@VARIABLE_PREFIX@@_env_file | dirname }}"
    common_openbao_compose_env_env_file: "{{ @@VARIABLE_PREFIX@@_env_file }}"
    common_openbao_compose_env_secret_path: "{{ @@VARIABLE_PREFIX@@_openbao_secret_path }}"
    common_openbao_compose_env_secret_payload: "{{ @@VARIABLE_PREFIX@@_runtime_secret_payload }}"
    common_openbao_compose_env_policy_name: "{{ @@VARIABLE_PREFIX@@_openbao_policy_name }}"
    common_openbao_compose_env_policy_rules: |
      path "sys/health" {
        capabilities = ["read"]
      }

      path "kv/data/{{ @@VARIABLE_PREFIX@@_openbao_secret_path }}" {
        capabilities = ["read"]
      }

      path "kv/metadata/{{ @@VARIABLE_PREFIX@@_openbao_secret_path }}" {
        capabilities = ["read", "list"]
      }
    common_openbao_compose_env_approle_name: "{{ @@VARIABLE_PREFIX@@_openbao_approle_name }}"
    common_openbao_compose_env_agent_config_file: "{{ @@VARIABLE_PREFIX@@_openbao_agent_dir }}/agent.hcl"
    common_openbao_compose_env_agent_template_file: "{{ @@VARIABLE_PREFIX@@_openbao_agent_dir }}/runtime.env.ctmpl"
    common_openbao_compose_env_agent_template_src: runtime.env.ctmpl.j2
    common_openbao_compose_env_role_id_file: "{{ @@VARIABLE_PREFIX@@_openbao_agent_dir }}/role_id"
    common_openbao_compose_env_secret_id_file: "{{ @@VARIABLE_PREFIX@@_openbao_agent_dir }}/secret_id"
    common_openbao_compose_env_image: "{{ @@VARIABLE_PREFIX@@_openbao_agent_image }}"
    common_openbao_compose_env_legacy_env_files:
      - "{{ @@VARIABLE_PREFIX@@_legacy_env_file }}"
  no_log: true

- name: Render the @@DISPLAY_NAME@@ environment file
  ansible.builtin.template:
    src: runtime.env.j2
    dest: "{{ @@VARIABLE_PREFIX@@_env_file }}"
    owner: root
    group: root
    mode: "0600"
  no_log: true

- name: Render the @@DISPLAY_NAME@@ compose file
  ansible.builtin.template:
    src: docker-compose.yml.j2
    dest: "{{ @@VARIABLE_PREFIX@@_compose_file }}"
    owner: root
    group: root
    mode: "0644"

- name: Pull the @@DISPLAY_NAME@@ image
  ansible.builtin.command:
    argv:
      - docker
      - compose
      - --file
      - "{{ @@VARIABLE_PREFIX@@_compose_file }}"
      - pull
  args:
    chdir: "{{ @@VARIABLE_PREFIX@@_site_dir }}"
  register: @@VARIABLE_PREFIX@@_pull
  changed_when: >-
    'Pulling' in @@VARIABLE_PREFIX@@_pull.stdout
    or 'Downloaded newer image' in @@VARIABLE_PREFIX@@_pull.stdout
    or 'Pull complete' in @@VARIABLE_PREFIX@@_pull.stdout

- name: Start the @@DISPLAY_NAME@@ stack
  ansible.builtin.command:
    argv:
      - docker
      - compose
      - --file
      - "{{ @@VARIABLE_PREFIX@@_compose_file }}"
      - up
      - -d
      - --remove-orphans
  args:
    chdir: "{{ @@VARIABLE_PREFIX@@_site_dir }}"
  register: @@VARIABLE_PREFIX@@_up
  changed_when: >-
    'Creating' in @@VARIABLE_PREFIX@@_up.stdout
    or 'Recreating' in @@VARIABLE_PREFIX@@_up.stdout
    or 'Starting' in @@VARIABLE_PREFIX@@_up.stdout

- name: Verify the @@DISPLAY_NAME@@ runtime scaffold
  ansible.builtin.import_tasks: verify.yml
