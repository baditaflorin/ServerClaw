# Reference Platform Inventory

This directory provides a public-safe starter topology for a fresh fork.

Use these files when you want the structure of the LV3 platform without copying
the integrated live hostnames, addresses, or domains from the current
deployment.

Recommended flow:

1. Copy [`hosts.yml`](./hosts.yml), [`group_vars/platform.yml`](./group_vars/platform.yml), and [`host_vars/proxmox_reference.yml`](./host_vars/proxmox_reference.yml) into your fork-local inventory surfaces.
2. Pair them with [`config/examples/reference-provider-profile.yaml`](../../../config/examples/reference-provider-profile.yaml) and [`config/examples/reference-publication-profile.json`](../../../config/examples/reference-publication-profile.json).
3. Create your controller-local overlay from [`config/examples/reference-controller-local-secrets.json`](../../../config/examples/reference-controller-local-secrets.json).
4. Replace every `example.com`, `example.internal`, `203.0.113.0/24`, and `100.64.0.0/10` placeholder before any live apply.

These samples are intentionally minimal. They are meant to show the contract
shape, not to mirror every service currently running on the integrated LV3
platform.
