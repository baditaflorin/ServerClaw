REPO_ROOT := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
ANSIBLE_INVENTORY := $(REPO_ROOT)/inventory/hosts.yml
BOOTSTRAP_KEY ?= /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519
ANSIBLE_LOCAL_TEMP ?= /tmp/proxmox_florin_server-ansible-local
ANSIBLE_REMOTE_TEMP ?= /tmp
ANSIBLE_ENV := ANSIBLE_LOCAL_TEMP=$(ANSIBLE_LOCAL_TEMP) ANSIBLE_REMOTE_TEMP=$(ANSIBLE_REMOTE_TEMP)
UPTIME_KUMA_PYTHON ?= $(REPO_ROOT)/.local/uptime-kuma/client-venv/bin/python
ACTION ?= list-monitors
UPTIME_KUMA_ARGS ?=
RECEIPT ?=
COMMAND ?=
SERVICE ?=

.PHONY: validate validate-ansible-syntax validate-yaml validate-ansible-lint validate-shell validate-json validate-data-models generate-status-docs generate-status generate-ops-portal deploy-ops-portal validate-generated-docs validate-generated-portals receipts receipt-info workflows workflow-info commands command-info lanes lane-info preflight syntax-check syntax-check-monitoring syntax-check-docker-runtime syntax-check-backup-vm syntax-check-uptime-kuma syntax-check-mail-platform syntax-check-openbao syntax-check-step-ca syntax-check-windmill install-proxmox configure-network configure-ingress configure-edge-publication configure-tailscale provision-guests harden-access harden-guest-access harden-security provision-api-access converge-monitoring converge-docker-runtime converge-postgres-vm converge-mail-platform converge-openbao converge-step-ca converge-windmill deploy-uptime-kuma uptime-kuma-manage configure-backups configure-backup-vm database-dns show-service export-mcp-tools start-workstream

validate:
	$(REPO_ROOT)/scripts/validate_repo.sh

validate-ansible-syntax:
	$(REPO_ROOT)/scripts/validate_repo.sh ansible-syntax

validate-yaml:
	$(REPO_ROOT)/scripts/validate_repo.sh yaml

validate-ansible-lint:
	$(REPO_ROOT)/scripts/validate_repo.sh ansible-lint

validate-shell:
	$(REPO_ROOT)/scripts/validate_repo.sh shell

validate-json:
	$(REPO_ROOT)/scripts/validate_repo.sh json

validate-data-models:
	$(REPO_ROOT)/scripts/validate_repo.sh data-models

generate-status-docs:
	uvx --from pyyaml python $(REPO_ROOT)/scripts/generate_status_docs.py --write

generate-ops-portal:
	uvx --from pyyaml python $(REPO_ROOT)/scripts/generate_ops_portal.py --write

deploy-ops-portal: generate-ops-portal
	$(MAKE) configure-edge-publication

generate-status: generate-status-docs generate-ops-portal

validate-generated-docs:
	uvx --from pyyaml python $(REPO_ROOT)/scripts/generate_status_docs.py --check

validate-generated-portals:
	uvx --from pyyaml python $(REPO_ROOT)/scripts/generate_ops_portal.py --check

receipts:
	$(REPO_ROOT)/scripts/live_apply_receipts.py --list

receipt-info:
	@test -n "$(RECEIPT)" || (echo "set RECEIPT=<receipt-id>"; exit 1)
	$(REPO_ROOT)/scripts/live_apply_receipts.py --receipt $(RECEIPT)

workflows:
	$(REPO_ROOT)/scripts/workflow_catalog.py --list

workflow-info:
	@test -n "$(WORKFLOW)" || (echo "set WORKFLOW=<workflow-id>"; exit 1)
	$(REPO_ROOT)/scripts/workflow_catalog.py --workflow $(WORKFLOW)

commands:
	$(REPO_ROOT)/scripts/command_catalog.py --list

command-info:
	@test -n "$(COMMAND)" || (echo "set COMMAND=<command-id>"; exit 1)
	$(REPO_ROOT)/scripts/command_catalog.py --command $(COMMAND)

show-service:
	@test -n "$(SERVICE)" || (echo "set SERVICE=<service-id>"; exit 1)
	uvx --from pyyaml python $(REPO_ROOT)/scripts/service_catalog.py --service $(SERVICE)

export-mcp-tools:
	python3 $(REPO_ROOT)/scripts/agent_tool_registry.py --export-mcp

lanes:
	uvx --from pyyaml python $(REPO_ROOT)/scripts/control_plane_lanes.py --list

lane-info:
	@test -n "$(LANE)" || (echo "set LANE=<command|api|message|event>"; exit 1)
	uvx --from pyyaml python $(REPO_ROOT)/scripts/control_plane_lanes.py --lane $(LANE)

