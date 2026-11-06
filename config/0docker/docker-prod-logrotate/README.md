# Production Docker fleet-tool log rotation

The legacy `/etc/logrotate.d/fleet-defaults` used `/var/log/*.log` and
`/var/log/**/*.log`. Those patterns matched files already owned by the distro
policies, including alternatives and apt history, and made the daily service
fail. The replacement lists only the four fleet-tool paths found on the VM.
Package logs continue to use their existing policies.

Fleet-tool logs rotate daily or above 100 MiB, retain seven rotations, and use
`copytruncate` so processes holding an open log file continue writing. Like
other copytruncate policies, concurrent writes during the copy/truncate window
can lose a small amount of log data. A new tool with a different log directory
needs an explicit policy rather than broadening this to all OS logs.

From a reviewed checkout, use the existing root SSH alias for VM101:

```sh
ansible-playbook -i '0docker_docker_prod,' config/0docker/docker-prod-logrotate/apply.yml --check --diff
ansible-playbook -i '0docker_docker_prod,' config/0docker/docker-prod-logrotate/apply.yml
```

The apply saves the previous file, validates both the staged file and the
combined system configuration, restores the previous file on a validation
failure, and runs the daily service only after a changed policy passes.
`logrotate --debug /etc/logrotate.conf` must exit zero; the service's
`Result` must be `success` and `ExecMainStatus` zero. Rollback restores the
timestamped backup over the policy and validates the combined config again.
