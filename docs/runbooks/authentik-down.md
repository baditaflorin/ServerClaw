# Runbook: Authentik Down

## Severity

critical

## Alert condition

`probe_success{service="authentik",probe_kind="readiness"} == 0`

## Immediate steps

1. Confirm the public readiness path is failing from `monitoring`, not only from
   the operator workstation:

   ```bash
   curl --fail --silent --show-error https://id.example.com/-/health/ready/ >/dev/null
   ```

2. On `runtime-control`, inspect the managed stack without printing its
   environment or credentials:

   ```bash
   sudo docker compose --file /opt/authentik/docker-compose.yml ps
   sudo docker compose --file /opt/authentik/docker-compose.yml logs --tail 100 --no-color authentik worker
   curl --fail --silent --show-error http://127.0.0.1:9010/-/health/ready/ >/dev/null
   ```

3. Check the most recent mutation evidence for `authentik`, OpenBao secret
   rendering, PostgreSQL reachability, and shared-edge publication.

## Diagnosis

- Distinguish a local Authentik failure from DNS, NGINX, or TLS publication
  drift by comparing the local readiness request with the public one.
- Check that the Authentik server and worker containers are both healthy before
  changing dependent clients.
- Check OpenBao agent-render metadata and PostgreSQL connectivity; never print
  rendered runtime environments or tokens.
- If only a relying party is failing, use that service's runbook. Do not
  restart the identity provider to repair an application-local callback error.

## Resolution

1. Replay the governed workflow first:

   ```bash
   make live-apply-service service=authentik env=production ALLOW_IN_PLACE_MUTATION=true
   ```

2. Restart the Authentik compose stack only when the failure is confirmed and
   the current maintenance policy permits it.
3. If the stack does not become healthy, preserve non-secret logs and metadata,
   then investigate the declared OpenBao and PostgreSQL dependencies before
   attempting another replay.
4. If the local stack is healthy but the public endpoint fails, validate NGINX
   publication, upstream routing, and the active certificate lineage rather
   than restarting Authentik.

## Escalation

If Authentik remains unavailable after 15 minutes, treat the event as a shared
authentication outage and stop unrelated control-plane changes until recovery
is verified.

## Post-incident

Record the root cause, duration, any governed replay or manual restart, and
the non-secret recovery evidence in the mutation audit log and incident notes.
