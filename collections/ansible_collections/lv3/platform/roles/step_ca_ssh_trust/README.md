# step_ca_ssh_trust

Installs the `step` CLI on Linux targets, trusts the shared LV3 SSH user CA, and issues SSH host certificates for the Proxmox host and managed guests.

Inputs: the controller-local step-ca bootstrap artifacts, the private CA URL, SSH host-key paths, and any extra host principals that should appear on a signed host certificate.
Outputs: `/etc/ssh/lv3-user-ca.pub`, `/etc/ssh/ssh_host_ed25519_key-cert.pub`, and an sshd drop-in that enables CA-based user and host trust.
