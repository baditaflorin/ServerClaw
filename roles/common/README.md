# Common Role Task Library

This role provides reusable task entrypoints for patterns that recur across service roles.

Available task entrypoints:

- `assert_vars` validates required variables and optional extra assertions
- `directory_tree` creates one or more directories with shared owner/group/mode defaults
- `systemd_unit` enables and starts a systemd unit with optional active-state verification
- `wait_port` waits for a TCP listener with shared timeout defaults

Use the task entrypoints with `include_role`, for example:

```yaml
- name: Validate role inputs
  ansible.builtin.include_role:
    name: common
    tasks_from: assert_vars
  vars:
    common_assert_vars_required:
      - example_required_var
```
