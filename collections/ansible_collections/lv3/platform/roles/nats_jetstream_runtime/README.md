# nats_jetstream_runtime

Deploys the private NATS JetStream runtime on `docker-runtime`, renders the
repo-managed server config and compose stack under `/opt/nats-jetstream`, keeps
the controller-local `jetstream-admin` password authoritative, preserves the
additional service principals already in use on the live runtime, and verifies
the loopback monitoring endpoint after every converge.
