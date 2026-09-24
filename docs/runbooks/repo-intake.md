# Repo Intake

Use this runbook to converge and verify the dedicated repo-intake runtime on
`docker-runtime`.

## Converge

The governed target checks the controller bootstrap key and Coolify API auth
artifact first. Run repository validation and the focused playbook syntax check
before applying:

```bash
make preflight WORKFLOW=converge-repo-intake
make validate
make syntax-check-repo-intake
make converge-repo-intake
```

## Local Verification

Verify the private listener on `docker-runtime`:

```bash
ansible -i "${PLATFORM_INVENTORY_OVERLAY:?select the deployment inventory}" docker-runtime \
  -m ansible.builtin.uri -a 'url=http://127.0.0.1:8101/health status_code=200'
ansible -i "${PLATFORM_INVENTORY_OVERLAY:?select the deployment inventory}" docker-runtime \
  -m ansible.builtin.uri -a 'url=http://127.0.0.1:8101/ status_code=200 return_content=true'
```

## Public Verification

Verify the shared-edge publication still reaches the runtime through the auth
boundary:

```bash
curl -I https://repo-intake.example.com/
```

Expected result: an auth-boundary response such as `302` or a successful
authenticated page render, depending on the current browser/session context.

## Notes

- The private repo-intake listener uses `8101` on `docker-runtime`.
- `8096` remains reserved for the live browser-runner and other legacy runtime
  consumers, so repo-intake must not reuse it.
- The runtime image is built locally from the repo snapshot and mirrored
  controller secrets; a replay that reaches `repo_intake_runtime` should not
  depend on an external image registry.
