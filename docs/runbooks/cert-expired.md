# Certificate Expired

## Purpose

This runbook recovers a certificate-managed endpoint when the automated renewal path fails or a certificate has already expired.

The certificate inventory for the platform lives in [config/certificate-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server-certificate-lifecycle/config/certificate-catalog.json).

## OpenBao Emergency Rotation

Use this when `openbao-proxy` is expired or close enough to expiry that the scheduled timer no longer has time to recover cleanly.

1. SSH to `docker-runtime` as `ops`.
2. Reissue the certificate from step-ca.

```bash
sudo step ca certificate \
  --force \
  --provisioner services \
  --provisioner-password-file /opt/step-ca/secrets/services-password.txt \
  --ca-url https://10.10.10.20:9000 \
  --root /opt/step-ca/home/certs/root_ca.crt \
  --san 10.10.10.20 \
  --san 100.118.189.95 \
  --not-after 24h \
  100.118.189.95 \
  /opt/openbao/tls/server.crt \
  /opt/openbao/tls/server.key
```

3. Restore file permissions and restart only the OpenBao container.

```bash
sudo chown 100:1000 /opt/openbao/tls/server.crt /opt/openbao/tls/server.key
sudo chmod 0644 /opt/openbao/tls/server.crt
sudo chmod 0600 /opt/openbao/tls/server.key
sudo docker compose --file /opt/openbao/docker-compose.yml restart openbao
```

4. Confirm the endpoint presents a healthy certificate.

```bash
python3 scripts/tls_cert_probe.py --certificate-id openbao-proxy --fail-on warning
```

## Edge Certificate Validation

For certificates renewed by Certbot or Proxmox ACME, validate the endpoint directly from the repo workspace:

```bash
python3 scripts/tls_cert_probe.py --certificate-id grafana-edge
python3 scripts/tls_cert_probe.py --certificate-id proxmox-ui
```

If the probe still fails after renewal, treat it as a service publication issue rather than a certificate-issuance issue and move into the relevant service runbook.
