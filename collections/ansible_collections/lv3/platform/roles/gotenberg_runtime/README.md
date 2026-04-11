# gotenberg_runtime

Converges the private Gotenberg runtime on `docker-runtime`.

The role renders a Docker Compose stack, pulls the pinned image from
`config/image-catalog.json`, starts the service on the private guest network,
and verifies both Chromium and LibreOffice PDF conversion paths.
