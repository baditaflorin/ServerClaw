---
- name: Converge @@DISPLAY_NAME@@ on @@VM@@
  hosts: @@VM@@
  become: true
  gather_facts: true

  pre_tasks:
    - name: Ensure target guest is Debian
      ansible.builtin.assert:
        that:
          - ansible_distribution == "Debian"
        fail_msg: "This playbook only supports Debian guests."

  roles:
    - role: lv3.platform.@@ROLE_NAME@@
