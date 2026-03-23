FROM aquasec/trivy:0.68.2 AS trivy_source

FROM debian:12-slim@sha256:8af0e5095f9964007f5ebd11191dfe52dcb51bf3afa2c07f055fc5451b78ba0e

ENV DEBIAN_FRONTEND=noninteractive
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV VIRTUAL_ENV=/opt/check-runner
ENV PATH=/opt/check-runner/bin:${PATH}
ARG TARGETARCH
ARG GITLEAKS_VERSION=8.28.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
        python3 \
        python3-pip \
        python3-venv \
        tar \
    && rm -rf /var/lib/apt/lists/*

COPY --from=trivy_source /usr/local/bin/trivy /usr/local/bin/trivy

RUN case "${TARGETARCH}" in \
        amd64) arch="x64" ;; \
        arm64) arch="arm64" ;; \
        *) echo "unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
    esac \
    && curl -fsSL -o /tmp/gitleaks.tar.gz \
        "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_${arch}.tar.gz" \
    && tar -xzf /tmp/gitleaks.tar.gz -C /tmp gitleaks \
    && install -m 0755 /tmp/gitleaks /usr/local/bin/gitleaks \
    && rm -f /tmp/gitleaks.tar.gz /tmp/gitleaks

COPY .tool-versions /tmp/.tool-versions

RUN python3 -m venv "${VIRTUAL_ENV}" \
    && pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir checkov==3.2.469 \
    && trivy --download-db-only --cache-dir /var/lib/trivy >/dev/null

WORKDIR /workspace

CMD ["bash"]
