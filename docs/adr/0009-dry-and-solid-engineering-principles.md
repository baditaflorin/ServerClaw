# ADR 0009: DRY And Solid Engineering Principles

- Status: Accepted
- Date: 2026-03-21

## Context

This repository will be operated over time by both humans and coding agents. That makes duplication and weak structure especially costly:

- duplicate logic drifts
- duplicate documentation contradicts itself
- one-off host fixes become invisible dependencies
- fragile automation becomes unsafe to reuse

The repo needs a default engineering posture that keeps automation maintainable and predictable.

## Decision

We will treat the following as core repository rules:

1. DRY
   - define infrastructure facts once and reuse them
   - avoid copying package lists, network values, storage values, and security settings across multiple files
   - prefer shared roles, variables, templates, and reusable tasks over repeated shell blocks
2. Solid structure
   - keep responsibilities separated by concern: bootstrap, packages, networking, storage, security, backups, and Proxmox configuration
   - make interfaces explicit between layers such as host bootstrap vs Proxmox API automation
   - keep changes small, testable, and reversible
3. Durable operations
   - no undocumented one-off manual fixes
   - every important operational rule must live in code, a runbook, or an ADR
   - observed host state must be verifiable against declared desired state

## Consequences

- New automation should be refactored when duplication appears instead of letting repeated patterns accumulate.
- Variables and data models should be introduced early for host facts, repositories, users, networks, and storage.
- Any future playbook or role that bundles unrelated concerns should be split before it grows further.
