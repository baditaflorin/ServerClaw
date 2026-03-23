# cert_renewer_sidecar

Render a reusable Compose service fragment for TLS-terminating containers that renew their own step-ca-issued certificates.

The current platform topology does not yet attach this helper to the HTTP-only control-plane stacks on `main`; it exists so future TLS-owning Compose services can adopt the same governed shape instead of inventing their own renewal container.
