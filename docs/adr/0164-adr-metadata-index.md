# ADR 0164: ADR Metadata Index and Fast Discovery Protocol

- Status: Implemented
- Implementation Status: Implemented
- Implemented In Repo Version: 0.173.0
- Implemented In Platform Version: not applicable (repo-only)
- Implemented On: 2026-03-26
- Date: 2026-03-26

## Context

This repository maintains 162+ Architecture Decision Records (ADRs) documenting every major design decision. LLM agents onboarding to the project need to:

- Find relevant ADRs for a given task without reading all 162+ documents
- Understand relationships between decisions (which ADRs depend on which)
- Identify implemented vs. proposed decisions quickly
- Discover the design rationale behind existing infrastructure without exhaustive search

Currently, agents must:
- Glob search for ADR files by name or pattern
- Read multiple ADRs to understand dependencies
- Waste tokens on reading irrelevant ADRs
- Risk missing critical context that affects their decisions

A machine-readable metadata index of all ADRs would enable token-efficient discovery and understanding of the decision landscape.

## Decision

We will maintain a **machine-readable ADR metadata index** at `docs/adr/.index.yaml` that includes:

1. **All ADRs with metadata**: number, title, status, implementation status
2. **Keywords and tags**: searchable terms for discovering relevant decisions
3. **Dependencies**: which ADRs reference/depend on/build upon which others
4. **Concerns**: categorization by infrastructure domain
5. **Quick summaries**: 1-2 sentence summary of the decision (not the full context)

### Format

