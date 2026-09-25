# fleet_runner_private_0mcp_transport

Installs the fixed, non-secret `fleet-runner` transport on `0docker_builder` only. It pins the 0mcp bastion and VM180 host keys, sets an SSH configuration that enforces `StrictHostKeyChecking yes`, and writes the root-only transport JSON consumed by `FLEET_PRIVATE_0MCP_TRANSPORT_FILE`.

It writes `/usr/local/sbin/fleet-runner-private-0mcp`, the root-only entrypoint that fixes `FLEET_PRIVATE_0MCP_TRANSPORT_FILE` before invoking the runner. It neither installs SSH private keys nor carries tokens, certificates, service configuration, or image references. The existing approved Builder identities remain an external prerequisite.
