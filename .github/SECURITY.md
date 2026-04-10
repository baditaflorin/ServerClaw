# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it
responsibly. **Do not open a public issue.**

Email: **baditaflorin@gmail.com**

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

## Response Timeline

- **Acknowledgement**: within 48 hours
- **Initial assessment**: within 7 days
- **Fix or mitigation**: depends on severity, typically within 30 days

## Scope

This policy covers the infrastructure-as-code in this repository, including:
- Ansible roles and playbooks
- Docker Compose templates
- Scripts and automation tools
- Configuration templates

Vulnerabilities in upstream software (Keycloak, PostgreSQL, Nginx, etc.)
should be reported to their respective projects.

## Secrets

This repository is designed to keep all secrets in `.local/` (gitignored).
If you find a committed secret or credential, please report it immediately.
