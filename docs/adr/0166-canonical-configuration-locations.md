# ADR 0166: Canonical Configuration Locations Registry

- Status: Accepted
- Implementation Status: Implemented
- Implemented Version: 0.173.0
- Date: 2026-03-26

## Context

Infrastructure state and configuration in this repository is spread across multiple locations:

- Ansible inventory and variables in `inventory/`
- Service configurations in `config/`
- Stack definitions in `versions/stack.yaml`
- Version metadata in `VERSION`
- Changelog in `changelog.md`
- Deployed service state in `receipts/`
- Docker Compose definitions in `docker/`
- Terraform/OpenTofu code in `tofu/`
- Packer templates in `packer/`
- Workstream tracking in `workstreams.yaml`

LLM agents need to know:

- Where is the source of truth for X configuration?
- Where should I document Y change?
- How do related configuration files relate to each other?
- What file controls Z behavior?

Without a central registry, agents waste tokens:
- Searching for where a configuration lives
- Finding duplicate configurations in multiple locations
- Guessing which file is the source of truth
- Missing where to record configuration changes

A canonical registry of configuration locations and their purposes would enable agents to:
- Find the right file in one lookup
- Understand the relationship between configuration files
- Know which file to update for specific changes
- Avoid duplicating configuration across locations

## Decision

We will maintain a **canonical configuration locations registry** at `.config-locations.yaml` documenting:

1. Every location where configuration lives
2. What each location controls
3. Format and structure of the configuration
4. Who owns it (human, automation, or both)
5. When it's updated and by what process
6. The relationship to other configuration locations
7. How to validate changes to that configuration

### Format and Structure

