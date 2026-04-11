# ServerClaw VM-as-Container base image
# Simulates what Ansible expects from a freshly provisioned Debian VM:
#   - SSH server on port 22
#   - ops user with passwordless sudo
#   - Python 3 for Ansible
#   - Docker for service convergence (DinD via socket bind-mount)
#
# IMPORTANT: Must use Debian (not Ubuntu) — playbooks assert
# ansible_distribution == "Debian". Production VMs run Debian Bookworm.
#
# See ADR 0387: ServerClaw-in-Docker

FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

# Core packages: SSH, sudo, Python (Ansible needs these)
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-server \
    sudo \
    python3 \
    python3-apt \
    python3-venv \
    python3-pip \
    ca-certificates \
    curl \
    gnupg \
    iproute2 \
    iputils-ping \
    net-tools \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Install Docker CLI (for Docker-in-Docker via socket mount)
RUN install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && chmod a+r /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
       > /etc/apt/sources.list.d/docker.list \
    && apt-get update && apt-get install -y --no-install-recommends \
       docker-ce-cli \
       docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

# Create ops user matching production access model
RUN useradd -m -s /bin/bash -G sudo ops \
    && echo "ops ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/ops \
    && chmod 0440 /etc/sudoers.d/ops \
    && mkdir -p /home/ops/.ssh \
    && chmod 700 /home/ops/.ssh \
    && chown -R ops:ops /home/ops/.ssh

# Prepare SSH server
RUN mkdir -p /run/sshd \
    && sed -i 's/#PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config \
    && sed -i 's/#PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config \
    && sed -i 's/#PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config \
    && echo "AcceptEnv LANG LC_*" >> /etc/ssh/sshd_config

# Healthcheck: SSH port responds
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=3 \
    CMD ssh-keyscan -T 2 127.0.0.1 2>/dev/null | grep -q ssh || exit 1

EXPOSE 22

# Entrypoint: inject authorized_keys if bind-mounted, start SSH
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
