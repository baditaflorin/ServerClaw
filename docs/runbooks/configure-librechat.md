# Configure LibreChat

## Overview

LibreChat provides the user-facing chat interface at `chat.example.com`, replacing Open WebUI.

## Deployment

```bash
make converge-librechat env=production
```

## Configuration

- System prompt preset: `config/serverclaw/system-prompt.md`
- OIDC auth: `config/llm-gateway/auth.yaml`
- LibreChat config rendered from `librechat.yaml.j2`

## Verification

```bash
curl -fsS https://chat.example.com  # Should redirect to Keycloak login
```

## Troubleshooting

- Check container logs: `ssh coolify docker logs librechat`
- Check MongoDB: `ssh coolify docker exec librechat-mongodb mongosh --eval "db.stats()"`
