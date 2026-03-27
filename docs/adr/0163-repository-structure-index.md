# ADR 0163: Repository Structure Index for Agent Discovery

- Status: Implemented
- Implementation Status: Implemented
- Implemented In Repo Version: 0.173.0
- Implemented In Platform Version: not applicable (repo-only)
- Implemented On: 2026-03-26
- Date: 2026-03-26

## Context

LLM agents onboarding to this repository have no prior context about its structure, purpose, or conventions. Without a machine-discoverable directory map, agents must:

- Inefficiently explore the repository tree with multiple Glob searches
- Read multiple documentation files to understand what each directory contains
- Waste tokens on trial-and-error discovery of important files
- Risk missing critical paths or duplicating work across directories

A structured, centralized index of directory purposes, containing files, and key metadata would allow agents to:
- Discover the repository structure in a single read
- Identify relevant directories for specific tasks instantly
- Find canonical locations for configurations, automation, and documentation
- Understand directory relationships and dependencies

## Decision

We will maintain a machine-readable **repository structure index** at `.repo-structure.yaml` that documents:

1. Every top-level directory and key subdirectories
2. Purpose and primary use of each directory
3. Key files and their roles within that directory
4. Owning concern or subsystem (bootstrap, networking, backup, etc.)
5. Agent discovery hints (keywords for finding this directory)

### Format

