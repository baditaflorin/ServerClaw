# nats_jetstream_runtime

Deploys the private NATS JetStream runtime on `docker-runtime-lv3`, renders the
repo-managed server config and compose stack under `/opt/nats-jetstream`, keeps
the controller-local `jetstream-admin` password authoritative, and verifies the
loopback monitoring endpoint after every converge.
