# Inversion of Control — Value Flow Architecture

> **ADR 0407 / 0409** — How deployment-specific values flow from `.local/identity.yml`
> into the running system. Committed code is fully generic (`example.com`).

## 1. End-to-End Value Flow

```mermaid
graph TB
    subgraph BOOTSTRAP["Bootstrap (one-time)"]
        INIT["make init-local<br/>init_local_overlay.py"]
        EDIT["Operator edits<br/>.local/identity.yml<br/>(8 values)"]
        INIT -->|"creates scaffold +<br/>auto-generates 237 secrets"| LOCAL
        EDIT -->|"fills in real values"| IDENTITY
    end

    subgraph LOCAL[".local/ (gitignored)"]
        IDENTITY[".local/identity.yml<br/>─────────────<br/>platform_domain: your.domain<br/>management_ipv4: YOUR.IP<br/>platform_operator_email: you@..."]
        SECRETS[".local/ssh/ .local/keycloak/ ...<br/>SSH keys, API tokens, passwords"]
    end

    subgraph COMMITTED["Committed Code (generic)"]
        COMMITTED_ID["identity.yml<br/>platform_domain: example.com"]
        HOST_VARS["host_vars/proxmox-host.yml<br/>management_ipv4: 203.0.113.1"]
        CATALOGS["config/*.json catalogs<br/>(all use example.com)"]
        ROLES["Ansible role templates<br/>uses Jinja2 variables"]
    end

    subgraph GENERATORS["Generator Scripts (build-time)"]
        GEN_PLATFORM["generate_platform_vars.py"]
        GEN_TLS["generate_https_tls_assurance.py"]
        GEN_SLO["generate_slo_rules.py"]
        GEN_HAIRPIN["generate_cross_cutting_artifacts.py"]
        GEN_UPTIME["uptime_contract.py"]
    end

    subgraph GENERATED["Generated Files (gitignored)"]
        PLATFORM_YML["platform.yml"]
        PROM_FILES["Prometheus targets + rules"]
        HAIRPIN_YML["platform_hairpin.yml"]
        UPTIME_JSON["monitors.json"]
    end

    subgraph RUNTIME["Ansible Runtime"]
        SCOPE["ansible_scope_runner.py<br/>_resolve_identity_override()"]
        ANSIBLE["ansible-playbook<br/>-e @.local/identity.yml"]
        DEPLOYED["Deployed Services<br/>(real domain, real IPs)"]
    end

    COMMITTED_ID --> GEN_PLATFORM
    HOST_VARS --> GEN_PLATFORM
    CATALOGS --> GEN_TLS
    CATALOGS --> GEN_SLO
    CATALOGS --> GEN_HAIRPIN
    CATALOGS --> GEN_UPTIME
    GEN_PLATFORM --> PLATFORM_YML
    GEN_TLS --> PROM_FILES
    GEN_SLO --> PROM_FILES
    GEN_HAIRPIN --> HAIRPIN_YML
    GEN_UPTIME --> UPTIME_JSON

    IDENTITY ==>|"HIGHEST PRECEDENCE<br/>-e extra-vars"| ANSIBLE
    SCOPE -->|"auto-detects .local/identity.yml"| ANSIBLE
    COMMITTED_ID -->|"base values (overridden)"| ANSIBLE
    HOST_VARS -->|"base values (overridden)"| ANSIBLE
    PLATFORM_YML --> ANSIBLE
    ROLES --> ANSIBLE
    SECRETS --> ANSIBLE
    ANSIBLE ==>|"Jinja2 resolves real values"| DEPLOYED
```

## 2. Ansible Variable Precedence

The key insight: `.local/identity.yml` is injected via `-e @` extra-vars,
which have the **absolute highest** precedence in Ansible's 22-level hierarchy.

