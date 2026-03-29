# harbor_runtime

Deploys Harbor on `docker-runtime-lv3` using the upstream online installer, publishes it behind the shared edge at `registry.lv3.org`, and bootstraps repo-managed operator and automation artifacts.

Managed surfaces:

- Harbor installer tree under `/opt/harbor/installer`
- Harbor data, logs, and generated compose stack under `/opt/harbor/data`
- generated admin and internal database passwords under `/etc/lv3/harbor/`
- mirrored local recovery material under `.local/harbor/`
- repo-managed Keycloak client and admin group for Harbor OIDC
- Harbor project bootstrap for check-runner image publication
