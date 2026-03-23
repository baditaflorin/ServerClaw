# Configure @@DISPLAY_NAME@@

This runbook starts from the ADR 0078 scaffold for @@DISPLAY_NAME@@.

## Generated Surfaces

- role: [@@ROLE_PATH@@](@@ABS_REPO_ROOT@@/@@ROLE_PATH@@)
- playbook: [@@PLAYBOOK_PATH@@](@@ABS_REPO_ROOT@@/@@PLAYBOOK_PATH@@)
- service entry point: [@@SERVICE_PLAYBOOK_PATH@@](@@ABS_REPO_ROOT@@/@@SERVICE_PLAYBOOK_PATH@@)

## Required Follow-Up

1. Replace every scaffold TODO marker in the generated catalogs, ADR, workstream doc, and role.
2. Pin the requested runtime image: `make pin-image IMAGE=@@REQUESTED_IMAGE@@`
3. Confirm the health endpoint, exposed ports, and OpenBao runtime-secret payload for the real service.
4. Run `make validate` before merging.

## Notes

- requested image: `@@REQUESTED_IMAGE@@`
- initial internal URL: `@@PRIVATE_URL@@`
