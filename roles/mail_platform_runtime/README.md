# mail_platform_runtime

Runs the LV3 mail platform on the Docker runtime VM through a managed Compose file.

Inputs: mail hostnames, mailbox identities, notification-profile definitions, Brevo fallback sender settings, controller-local fallback API key, OTLP trace endpoint settings, and managed secret paths.
Outputs: a running Stalwart container, a local mail gateway API, bootstrap-managed mail principals, profile-scoped sender credentials, mirrored local admin credentials, and OpenTelemetry traces for mail-gateway requests.
