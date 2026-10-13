# fleet_tailscale_node

Node-level Tailscale settings for fleet hypervisors that are not covered by `lv3.platform.proxmox_tailscale` (which only
serves the 0mcp host and re-runs `tailscale up`). It manages one preference: the advertised subnet routes, via
`tailscale set --advertise-routes`, so no other node setting (tags, SSH, DNS, accept-routes) is touched.

The tailnet **policy** (grants, `autoApprovers`, tests) is not managed here; it lives in the control plane and is being
codified separately. Without an auto-approver for a route the advertisement stays pending in the admin console.
