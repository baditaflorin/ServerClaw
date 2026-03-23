# loki_log_agent

Installs Grafana Alloy and ships managed host, guest, and container logs into the central Loki endpoint.

Inputs: Grafana APT repository settings, Alloy config path, target Loki push URL, and host-role-specific log source toggles.
Outputs: a running `alloy` service with managed journald collection plus optional NGINX file and Docker container log shipping.