```yaml
version: 1
last_updated: 2026-03-26
total_adrs: 162

adr_index:
  - adr: 0001
    title: Bootstrap Dedicated Host With Ansible
    status: Accepted
    implementation_status: Implemented
    implemented_version: 0.2.0
    date: 2026-03-21
    concern: bootstrap
    keywords: [bootstrap, ansible, host, hetzner]
    summary: Two-stage bootstrap - out-of-band SSH access, then in-band Ansible infrastructure-as-code
    depends_on: []
    referenced_by: [0002, 0003, 0004]

  - adr: 0002
    title: Target Proxmox VE 9 on Debian 13
    status: Accepted
    implementation_status: Implemented
    implemented_version: 0.2.0
    date: 2026-03-21
    concern: host-os
    keywords: [proxmox, debian, version-target, host]
    summary: Use Proxmox VE 9 on Debian 13 as the official base OS combination
    depends_on: [0001]
    referenced_by: [0003, 0004]

  - adr: 0007
    title: Agent-Oriented Access Model
    status: Accepted
    implementation_status: Implemented
    implemented_version: 0.3.0
    date: 2026-03-21
    concern: security, access-control
    keywords: [access, agents, security, identities]
    summary: Use durable agent identities instead of user accounts for API access
    depends_on: []
    referenced_by: [0040, 0056, 0090]

  - adr: 0031
    title: Repository Validation Pipeline
    status: Accepted
    implementation_status: Implemented
    implemented_version: 0.4.0
    date: 2026-03-21
    concern: ci-cd, validation
    keywords: [validation, ci, pre-commit, gates]
    summary: Pre-push and server-side validation gates for all repository changes
    depends_on: [0017]
    referenced_by: [0143]

  - adr: 0044
    title: Windmill for Self-Hosted Automation
    status: Accepted
    implementation_status: Implemented
    implemented_version: 0.50.0
    date: 2026-03-21
    concern: automation, workflow
    keywords: [windmill, workflow, scheduling, automation]
    summary: Deploy Windmill for local workflow automation and scheduled tasks
    depends_on: [0023]
    referenced_by: [0081, 0121, 0143]

  - adr: 0056
    title: Keycloak for SSO
    status: Accepted
    implementation_status: Implemented
    implemented_version: 0.60.0
    date: 2026-03-21
    concern: security, identity
    keywords: [sso, keycloak, oidc, identity]
    summary: Use Keycloak as the identity provider for all services requiring authentication
    depends_on: [0023]
    referenced_by: [0143, 0147]

  - adr: 0081
    title: Deployment Changelog Generation
    status: Accepted
    implementation_status: Implemented
    implemented_version: 0.80.0
    date: 2026-03-21
    concern: documentation, release
    keywords: [changelog, release, documentation, notes]
    summary: Automatically generate changelog from git commits on push to main
    depends_on: [0044]
    referenced_by: [0143]

  - adr: 0111
    title: End-to-End Integration Test Suite
    status: Accepted
    implementation_status: Implemented
    implemented_version: 0.110.0
    date: 2026-03-21
    concern: testing, validation
    keywords: [testing, integration, pytest, validation]
    summary: Maintain pytest integration test suite for end-to-end platform validation
    depends_on: [0031]
    referenced_by: [0143]

  - adr: 0121
    title: Local Search and Indexing Fabric
    status: Accepted
    implementation_status: Implemented
    implemented_version: 0.119.0
    date: 2026-03-21
    concern: documentation, search
    keywords: [search, indexing, discovery, documentation]
    summary: Local indexer for ADRs, runbooks, and configurations - triggered by git webhooks
    depends_on: [0044]
    referenced_by: [0143]

  - adr: 0132
    title: Self-Describing Platform Manifest
    status: Accepted
    implementation_status: Implemented
    implemented_version: 0.120.0
    date: 2026-03-21
    concern: architecture, state
    keywords: [manifest, state, services, topology]
    summary: Machine-readable manifest describing all deployed services, configuration, and topology
    depends_on: [0044]
    referenced_by: [0143]

  - adr: 0143
    title: Gitea for Self-Hosted Git and Webhook-Driven Automation
    status: Accepted
    implementation_status: Implemented
    implemented_version: 0.122.0
    date: 2026-03-24
    concern: ci-cd, git, automation
    keywords: [gitea, git, ci, webhook, local]
    summary: Deploy Gitea as self-hosted git service with local Actions CI and webhook automation
    depends_on: [0023, 0044, 0056, 0081, 0111, 0121, 0132]
    referenced_by: [0144]

concerns:
  bootstrap: [0001, 0003, 0004, 0005]
  host-os: [0002, 0006]
  vm-topology: [0010, 0016, 0018]
  networking: [0012, 0013, 0014, 0015]
  security: [0006, 0007, 0041, 0047]
  storage: [0019, 0029]
  monitoring: [0011, 0027]
  backup: [0029]
  ci-cd: [0031, 0083, 0143]
  automation: [0044, 0090]
  identity: [0056, 0147]
  documentation: [0081, 0094, 0121]
  testing: [0111]
  release: [0081]
  api: [0090, 0144]

discovery_queries:
  "how do we bootstrap": [0001, 0003, 0004, 0005]
  "authentication and identity": [0007, 0056, 0147]
  "ci and testing": [0031, 0083, 0111, 0143]
  "automation": [0044, 0090]
  "disaster recovery": [0029, 0051]
  "monitoring": [0011, 0027]
  "networking and ingress": [0012, 0013, 0014, 0015]
  "vm management": [0010, 0016, 0018]
  "agent access": [0007, 0090, 0132]
  "deployment": [0081, 0143]
  "local services": [0023, 0024, 0027, 0043, 0044]

  - adr: 0163
    title: Repository Structure Index for Agent Discovery
    status: Proposed
    implementation_status: Proposed
    implemented_version: null
    date: 2026-03-26
    concern: agent-discovery, documentation
    keywords: [structure, index, discovery, agent, onboarding]
    summary: Machine-readable directory map enabling agents to discover repo structure in one read
    depends_on: []
    referenced_by: [0164, 0165, 0166, 0167, 0168]

  - adr: 0164
    title: ADR Metadata Index and Fast Discovery Protocol
    status: Proposed
    implementation_status: Proposed
    implemented_version: null
    date: 2026-03-26
    concern: agent-discovery, documentation
    keywords: [adr, index, discovery, metadata, fast-lookup]
    summary: Structured metadata index for all ADRs enabling token-efficient decision discovery
    depends_on: [0163]
    referenced_by: [0168]

  - adr: 0165
    title: Playbook and Role Metadata Standard for Agent Discovery
    status: Proposed
    implementation_status: Proposed
    implemented_version: null
    date: 2026-03-26
    concern: agent-discovery, automation
    keywords: [playbook, role, metadata, standard, discovery]
    summary: Standardized metadata headers for all playbooks/roles documenting purpose, inputs, outputs, dependencies
    depends_on: [0163]
    referenced_by: [0168]

  - adr: 0166
    title: Canonical Configuration Locations Registry
    status: Proposed
    implementation_status: Proposed
    implemented_version: null
    date: 2026-03-26
    concern: agent-discovery, configuration
    keywords: [config, locations, registry, source-of-truth, canonical]
    summary: Central registry mapping all config file locations to their purposes, owners, and update processes
    depends_on: [0163]
    referenced_by: [0168]

  - adr: 0167
    title: Agent Handoff and Context Preservation Protocol
    status: Proposed
    implementation_status: Proposed
    implemented_version: null
    date: 2026-03-26
    concern: agent-coordination, context, handoff
    keywords: [handoff, context, protocol, agent, worktree, commit, workstream]
    summary: Standards for leaving clear context for next agent - commit format, workstream updates, receipt tracking
    depends_on: [0163, 0166]
    referenced_by: [0168]

  - adr: 0168
    title: Automated Enforcement of Agent Discovery and Handoff Standards
    status: Proposed
    implementation_status: Proposed
    implemented_version: null
    date: 2026-03-26
    concern: agent-discovery, validation, automation
    keywords: [enforcement, validation, automation, drift-prevention, pre-push-gate]
    summary: Pre-push gate validation that enforces metadata headers, workstream updates, commit format, and receipt creation
    depends_on: [0163, 0164, 0165, 0166, 0167]
    referenced_by: []

implementation_status_summary:
  implemented: 162
  accepted: 0
  proposed: 6
  deprecated: 0

# Agent quick-reference
agent_discovery_tips:
  - "Search .index.yaml for keywords relevant to your task"
  - "Check 'depends_on' and 'referenced_by' to understand decision relationships"
  - "Use 'concern' field to find ADRs related to a specific infrastructure domain"
  - "Check 'discovery_queries' for common patterns"
  - "When in doubt about rationale, read the relevant ADR before making changes"
  - "This index is automatically generated - do not edit by hand"
