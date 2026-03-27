# linux_keepalived

Install and manage a repo-owned keepalived VRRP instance.

Inputs: VIPs, VRID, priority, interface, peer list, and a local health-check URL.
Outputs: an active keepalived service that follows Patroni leadership.
