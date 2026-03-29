# nomad_cluster_member

Install and manage one Nomad server or client agent for the ADR 0232 internal job scheduler cluster.

Inputs: pinned Nomad version, local TLS artifacts, server/client role flags, and cluster network settings.
Outputs: a repo-managed `lv3-nomad` systemd unit, local CLI wrapper, and an active Nomad agent.
