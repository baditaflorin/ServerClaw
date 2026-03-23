FROM aquasec/trivy:0.68.2 AS trivy_source

FROM debian:12-slim@sha256:8af0e5095f9964007f5ebd11191dfe52dcb51bf3afa2c07f055fc5451b78ba0e

ENV DEBIAN_FRONTEND=noninteractive
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV VIRTUAL_ENV=/opt/check-runner
ENV PATH=/opt/check-runner/bin:${PATH}
ARG TARGETARCH
ARG OPENTOFU_VERSION=1.10.6
ARG PACKER_VERSION=1.13.1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
        jq \
        python3 \
        python3-pip \
        python3-venv \
        tar \
        unzip \
    && rm -rf /var/lib/apt/lists/*

RUN case "${TARGETARCH}" in \
        amd64) arch="amd64" ;; \
        arm64) arch="arm64" ;; \
        *) echo "unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
    esac \
    && curl -fsSL -o /tmp/tofu.zip \
        "https://github.com/opentofu/opentofu/releases/download/v${OPENTOFU_VERSION}/tofu_${OPENTOFU_VERSION}_linux_${arch}.zip" \
    && unzip /tmp/tofu.zip -d /usr/local/bin \
    && rm -f /tmp/tofu.zip

RUN case "${TARGETARCH}" in \
        amd64) arch="amd64" ;; \
        arm64) arch="arm64" ;; \
        *) echo "unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
    esac \
    && curl -fsSL -o /tmp/packer.zip \
        "https://releases.hashicorp.com/packer/${PACKER_VERSION}/packer_${PACKER_VERSION}_linux_${arch}.zip" \
    && unzip /tmp/packer.zip -d /usr/local/bin \
    && rm -f /tmp/packer.zip

COPY --from=trivy_source /usr/local/bin/trivy /usr/local/bin/trivy

COPY .tool-versions /tmp/.tool-versions

RUN python3 -m venv "${VIRTUAL_ENV}" \
    && pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir \
        jsonschema==4.25.1 \
        yamllint==1.37.1

WORKDIR /workspace

CMD ["bash"]
