# Purpose: Install the supported NGINX.org stable package and modules on managed Debian edge hosts.
# Use case: Remediate vendor NGINX packages that have not received these CVE fixes.
# Inputs: Debian release facts; optional NGINX Perl module use detected from the active config.
# Outputs: NGINX 1.30.7 stable, signed package source, matching module ABI, and validated config.
# Idempotency: Yes; packages, source, pin, and module load config converge to declared state.
# Dependencies: Debian/Ubuntu apt, gpg, ca-certificates, systemd; NGINX official signing key.

The role keeps the distribution NGINX configuration files in place during the
package migration. It uses the signed NGINX.org stable repository, verifies the
repository key fingerprint, installs the matching Perl module only when the
active config uses it, removes the obsolete Debian stream module loader (the
official binary includes stream support), validates `nginx -t`, and restarts
the service.
