#!/usr/bin/env bash
set -e

# Inject authorized_keys from bind-mounted public key
PUBKEY_PATH="/run/secrets/bootstrap_pubkey"
if [ -f "$PUBKEY_PATH" ]; then
    cp "$PUBKEY_PATH" /home/ops/.ssh/authorized_keys
    chmod 600 /home/ops/.ssh/authorized_keys
    chown ops:ops /home/ops/.ssh/authorized_keys
fi

# Also support direct mount to authorized_keys location
if [ -f /home/ops/.ssh/authorized_keys ]; then
    chmod 600 /home/ops/.ssh/authorized_keys
    chown ops:ops /home/ops/.ssh/authorized_keys
fi

# Create /run/sshd (tmpfs mount clears it on start)
mkdir -p /run/sshd

# Generate SSH host keys if missing (first boot)
ssh-keygen -A 2>/dev/null || true

# If Docker socket is bind-mounted, ensure ops can use it
if [ -S /var/run/docker.sock ]; then
    DOCKER_GID=$(stat -c '%g' /var/run/docker.sock 2>/dev/null || stat -f '%g' /var/run/docker.sock 2>/dev/null)
    if [ -n "$DOCKER_GID" ] && [ "$DOCKER_GID" != "0" ]; then
        groupadd -g "$DOCKER_GID" dockerhost 2>/dev/null || true
        usermod -aG dockerhost ops 2>/dev/null || true
    fi
    usermod -aG root ops 2>/dev/null || true
fi

echo "Starting SSH server..."
exec /usr/sbin/sshd -D -e
