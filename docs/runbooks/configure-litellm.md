# Configure LiteLLM Proxy

## Overview

LiteLLM Proxy provides an OpenAI-compatible API gateway on `docker-runtime:4000`, replacing One API.

## Deployment

```bash
make converge-litellm env=production
```

## Configuration

Model routing is defined in `config/llm-gateway/model-catalog.yaml` and rendered to `litellm-config.yaml.j2`.

Consumer API keys are bootstrapped via:
```bash
python scripts/litellm_bootstrap.py \
  --base-url http://10.10.10.20:4000 \
  --master-key-file .local/litellm/master-key.txt
```

## Verification

```bash
curl -fsS http://100.64.0.1:4000/health/liveliness
curl -fsS -H "Authorization: Bearer $(cat .local/litellm/master-key.txt)" http://100.64.0.1:4000/v1/models
```

## Troubleshooting

- Check container logs: `ssh docker-runtime docker logs litellm`
- Check PostgreSQL: `ssh postgres-vm sudo -u postgres psql -d litellm -c '\dt'`
