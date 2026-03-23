# etcd_cluster_member

Install and manage one static etcd member for the Postgres HA DCS quorum.

Inputs: member name, bind host, peer/client ports, cluster membership, and managed paths.
Outputs: a repo-managed `lv3-etcd` systemd unit and an active etcd member.
