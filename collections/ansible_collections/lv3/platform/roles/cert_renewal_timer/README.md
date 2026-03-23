# cert_renewal_timer

Render a managed renewal script plus systemd service and timer units for certificate rotation jobs that should run on a host schedule.

Inputs: a base unit name, the rendered output paths, the renewal command, and an optional reload command to execute after the certificate changes.

Outputs: a shell script under `/usr/local/libexec`, a matching oneshot systemd service, and a persistent timer enabled on the target host.
