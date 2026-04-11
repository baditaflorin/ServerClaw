# Configure Public Ingress Runbook

## Purpose

This runbook captures the executable path used to expose only the NGINX VM to the public internet while keeping the other private guests non-public by default.

## Result

- the host public IPv4 forwards TCP `80` and `443`
- forwarded traffic is DNATed to the NGINX VM at `10.10.10.10`
- runtime, build, and monitoring guests remain private by default

## Command

```bash
make configure-ingress
```

## What the playbook does

1. Renders nftables DNAT rules for the declared public ingress ports.
2. Allows only the forwarded edge traffic from `vmbr0` to the private bridge.
3. Reloads nftables without rewriting host bridge addresses.

## Verification

From an external client:

```bash
curl -I http://203.0.113.1
curl -I http://nginx.example.com
```

From the Proxmox host:

```bash
sudo nft list ruleset
```
