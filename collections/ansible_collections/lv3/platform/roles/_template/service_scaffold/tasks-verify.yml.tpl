---
- name: Wait for the @@DISPLAY_NAME@@ runtime to listen locally
  ansible.builtin.wait_for:
    host: 127.0.0.1
    port: "{{ @@VARIABLE_PREFIX@@_internal_port }}"
    delay: 0
    timeout: 180

- name: Verify the @@DISPLAY_NAME@@ health endpoint
  ansible.builtin.uri:
    url: "{{ @@VARIABLE_PREFIX@@_private_url }}{{ @@VARIABLE_PREFIX@@_healthcheck_path }}"
    method: GET
    status_code: 200
  register: @@VARIABLE_PREFIX@@_verify_health
  retries: 18
  delay: 5
  until: @@VARIABLE_PREFIX@@_verify_health.status == 200
  changed_when: false
