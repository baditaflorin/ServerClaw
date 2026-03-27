# guest_observability

Provides shared guest-local observability plumbing for Telegraf-based service telemetry.

Inputs: guest writer token paths, Influx repository settings, Telegraf package settings, service identity, and managed directories.
Outputs: Telegraf installed on the guest, the mirrored guest-writer token, and a consistent verification path for service roles.