preflight:
	@if [ -z "$(WORKFLOW)" ]; then \
		$(REPO_ROOT)/scripts/preflight_controller_local.py --list; \
		echo "set WORKFLOW=<workflow-id>"; \
		exit 0; \
	else \
		$(REPO_ROOT)/scripts/preflight_controller_local.py --workflow $(WORKFLOW); \
	fi

syntax-check:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --syntax-check

syntax-check-monitoring:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/monitoring-stack.yml --syntax-check

syntax-check-docker-runtime:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/docker-runtime.yml --syntax-check

syntax-check-backup-vm:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/backup-vm.yml --syntax-check

syntax-check-uptime-kuma:
	ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/uptime-kuma.yml --syntax-check

syntax-check-mail-platform:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/mail-platform.yml --syntax-check

syntax-check-openbao:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/openbao.yml --syntax-check

syntax-check-step-ca:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/step-ca.yml --syntax-check

syntax-check-windmill:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/windmill.yml --syntax-check

install-proxmox:
	$(MAKE) preflight WORKFLOW=install-proxmox
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY)

configure-network:
	$(MAKE) preflight WORKFLOW=configure-network
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags repository,network

configure-ingress:
	$(MAKE) preflight WORKFLOW=configure-ingress
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags ingress

configure-edge-publication:
	$(MAKE) preflight WORKFLOW=configure-edge-publication
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/public-edge.yml --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

configure-tailscale:
	$(MAKE) preflight WORKFLOW=configure-tailscale
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags tailscale

provision-guests:
	$(MAKE) preflight WORKFLOW=provision-guests
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags guests

harden-access:
	$(MAKE) preflight WORKFLOW=harden-access
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags access

harden-guest-access:
	$(MAKE) preflight WORKFLOW=harden-guest-access
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/guest-access.yml --private-key $(BOOTSTRAP_KEY)

harden-security:
	$(MAKE) preflight WORKFLOW=harden-security
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} $(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags security

provision-api-access:
	$(MAKE) preflight WORKFLOW=provision-api-access
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags api-access

converge-monitoring:
	$(MAKE) preflight WORKFLOW=converge-monitoring
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/monitoring-stack.yml --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-docker-runtime:
	$(MAKE) preflight WORKFLOW=converge-docker-runtime
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/docker-runtime.yml --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-postgres-vm:
	$(MAKE) preflight WORKFLOW=converge-postgres-vm
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/postgres-vm.yml --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-mail-platform:
	$(MAKE) preflight WORKFLOW=converge-mail-platform
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/mail-platform.yml --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-openbao:
	$(MAKE) preflight WORKFLOW=converge-openbao
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/openbao.yml --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-step-ca:
	$(MAKE) preflight WORKFLOW=converge-step-ca
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/step-ca.yml --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-windmill:
	$(MAKE) preflight WORKFLOW=converge-windmill
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/windmill.yml --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

deploy-uptime-kuma:
	$(MAKE) preflight WORKFLOW=deploy-uptime-kuma
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/uptime-kuma.yml --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

uptime-kuma-manage:
	$(MAKE) preflight WORKFLOW=uptime-kuma-manage
	@test -n "$(ACTION)" || (echo "set ACTION=<bootstrap|ensure-monitors|list-monitors>"; exit 1)
	$(UPTIME_KUMA_PYTHON) $(REPO_ROOT)/scripts/uptime_kuma_tool.py $(ACTION) $(UPTIME_KUMA_ARGS)

configure-backups:
	$(MAKE) preflight WORKFLOW=configure-backups
	PROXMOX_BACKUP_CIFS_SERVER=$${PROXMOX_BACKUP_CIFS_SERVER:?set PROXMOX_BACKUP_CIFS_SERVER} \
	PROXMOX_BACKUP_CIFS_SHARE=$${PROXMOX_BACKUP_CIFS_SHARE:?set PROXMOX_BACKUP_CIFS_SHARE} \
	PROXMOX_BACKUP_CIFS_USERNAME=$${PROXMOX_BACKUP_CIFS_USERNAME:?set PROXMOX_BACKUP_CIFS_USERNAME} \
	PROXMOX_BACKUP_CIFS_PASSWORD=$${PROXMOX_BACKUP_CIFS_PASSWORD:?set PROXMOX_BACKUP_CIFS_PASSWORD} \
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags storage,backups

configure-backup-vm:
	$(MAKE) preflight WORKFLOW=configure-backup-vm
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/backup-vm.yml --private-key $(BOOTSTRAP_KEY)

database-dns:
	$(MAKE) preflight WORKFLOW=database-dns
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/database-dns.yml

start-workstream:
	@test -n "$(WORKSTREAM)" || (echo "set WORKSTREAM=<workstream-id>"; exit 1)
	$(REPO_ROOT)/scripts/create-workstream.sh $(WORKSTREAM)
