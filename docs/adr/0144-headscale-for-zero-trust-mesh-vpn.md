# ADR 0144: Headscale for Zero-Trust Mesh VPN

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

Operator access to the platform's private network is currently managed through Tailscale using the commercial Tailscale coordination server. This provides the Tailscale 100.x.x.x mesh VPN that routes operator traffic to the Proxmox host and internal services.

The commercial Tailscale coordination server is a third-party dependency that:

- Maintains a record of which devices have connected to the platform and when.
- Holds the public keys of all nodes in the tailnet.
- Is required for the tailnet to function: if Tailscale's coordination server is unavailable, new connections cannot be established (existing connections are unaffected, but rekeying and new device enrollment require it).
- Requires account management and billing outside the platform.
- Logs authentication events that are not under the operator's control.

**Headscale** is a self-hosted, open-source implementation of the Tailscale coordination server. Running Headscale on the Proxmox host replaces the Tailscale commercial coordination server with one the operator controls, while retaining full compatibility with the official Tailscale and Taildrop clients.

This aligns with the platform's principle of self-hosted infrastructure for all control-plane components. The VPN coordination server is a control-plane component; it should be subject to the same visibility, backup, and access control as the rest of the platform.

## Decision

We will deploy **Headscale** on the Proxmox host as a systemd service (not in a VM or container, for maximum availability and simplicity), replacing the commercial Tailscale coordination server.

### Deployment

```yaml
# Deployed as a systemd service on the Proxmox host (bare metal)
# Not containerised: Headscale is a single Go binary with no runtime dependencies.
# This maximises availability: it runs before any VMs start.

headscale:
  binary: /usr/local/bin/headscale
  config: /etc/headscale/config.yaml
  db: /var/lib/headscale/db.sqlite   # SQLite; small dataset, no Postgres dependency
  listen_addr: 0.0.0.0:443           # Public internet (HTTPS)
  public_url: https://headscale.lv3.org
  tls: letsencrypt                   # headscale manages its own cert
```

`headscale.lv3.org` is a new public subdomain that serves the coordination protocol. Tailscale clients point their custom control server URL to this endpoint.

### Authentication model

Headscale uses **pre-authentication keys** (preauthkeys) for new device enrollment. Unlike the commercial Tailscale which uses OAuth, preauthkeys are short-lived (24-hour TTL) and single-use by default:

```bash
# Issue a new key for device enrollment (managed via the platform CLI)
$ lv3 headscale new-preauth-key --user ops --expiry 24h --reusable false
preauth:abc123...

# Enroll a device
$ tailscale up --login-server https://headscale.lv3.org --authkey preauth:abc123...
```

Preauth keys are managed in OpenBao (ADR 0043) with a 24-hour TTL. Key issuance is an authenticated platform CLI operation requiring T3 trust (ADR 0125).

### Access control lists (ACLs)

Headscale ACLs (equivalent to Tailscale's `tailnet policy`) define which devices can reach which addresses:

```json
// config/headscale-acl.json (managed in repo, applied by Ansible)
{
  "acls": [
    {
      "action": "accept",
      "src": ["tag:operator"],
      "dst": ["tag:proxmox-host:*", "tag:internal-services:*"]
    },
    {
      "action": "accept",
      "src": ["tag:agent"],
      "dst": ["tag:internal-services:22", "tag:internal-services:5432"]
    }
  ],
  "tagOwners": {
    "tag:operator": ["user:live"],
    "tag:agent":    ["user:automation"]
  }
}
```

ACL changes go through the standard repo → Ansible convergence pipeline, making network policy changes auditable and version-controlled.

### API integration for agents

Headscale provides a REST API and a gRPC API that agents can use to:
- List connected devices and their last-seen times.
- Check whether an operator device is currently connected (used by the handoff protocol ADR 0131 to determine if an escalation will reach a human promptly).
- Revoke device keys on incident response (e.g., if an operator laptop is reported stolen).

```python
# platform/network/headscale.py
hs = HeadscaleClient(base_url="http://localhost:8080", api_key=openbao.get("headscale/api-key"))
devices = hs.list_devices(user="ops")
online_devices = [d for d in devices if d.last_seen > datetime.now() - timedelta(minutes=5)]
operator_reachable = len(online_devices) > 0
```

This enables the handoff protocol (ADR 0131) to route an escalation differently when no operator device is online.

### Migration path

1. Deploy Headscale on the Proxmox host.
2. Issue preauthkeys for all operator devices.
3. Re-enroll each device with `tailscale up --login-server https://headscale.lv3.org`.
4. Verify connectivity on all services via the new tailnet.
5. Revoke the commercial Tailscale account (after a 30-day overlap period).

No existing Tailscale client software needs to be replaced; the official Tailscale client is reused with a custom `--login-server` pointing to the self-hosted Headscale instance.

## Consequences

**Positive**

- The VPN coordination server is self-hosted and under the operator's control. No third party has visibility into which devices are connected or when.
- ACL policy is version-controlled and applied via Ansible like all other platform configuration.
- The Headscale API enables agents to check operator connectivity before routing escalations, improving handoff effectiveness (ADR 0131).
- Eliminating the commercial Tailscale subscription removes an ongoing external billing dependency.

**Negative / Trade-offs**

- Headscale must be kept available for device rekeying and new enrollments. Running it on the Proxmox host (not in a VM) maximises availability but means a Proxmox host outage also loses VPN coordination. Existing tunnel connections survive short outages, but extended Proxmox outages prevent new connections.
- Headscale does not support all Tailscale features: Taildrop (file transfer), Tailscale Funnel (public endpoint exposure), and SSH key management are commercial-only. These features are not currently used by the platform, so this is not an immediate gap.
- The migration requires re-enrollment of all devices. Any device that is not re-enrolled before the commercial Tailscale account is revoked will lose access to the platform.

## Boundaries

- Headscale manages the VPN coordination plane only. The data plane (WireGuard tunnels) continues to use the official Tailscale client software on each device.
- This ADR does not change the network topology or ACLs; it migrates the control server. Existing ACLs are ported to Headscale format.

## Related ADRs

- ADR 0006: Security baseline (operator access model; Tailscale/Headscale is the access mechanism)
- ADR 0014: Operator access to private guest network (this ADR changes how that access is provided)
- ADR 0043: OpenBao (preauthkey storage)
- ADR 0045: Control-plane communication lanes (internal network topology; unchanged)
- ADR 0067: Guest network policy (ACL policy managed alongside nftables rules)
- ADR 0125: Agent capability bounds (T3 required for preauth key issuance)
- ADR 0131: Multi-agent handoff protocol (agent checks operator connectivity via Headscale API)
