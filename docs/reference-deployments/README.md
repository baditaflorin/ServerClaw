# Reference Deployments

This directory defines the public reference tier for fresh forks.

It sits between the root onboarding entrypoints and the integrated live
deployment truth:

- root entrypoints explain how the repo is organized
- reference deployment samples show how to start with replaceable values
- integrated live truth remains in the real inventory, versions stack, receipts,
  and workstream history

Use these surfaces first when adapting the repo to a new environment:

- [inventory/examples/reference-platform/README.md](../../inventory/examples/reference-platform/README.md)
- [config/examples/reference-provider-profile.yaml](../../config/examples/reference-provider-profile.yaml)
- [config/examples/reference-publication-profile.json](../../config/examples/reference-publication-profile.json)
- [config/examples/reference-controller-local-secrets.json](../../config/examples/reference-controller-local-secrets.json)
- [docs/runbooks/fork-reference-platform.md](../runbooks/fork-reference-platform.md)

Keep deployment-specific domains, addresses, provider accounts, and secret files
in your fork-local inventory and `.local/` overlay state rather than pushing
them back into these public sample surfaces.