```yaml
# Canonical Configuration Locations Registry
# Last Updated: 2026-03-26
# Purpose: Map all configuration locations and their purposes
# Agents should use this as their first reference when changing infrastructure

version: 1

infrastructure_state:
  # Source of truth for deployed infrastructure

  versions/stack.yaml:
    purpose: Canonical description of all deployed services and versions
    owner: human (manual, on successful deployment)
    format: YAML - service definitions with versions, ports, configuration
    use_for: Querying what services are deployed and their versions
    update_when: After successful deployment to production
    update_by: Agent or human completing a deployment workstream
    validation: |
      - Must be valid YAML
      - Every service must have name, vm, image, port fields
      - Versions must exist in respective registries
    related_files:
      - config/*: Service configuration files
      - docker/docker-compose.yml: Docker Compose reference
      - inventory/group_vars/all.yml: Common variables
    schema: |
      services:
        - service: service_name
          vm: vm_name
          image: image_name:version
          port: port_number
          data_volume: /path/to/volume (optional)
          config_source: config/service_name.yaml (optional)

  versions/image-versions.yaml:
    purpose: Pinned versions for all Docker images and binaries
    owner: automation (generated from builds)
    format: YAML - image: version pairs
    use_for: Building deployment manifests with specific image versions
    update_when: When a new image is built and tested
    update_by: Packer/Docker build pipeline
    validation: |
      - All images must be reachable and verified
      - Versions must follow semantic versioning

  receipts/:
    purpose: Operational audit trail of deployments and configuration changes
    owner: automation (generated on each successful operation)
    format: YAML receipt files with timestamp and change details
    use_for: Understanding what changed when and why
    update_when: After every deployment or major configuration change
    update_by: Deployment automation (Windmill, Ansible)
    validation: Manual - review receipts after each operation

versioning:
  # Metadata about versions and releases

  VERSION:
    purpose: Current repository version number
    owner: human (bumped on release)
    format: Plain text - semantic version number (e.g., "0.122.0")
    use_for: Tracking repository version and release boundaries
    update_when: When changes are merged to main
    update_by: Integration agent or human
    validation: Must be semantic version X.Y.Z
    related_files:
      - changelog.md: Release notes for this version
      - workstreams.yaml: Track what's merged in this version

  changelog.md:
    purpose: Human-readable changelog and release notes
    owner: human (curated)
    format: Markdown with version sections and change bullets
    use_for: Understanding what changed in each release
    update_when: When VERSION changes
    update_by: Integration agent or human
    validation: |
      - All changes should correspond to merged workstreams
      - Unreleased section stays at top until version is cut
    structure: |
      # Changelog
      ## Unreleased
      - Change 1
      - Change 2
      ## [0.122.0] - 2026-03-25
      - Change 3
      - Change 4

inventory:
  # Infrastructure topology and host definitions

  inventory/hosts.yml:
    purpose: Ansible inventory - define all hosts and groups
    owner: human (updated when hosts change)
    format: YAML - Ansible hosts and group definitions
    use_for: Defining which hosts exist and their relationships
    update_when: Adding/removing hosts or changing host groupings
    update_by: Infrastructure agent or human
    validation: Must be valid Ansible inventory format
    related_files:
      - inventory/group_vars/*.yml: Group-specific variables
      - inventory/host_vars/*/: Host-specific variables

  inventory/group_vars/all.yml:
    purpose: Common variables applied to all hosts
    owner: human and automation
    format: YAML - variable definitions
    use_for: Defining shared infrastructure settings
    update_when: Changing default behavior across hosts
    update_by: Agent or human
    validation: YAML syntax, referenced by playbooks
    coverage: All hosts share these variables

  inventory/group_vars/proxmox_host.yml:
    purpose: Variables specific to Proxmox host
    owner: human
    format: YAML
    use_for: Proxmox-specific configuration (networking, storage, firewall)
    update_when: Changing Proxmox host behavior
    update_by: Agent or human
    examples: |
      - pve_node_name: hostname for Proxmox
      - bridge configurations: vmbr0, vmbr10
      - firewall rules and policies

  inventory/group_vars/guests.yml:
    purpose: Variables for guest VMs
    owner: human
    format: YAML
    use_for: Default VM configuration (OS, network, packages)
    update_when: Changing default VM behavior
    examples: |
      - guest_os: debian or ubuntu
      - network_bridge: which bridge for each guest
      - cloud_init_template: base image to use

  inventory/host_vars/:
    purpose: Host-specific overrides to group variables
    owner: human
    format: YAML files named after hostname (e.g., nginx-vm.yml)
    use_for: Per-host customization
    update_when: A specific host needs different behavior
    structure: One file per host, overrides group_vars

automation:
  # Ansible playbooks, roles, and related automation

  playbooks/site.yml:
    purpose: Main site playbook - runs full host bootstrap
    owner: human (maintained)
    format: Ansible playbook YAML
    use_for: Complete host setup from Debian 13
    metadata_header: |
      Check lines 1-30 for Purpose, Inputs, Outputs, Dependencies
    runs_when: Fresh Debian 13 installed or full refresh needed
    validation: ansible-playbook --syntax-check

  playbooks/bootstrap.yml:
    purpose: Bootstrap playbook - initial SSH and base packages
    owner: human
    format: Ansible playbook YAML
    use_for: First-run access and security setup
    runs_when: Immediately after OS installation

  roles/:
    purpose: Reusable Ansible roles for specific concerns
    owner: human
    format: Ansible roles in collections/ansible_collections/lv3/platform/roles/
    metadata: Check meta/main.yml for each role
    examples: |
      - roles/proxmox_bootstrap: Install Proxmox VE
      - roles/security_baseline: Security hardening
      - roles/networking: Network interface configuration

service_configuration:
  # Configuration files for deployed services

  config/:
    purpose: Service configuration files for all deployed services
    owner: human (templated by Ansible)
    format: YAML, JSON, CONF - service-specific formats
    use_for: Service-level customization beyond environment defaults
    update_when: Changing service behavior
    update_by: Agent or human
    structure: One directory per service (e.g., config/gitea/, config/keycloak/)
    deployment: Copied to service at deploy time via Ansible

  docker/docker-compose.yml:
    purpose: Docker Compose reference for services running on docker-runtime-lv3
    owner: human (template)
    format: Docker Compose YAML
    use_for: Understanding service dependencies and networking
    update_when: Adding/removing services on Docker
    update_by: Agent or human
    validation: docker-compose config

project_tracking:
  # Workstream and project management

  workstreams.yaml:
    purpose: List of active workstreams and branch assignments
    owner: human and automation
    format: YAML - workstream definitions with branch, assignee, status
    use_for: Understanding parallel work and current projects
    update_when: Starting/completing a workstream
    update_by: Agent at start/end of branch work
    structure: |
      workstreams:
        - name: workstream-name
          branch: branch-name
          assignee: agent or human
          status: in-progress / blocked / complete
          adr_reference: docs/workstreams/adr-XXXX-workstream.md

  docs/workstreams/:
    purpose: ADR-style documentation for active workstreams
    owner: human and automation
    format: Markdown ADRs following ADR format
    use_for: Detailed workstream planning and decision records
    creation: Create when starting a workstream branch
    update_when: Work progresses or plans change
    structure: adr-XXXX-workstream-name.md

validation_and_ci:
  # Testing and validation configuration

  Makefile:
    purpose: Development and operational task runners
    owner: human (maintained)
    format: GNU Make
    use_for: Common tasks (validate, test, build, deploy)
    examples: |
      make validate-data-models
      make test
      make deploy
    validation: makefile syntax checker

  .github/workflows/:
    purpose: GitHub Actions workflows (legacy/mirror)
    owner: human (mirrors Gitea CI)
    format: GitHub Actions YAML
    use_for: Legacy external CI (now mirrored from Gitea)

  .gitea/workflows/:
    purpose: Gitea Actions workflows (primary CI)
    owner: human
    format: GitHub Actions-compatible YAML
    use_for: Local CI for validation and testing
    runs_on: self-hosted runner on docker-build-lv3
    validation: Gitea syntax checking

agent_quick_reference:
  "I need to find where X configuration lives":
    - Check .config-locations.yaml (this file)
    - Look in the section matching your concern
    - Read the "use_for" and "update_when" fields

  "I'm changing X - where should I document it":
    - For infrastructure changes: workstreams.yaml and docs/workstreams/
    - For service deployments: versions/stack.yaml
    - For version bumps: VERSION and changelog.md
    - For operational changes: receipts/

  "What's the source of truth for X":
    - Look in .config-locations.yaml for "owner" field
    - If "human", it's the primary source
    - If "automation", it's generated - modify the generator, not the file

  "How do I validate my changes":
    - See Makefile for validation tasks
    - See related_files in .config-locations.yaml for dependent files
    - Run: make validate-data-models

discovery_principles:
  - Single source of truth per configuration domain
  - Configuration is as close to point-of-use as practical
  - No duplication unless explicitly documented
  - "Owner" field indicates who maintains it (human or automation)
  - Related files show interdependencies
  - Validation methods documented for each location
