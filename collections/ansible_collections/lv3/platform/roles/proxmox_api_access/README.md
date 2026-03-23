# proxmox_api_access

Creates and verifies the durable Proxmox API automation identity and token.

Inputs: API hostname, automation user metadata, token ACL settings, and local token storage paths.
Outputs: a working API token persisted only on the controller and verified against the live API.
