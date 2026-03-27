# step_ca_runtime

Deploys a private `step-ca` instance on `docker-runtime-lv3`, mirrors the bootstrap artifacts to the controller, and verifies SSH and X.509 issuance surfaces.

Inputs: step-ca image and CLI versions, private CA URLs, local artifact paths, and the service topology values that identify the runtime and Tailscale proxy endpoint.
Outputs: a running Compose-managed CA under `/opt/step-ca`, controller-local bootstrap and provisioner artifacts under `.local/step-ca/`, and verified SSH/X.509 issuance primitives for later workflows.
