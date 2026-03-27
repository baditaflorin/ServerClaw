# ADR 0005: Single-Node First Topology

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.2.0
- Implemented In Platform Version: 0.2.0
- Implemented On: 2026-03-21
- Date: 2026-03-21

## Context

This server is the first Proxmox node in the environment. The hardware has not yet been modeled in automation, and there is no existing cluster quorum partner, Ceph plan, or HA fabric defined in this repository.

The fastest route to a reliable system is to keep the first deployment simple enough that both humans and agents can understand, verify, and recover it.

## Decision

We will design the first delivery as a single Proxmox node with local storage and external backups, not as a cluster and not as a hyper-converged Ceph deployment.

Immediate implications:

- no cluster formation in phase one
- no Ceph deployment in phase one
- no HA assumptions in phase one
- backups and restore validation are mandatory before expansion

## Consequences

- The first automation set can stay small and testable.
- Recovery paths remain straightforward because there is only one control plane node.
- Future clustering remains possible, but it requires new ADRs covering quorum, networking, storage replication, and maintenance procedures.
