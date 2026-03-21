ANSIBLE_INVENTORY := /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/hosts.yml
BOOTSTRAP_KEY := /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519

.PHONY: syntax-check install-proxmox configure-network provision-guests harden-access harden-guest-access

syntax-check:
	ansible-playbook -i $(ANSIBLE_INVENTORY) /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/site.yml --syntax-check

install-proxmox:
	ansible-playbook -i $(ANSIBLE_INVENTORY) /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/site.yml --private-key $(BOOTSTRAP_KEY)

configure-network:
	ansible-playbook -i $(ANSIBLE_INVENTORY) /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags repository,network

provision-guests:
	ansible-playbook -i $(ANSIBLE_INVENTORY) /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags guests

harden-access:
	ansible-playbook -i $(ANSIBLE_INVENTORY) /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags access

harden-guest-access:
	ansible-playbook -i $(ANSIBLE_INVENTORY) /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/guest-access.yml --private-key $(BOOTSTRAP_KEY)
