# Purpose: Build the pinned MinIO source with a patched Go runtime and gRPC dependency.
# The runtime is UBI Micro, so invoke MinIO directly rather than relying on a shell.
ARG GO_IMAGE=golang:1.25.7-trixie@sha256:2b174ffcf56c7ad0c47d30d2630693265639ddf2a5141149c2da34db921791b4
FROM ${GO_IMAGE} AS build

ARG MINIO_VERSION=2025-10-15T17-29-55Z
ARG MINIO_COMMIT
ENV CGO_ENABLED=0
WORKDIR /src
COPY . .
RUN GOTOOLCHAIN=local go get google.golang.org/grpc@v1.79.3 && \
    GOTOOLCHAIN=local go mod tidy -compat=1.24 && \
    GOTOOLCHAIN=local go test ./cmd/... && \
    short_commit="$(printf '%.12s' "${MINIO_COMMIT}")" && \
    GOTOOLCHAIN=local go build -tags kqueue -trimpath \
      --ldflags "-s -w -X github.com/minio/minio/cmd.Version=${MINIO_VERSION} -X github.com/minio/minio/cmd.CopyrightYear=2025 -X github.com/minio/minio/cmd.ReleaseTag=RELEASE.${MINIO_VERSION} -X github.com/minio/minio/cmd.CommitID=${MINIO_COMMIT} -X github.com/minio/minio/cmd.ShortCommitID=${short_commit}" \
      -o /out/minio .

FROM registry.access.redhat.com/ubi9/ubi-micro@sha256:ff30602252a3e92706585c7c34cd3c74028eaac4ab815e6b19f8b27562bdd7e3

ARG MINIO_VERSION=2025-10-15T17-29-55Z
ARG MINIO_COMMIT
LABEL org.opencontainers.image.source="https://github.com/minio/minio" \
      org.opencontainers.image.version="RELEASE.${MINIO_VERSION}-patched" \
      org.opencontainers.image.revision="${MINIO_COMMIT}" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later"

COPY --from=build /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
COPY --from=build --chmod=0755 /out/minio /usr/bin/minio
COPY --from=build /src/LICENSE /licenses/LICENSE
COPY --from=build /src/CREDITS /licenses/CREDITS

ENV HOME=/tmp

USER 10001:10001


EXPOSE 9000
VOLUME ["/data"]
ENTRYPOINT ["/usr/bin/minio"]
CMD ["server", "/data"]