```yaml
repository: proxmox_florin_server
version: 1
last_updated: 2026-03-26
purpose: |
  Infrastructure-as-code for a Hetzner dedicated server running Proxmox VE.
  Manages bootstrap, VM provisioning, networking, backup, monitoring, and security.

directories:
  - path: docs/adr
    purpose: Architecture Decision Records - all major design decisions
    contains: decision records in markdown format (0001.md through 0162.md)
    concern: governance, architecture
    keywords: [decisions, architecture, history, rationale, consequences]
    for_agents: Start here for project direction and design rationale

  - path: docs/runbooks
    purpose: Operational runbooks and procedures for routine tasks
    contains: step-by-step guides for deployment, troubleshooting, recovery
    concern: operations
    keywords: [procedures, operational, how-to, runbook, recovery]
    for_agents: Find operational procedures and recovery steps

  - path: docs/workstreams
    purpose: Active workstream documentation and branch-specific ADRs
    contains: adr-XXXX-workstream-name.md files documenting active branches
    concern: project management, branch work
    keywords: [workstreams, parallel, branch, in-progress, tasks]
    for_agents: Understand what work is in progress and planned

  - path: playbooks
    purpose: Ansible playbooks for host and VM provisioning
    contains: site.yml, bootstrap.yml, and role-application playbooks
    concern: automation, infrastructure deployment
    keywords: [ansible, playbooks, deployment, automation, idempotent]
    for_agents: Find automation for host and VM provisioning

  - path: roles
    purpose: Ansible roles referenced by playbooks
    contains: reusable role implementations organized by concern
    concern: automation, shared logic
    keywords: [roles, reusable, task-groups, handlers]
    for_agents: Understand how automation is composed and organized

  - path: inventory
    purpose: Ansible inventory and host group definitions
    contains: hosts.yml, group_vars/, host_vars/, dynamic inventory scripts
    concern: infrastructure topology, declarative state
    keywords: [inventory, hosts, groups, variables, topology]
    for_agents: Understand the infrastructure layout and host groupings

  - path: config
    purpose: Service and application configuration templates
    contains: YAML/JSON configurations for all deployed services
    concern: service configuration, applications
    keywords: [config, templates, services, settings]
    for_agents: Find service configurations for deployed applications

  - path: scripts
    purpose: Utility and helper scripts (Python, Bash, etc)
    contains: operational scripts, data processing, CI helpers
    concern: automation, tooling
    keywords: [scripts, utilities, helpers, tools]
    for_agents: Find specific task helpers or operational utilities

  - path: tests
    purpose: Test suites for automated validation
    contains: unit tests, integration tests, molecule scenarios
    concern: validation, quality assurance
    keywords: [tests, validation, pytest, molecule, integration]
    for_agents: Understand testing approach and validation gates

  - path: versions
    purpose: Current observed state and version metadata
    contains: stack.yaml (canonical services), version snapshots
    concern: state tracking, versioning
    keywords: [versions, state, stack, canonical, deployed]
    for_agents: Check current deployed state and service versions

  - path: migrations
    purpose: Database and schema migration scripts
    contains: timestamped migration files for data changes
    concern: data management, backwards compatibility
    keywords: [migrations, database, schema, evolution]
    for_agents: Find data schema changes and migration history

  - path: collections/ansible_collections/lv3/platform
    purpose: Custom Ansible collection for this platform
    contains: roles, plugins, modules specific to this infrastructure
    concern: shared automation, extensibility
    keywords: [collection, custom, modules, plugins, reusable]
    for_agents: Find platform-specific custom Ansible components

  - path: packer
    purpose: Packer templates for VM image building
    contains: Debian cloud-init templates, image build configurations
    concern: image building, templates
    keywords: [packer, image, template, vm, cloud-init]
    for_agents: Understand how VM images are built

  - path: docker
    purpose: Docker configurations and compose files
    contains: Dockerfile definitions, docker-compose templates
    concern: containerization, service deployment
    keywords: [docker, container, compose, image]
    for_agents: Find container and compose configurations

  - path: tofu
    purpose: OpenTofu/Terraform code for infrastructure provisioning
    contains: infrastructure-as-code for cloud resources
    concern: infrastructure provisioning, IaC
    keywords: [tofu, terraform, provisioning, iac, cloud]
    for_agents: Find infrastructure code for cloud provisioning

  - path: windmill
    purpose: Windmill workflow definitions and automations
    contains: YAML workflow definitions for scheduled tasks
    concern: workflow automation, scheduled tasks
    keywords: [windmill, workflow, automation, scheduled]
    for_agents: Find workflow and scheduler configurations

  - path: molecule
    purpose: Molecule test scenarios for Ansible role testing
    contains: test scenarios for validating Ansible roles
    concern: testing, role validation
    keywords: [molecule, testing, scenarios, validation]
    for_agents: Find role testing configurations

  - path: receipts
    purpose: Operational receipts and audit trails
    contains: recorded state changes, deployment receipts
    concern: audit, operational history
    keywords: [receipts, audit, history, deployment]
    for_agents: Check operational history and state changes

  - path: requirements
    purpose: Python, system, and dependency specifications
    contains: requirements.txt, poetry.lock, system package lists
    concern: dependencies, versions
    keywords: [requirements, dependencies, packages, versions]
    for_agents: Check dependencies and versions

  - path: keys
    purpose: SSH keys and cryptographic material
    contains: bootstrap keys, operator keys, automation keys
    concern: security, credentials
    keywords: [keys, ssh, credentials, security]
    for_agents: Understand key material structure (do not expose keys)

  - path: .github
    purpose: GitHub Actions workflows and CI configuration
    contains: GitHub Actions workflow YAML files
    concern: ci, external automation
    keywords: [github, ci, actions, workflows]
    for_agents: Understand GitHub Actions pipelines (mirrors local Gitea)

  - path: .gitea
    purpose: Gitea Actions workflows and CI configuration
    contains: Gitea Actions workflow YAML files (primary CI)
    concern: ci, local automation
    keywords: [gitea, ci, actions, workflows, local]
    for_agents: Find local CI pipelines in Gitea

top_level_files:
  - file: README.md
    purpose: Project overview and current status summary
    for_agents: Start here for high-level context and current state

  - file: AGENTS.md
    purpose: Guidelines and rules for LLM agents working on this repo
    for_agents: MUST READ - contains working rules and conventions

  - file: workstreams.yaml
    purpose: List of active workstreams and branch assignments
    for_agents: Understand parallel work and branch organization

  - file: VERSION
    purpose: Current repository version number
    for_agents: Check for versioning and identify release boundaries

  - file: Makefile
    purpose: Development and operational task runners
    for_agents: Find common development tasks and automations

  - file: ansible.cfg
    purpose: Ansible configuration and defaults
    for_agents: Understand Ansible behavior and settings

  - file: mkdocs.yml
    purpose: Documentation site configuration
    for_agents: Understand how documentation is published

  - file: changelog.md
    purpose: Versioned change log and release notes
    for_agents: Check history of changes and releases

  - file: pyproject.toml
    purpose: Python project metadata and tool configuration
    for_agents: Check Python tooling and dependencies

  - file: .repo-structure.yaml
    purpose: This file - machine-readable directory index
    for_agents: Use this to orient to the repository structure

quick_start_for_agents:
  1. Read README.md for project overview
  2. Read AGENTS.md for working rules and conventions
  3. Use this file (.repo-structure.yaml) to find directories relevant to your task
  4. Check docs/adr/ for design rationale
  5. Check docs/runbooks/ for operational procedures
  6. Check workstreams.yaml for parallel work organization
