# Configure tailnet-only service access

## Purpose

Declare a service as private-only and reachable over the operator tailnet,
without coupling the service to a specific mesh control-plane vendor.

## Service declaration

In a service bundle, retain `exposure: private-only` and add:

```yaml
mesh_access: tailnet
```

The catalog validator requires the service to remain private-only and to have
managed DNS with `visibility: tailnet` plus a managed Tailscale TCP proxy access
path in the Proxmox topology.
Do not publish the same hostname through the public edge as a workaround.

## Select the control plane

The Tailscale client remains installed on the Proxmox host in either mode.
Configure the following flat variables in `inventory/host_vars/proxmox-host.yml`
or its ignored deployment host-vars overlay:

Hosted Tailscale:

```yaml
proxmox_tailscale_provider: tailscale
proxmox_tailscale_login_server: ""
```

Self-hosted Headscale:

```yaml
proxmox_tailscale_provider: headscale
proxmox_tailscale_login_server: "https://headscale.example.com"
```

The role rejects an unknown provider, a custom login-server URL with hosted
Tailscale, and a missing or non-HTTPS URL for Headscale. Headscale is an
open-source, self-hosted control server compatible with Tailscale clients; it
removes the hosted control-plane dependency but does not replace the Tailscale
client. A separate mesh such as NetBird is not a drop-in provider here; it needs
its own client installation, route/policy management, and service-proxy
integration. Review the feature-support differences and the separate migration
runbook before operating a Headscale deployment.

For an already enrolled host, the role compares the active control-server URL
with the selected provider and refuses a mismatch by default. A planned
Tailscale-to-Headscale or Headscale-to-Tailscale move requires the explicit
`proxmox_tailscale_allow_control_plane_migration: true` setting for that apply;
follow the migration runbook and keep an existing management session open.

## Apply boundary

Changing these variables only changes declared desired configuration. It does
not migrate a running node, update hosted Tailscale ACLs, approve subnet routes,
or configure split DNS. Keep an existing management session open, back up the
current enrollment details, migrate one device at a time, and verify operator
reachability before changing the next node. Use a separate reviewed change for
tailnet ACL policy and private DNS.
