# nomad_cluster_bootstrap

Generate controller-local Nomad bootstrap artifacts, initialize ACL access, register repo-managed smoke jobs, and verify the live cluster.

Inputs: controller-local file paths, monitoring/runtime/build inventory hosts, and repo-managed job specs.
Outputs: persistent `.local/nomad/` TLS and token artifacts plus a verified Nomad cluster with running smoke jobs.
