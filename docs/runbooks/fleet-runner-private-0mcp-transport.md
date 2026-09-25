# Builder private 0mcp transport

Apply `playbooks/fleet-runner-private-0mcp-transport.yml` only to the exact `0docker_builder` inventory host. The role writes root-owned mode `0600` topology at `/etc/fleet-runner/private-0mcp-transport.json`, root-owned pinned known-hosts, and SSH configuration that resolves the pinned file with `StrictHostKeyChecking=yes`. Use only `/usr/local/sbin/fleet-runner-private-0mcp` for a private-lane invocation; it sets the transport path itself and overrides any inherited value.

The content is non-secret deployment topology. Do not put an SSH private key, token, certificate, image digest, service data, or a `StrictHostKeyChecking=no` escape hatch in the role. Verify with `ssh -G -o StrictHostKeyChecking=yes -J root@203.0.113.1:2222 claude-ops@10.10.10.80` and then run the broker's mTLS canary; an unsuccessful identity or host-key check is a failed precondition, not a reason to relax the transport.
