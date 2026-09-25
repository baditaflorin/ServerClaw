# Repo Intake

Use this runbook to converge and verify the dedicated repo-intake runtime on
`docker-runtime`.

## Converge

```bash
make converge-repo-intake
```

## Local Verification

Verify the private listener on `docker-runtime`:

```bash
ssh -J ops@100.64.0.1 ops@10.10.10.20 'curl -fsS http://127.0.0.1:8101/health'
ssh -J ops@100.64.0.1 ops@10.10.10.20 'curl -fsS http://127.0.0.1:8101/ | grep -q "Repo Intake"'
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
