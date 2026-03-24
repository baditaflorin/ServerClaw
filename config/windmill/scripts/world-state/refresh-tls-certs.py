from platform.world_state.workers import run_worker


def main(
    repo_path: str = "/srv/proxmox_florin_server",
    dsn: str | None = None,
    publish_nats: bool = True,
):
    return run_worker("tls_cert_expiry", repo_path=repo_path, dsn=dsn, publish_nats=publish_nats)