```mermaid
graph BT
    L1["1. Role defaults<br/>roles/*/defaults/main.yml"] --> MERGE
    L2["2. Committed identity.yml<br/>platform_domain: example.com"] --> MERGE
    L3["3. Host vars<br/>host_vars/proxmox-host.yml<br/>management_ipv4: 203.0.113.1"] --> MERGE
    L4["4. Generated platform.yml<br/>(gitignored, derived)"] --> MERGE
    L5["5. .local/identity.yml via -e @<br/>platform_domain: YOUR.DOMAIN<br/>management_ipv4: YOUR.REAL.IP"] ==>|"WINS ALWAYS"| MERGE

    MERGE["Ansible Variable Merge"] ==> RESULT["Final runtime values:<br/>platform_domain = YOUR.DOMAIN<br/>management_ipv4 = YOUR.REAL.IP"]

    style L5 fill:#ff9,stroke:#f90,stroke-width:3px
    style RESULT fill:#9f9,stroke:#090,stroke-width:2px
```

## 3. Bootstrap Sequence

What an operator runs after cloning — 3 scripts set up everything:

```mermaid
graph LR
    subgraph STEP1["Step 1: make init-local"]
        A1["init_local_overlay.py"] -->|reads| A2["controller-local-secrets.json<br/>(manifest of 237 secrets)"]
        A1 -->|creates| A3[".local/ directory tree<br/>SSH keys auto-generated<br/>Random passwords auto-generated<br/>Placeholder files for manual secrets"]
    end

    subgraph STEP2["Step 2: Operator edits"]
        B1[".local/identity.yml"] -->|set 8 values| B2["platform_domain<br/>platform_operator_email<br/>platform_operator_name<br/>platform_repo_name<br/>management_ipv4<br/>management_gateway4<br/>management_ipv6<br/>hetzner_ipv4_route_network"]
    end

    subgraph STEP3["Step 3: make generate-platform-vars"]
        C1["generate_platform_vars.py"] -->|reads| C2["identity + host_vars + stack"]
        C1 -->|writes| C3["inventory/group_vars/platform.yml<br/>(merged topology, ports, DNS)"]
    end

    subgraph STEP4["Step 4: make converge-..."]
        D1["ansible_scope_runner.py"] -->|injects| D2["-e @.local/identity.yml"]
        D2 --> D3["ansible-playbook runs<br/>with real values"]
    end

    A3 --> B1
    B2 --> C1
    C3 --> D1
```

## 4. The 8 Values That Control Everything

| Variable | What It Controls |
|----------|-----------------|
| `platform_domain` | ALL 60+ service FQDNs, TLS certs, DNS zone, Keycloak realm, mail domain |
| `platform_operator_email` | ACME certs, alert recipients, mail sender |
| `platform_operator_name` | Proxmox admin comment, notification author |
| `platform_repo_name` | Server checkout path, Gitea repo reference |
| `management_ipv4` | Public IP for DNS A records, firewall rules |
| `management_gateway4` | Network route for outbound traffic |
| `management_ipv6` | Public IPv6 for DNS AAAA records |
| `hetzner_ipv4_route_network` | Hetzner route for additional IPs |

The `platform_domain` value alone derives 60+ downstream variables:

```
platform_domain: acme.corp
    keycloak_realm_name: acme
    keycloak_oidc_issuer_url: https://sso.acme.corp/realms/acme
    hetzner_dns_zone_name: acme.corp
    platform_container_registry: registry.acme.corp
    mail_platform_domain: acme.corp
    proxmox_acme_domain: proxmox.acme.corp
    searxng_controller_url: http://search.acme.corp
    serverclaw_public_url: https://chat.acme.corp
    ...
```

## 5. Publication Pipeline (Zero Sanitization)

After ADR 0409, the committed code and public repo are identical:

```mermaid
graph LR
    subgraph PRIVATE["Private Repo (committed)"]
        P1["identity.yml: example.com"]
        P2["host_vars: 203.0.113.x"]
        P3["catalogs: example.com"]
    end

    subgraph PUBLIC["Public ServerClaw Repo"]
        S1["identity.yml: example.com"]
        S2["host_vars: 203.0.113.x"]
        S3["catalogs: example.com"]
    end

    subgraph DEPLOY["Deployed Instance"]
        D1["identity: lv3.org"]
        D2["host_vars: 65.108.75.123"]
        D3["services: *.lv3.org"]
    end

    PRIVATE -->|"publish_to_serverclaw.py<br/>Tier C: 0 files changed"| PUBLIC
    PRIVATE -->|".local/identity.yml<br/>-e extra-vars override"| DEPLOY

    style PUBLIC fill:#9f9,stroke:#090
    style DEPLOY fill:#9cf,stroke:#09c
```
