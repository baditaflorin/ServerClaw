# ADR 0014: Operator Access To Private Guest Network

- Status: Accepted
- Date: 2026-03-21

## Context

The private VM network `10.10.10.0/24` must be reachable from operator laptops for administration and build workflows, especially for the Docker build VM at `10.10.10.30`.

At the same time, the guest network should not be made broadly public just to make operator access easy.

The access model needs to satisfy two realities:

- phase-one bootstrap must work quickly
- steady-state access should be deliberate, private, and repeatable

## Decision

We will use a two-stage operator access model.

Stage one: bootstrap access

- use the Proxmox host as the temporary jump point
- laptops reach private guests via SSH `ProxyJump` or equivalent tunneling through the Proxmox host
- this path is acceptable only while the dedicated guest access path is being built

Stage two: steady-state operator access

- provide laptop access to `10.10.10.0/24` through a WireGuard-based private access path
- do not expose the Docker runtime VM, Docker build VM, or monitoring VM directly to the public internet
- keep the build VM reachable privately for interactive remote work from approved operator machines

## Implications For The Build VM

The build VM at `10.10.10.30` is intentionally private but operator-reachable.

That means:

- remote SSH from approved laptops should work over the private access path
- no general public SSH exposure should be required
- large build throughput can be supported without changing the public exposure model

## Consequences

- We avoid weakening the private VM network just to make laptop access convenient.
- The Proxmox host can serve as a temporary bootstrap hop without becoming the permanent user-facing access pattern.
- WireGuard becomes part of the platform access design and should be treated as first-class infrastructure.

## Follow-up requirements

This ADR still requires implementation details for:

- where WireGuard terminates in steady state
- peer management and key rotation
- which laptops or admin devices are allowed
- whether the monitoring VM should also be reachable over the same access path
