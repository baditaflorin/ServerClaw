# Release 0.122.0

- Date: 2026-03-25

## Summary
- implemented ADR 0143 with a private Gitea service on `docker-runtime-lv3`, Keycloak OIDC login, and a managed PostgreSQL backend
- added the self-hosted Gitea Actions runner on `docker-build-lv3` plus the repo-managed `.gitea/workflows/validate.yml` workflow
- verified live repository creation, push-triggered webhook delivery, and successful workflow execution against the self-hosted Gitea control plane

## Platform Impact
- verified mainline live apply for ADR 0143 private Gitea rollout; platform_version advanced to 0.106.0

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
