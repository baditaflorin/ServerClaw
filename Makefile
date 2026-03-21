REPO_ROOT := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
ANSIBLE_INVENTORY := $(REPO_ROOT)/inventory/hosts.yml
BOOTSTRAP_KEY ?= /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519

.PHONY: syntax-check syntax-check-monitoring install-proxmox configure-network configure-ingress configure-tailscale provision-guests harden-access harden-guest-access harden-security provision-api-access converge-monitoring

syntax-check:
	ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --syntax-check

syntax-check-monitoring:
	ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/monitoring-stack.yml --syntax-check

install-proxmox:
	ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY)

configure-network:
	ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags repository,network

configure-ingress:
	ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags ingress

configure-tailscale:
	ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags tailscale

provision-guests:
	ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags guests

harden-access:
	ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags access

harden-guest-access:
	ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/guest-access.yml --private-key $(BOOTSTRAP_KEY)

harden-security:
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags security

provision-api-access:
	ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags api-access

converge-monitoring:
	ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/monitoring-stack.yml --private-key $(BOOTSTRAP_KEY)
