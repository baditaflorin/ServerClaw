# temporal_runtime

Deploys the private Temporal runtime on `docker-runtime-lv3`, renders the
repo-managed compose stack and per-service config templates under
`/opt/temporal`, injects the PostgreSQL password through the OpenBao compose
env helper, bootstraps the default `lv3` namespace through the official
admin-tools image, and keeps the diagnostic UI plus gRPC frontend loopback-only
for operator access via SSH tunneling.
