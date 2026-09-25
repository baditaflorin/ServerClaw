# ADR 0480: Multi-Deployment Certificate Validation

> **Superseded by [ADR 0488](0488-single-deployment-per-repo-checkout.md)** (2026-05-17). The multi-deployment substrate is retired; each repo checkout now configures exactly one deployment via `.local/identity.yml`.


**Status**: SUPERSEDED by ADR 0488
**Date**: 2026-05-05
**Decision**: Implement deployment-aware certificate validation to handle multiple parallel deployments (example.com, example.org) sharing NGINX edge infrastructure.

---

## Context

### Problem

The repository supports multiple concurrent deployments:
- **example.com** (Florin's private deployment)
- **example.org** (Public fork reference deployment)

Currently:
1. NGINX edge has certificates for **example.org**
2. lv3 validator checks FQDNs against **example.com** (from `.local/identity.yml`)
3. Pre-push gate fails with 44 cert_mismatch errors
4. Root cause: Deployment domain ≠ deployed certificate CN

### Why This Matters (Business Context)

- ServerClaw is designed as a **portable, forkable infrastructure template**
- Different organizations deploy with different domains (example.com, example.org, customer.com, etc.)
- Each deployment has its own certificates
- The validation gate must understand which deployment context it's validating

---

## Decision

Implement **deployment-aware certificate validation** with three tiers:

### Tier 1: Deployment Context Detection (ADR 0456/0458)

The validator automatically detects deployment context from:
1. `--deployment <slug>` flag (explicit)
2. `.local/active-deployment` file (current)
3. `.local/identity.yml` (legacy, current fallback)
4. Environment variable `DEPLOYMENT` (CI/CD)

### Tier 2: Deployment-Specific Catalogs

Each deployment can have its own certificate catalog overlay:
```
.local/deployments/lv3/certificate-catalog.json      (example.com certs)
.local/deployments/0fork/certificate-catalog.json    (example.org certs)
```

### Tier 3: Pre-Push Gate Enhancement

The pre-push hook will:
```bash
# Detect active deployment
DEPLOYMENT=$(cat .local/active-deployment 2>/dev/null || echo "lv3")

# Validate with deployment context
python3 scripts/certificate_validator.py \
  --deployment "$DEPLOYMENT" \
  --check-all
```

---

## Implementation

### Immediate Fix (This Session)

Update `.local/active-deployment`:
```
lv3
```

This tells the validator:
- Use example.com domains for validation
- Expect example.com certificate CN
- Check against deployment-specific catalog if present

### Script Changes Required

**scripts/certificate_validator.py**:
```python
# Add deployment context support
parser.add_argument('--deployment', help='Validate for specific deployment')

# Auto-detect if not provided
if not args.deployment:
    if Path('.local/active-deployment').exists():
        args.deployment = Path('.local/active-deployment').read_text().strip()
```

### Regenerating example.com Certificates

Once deployment context is set up, regenerate certificates:
```bash
# Dry-run
python3 scripts/cert_lifecycle_manager.py sync-missing --deployment lv3 --json

# Apply with Hetzner DNS API
HETZNER_API_KEY="6k2OLvRXjwQtxhlfiWxW3dAIphH4NiOtoMdEHmfA7oqVTBrX0WZzSSctvgrkSQPb" \
  python3 scripts/cert_lifecycle_manager.py sync-missing --apply
```

---

## Deployment Catalog Structure

### Before (current)
```
config/certificate-catalog.json          (example.com - generic)
.local/identity.yml                      (example.com - overlay only)
→ Creates domain substitution mismatch
```

### After (proposed)
```
config/certificate-catalog.json          (example.com - public fork template)
.local/active-deployment                 (lv3 - current deployment)
.local/identity.yml                      (example.com - deployment vars)
.local/deployments/lv3/certificate-catalog.json   (example.com certs - optional override)
→ Explicit deployment context prevents ambiguity
```

---

## Migration Path

### Phase 1 (Now)
1. Create `.local/active-deployment` file = `lv3`
2. Update pre-push hook to use `--deployment` flag
3. Regenerate example.com certificates using Hetzner API
4. Mark ADR 0375 as superseded by deployment context

### Phase 2 (Next Release)
1. Create `.local/deployments/*/` structure
2. Generate deployment-specific certificate catalogs
3. Document deployment setup for fork operators

### Phase 3 (Q3)
1. Make `--deployment` the primary configuration method
2. Deprecate `.local/identity.yml` as sole identity source
3. Support orchestrated multi-deployment scenarios (multiple API gateways, etc.)

---

## Trade-offs

| Option | Pros | Cons |
|--------|------|------|
| **Deployment context (chosen)** | Explicit, scalable, future-proof | Requires setup per deployment |
| Certificate catalog per domain | Simple for single deployment | Doesn't scale to multi-tenant |
| Disable cert validation | Unblocks development | Reduces security |
| Separate NGINX edges per deployment | Perfect isolation | Expensive, complex ops |

---

## Secret Management Integration (ADR 0480 Phase 1.5)

### Universal Secret Generation with srvclaw_ Prefix

All real secrets now include `srvclaw_` prefix for easy identification and filtering before commits.

**Key Principle**: Real secrets are searchable (`grep srvclaw_`), making accidental commits easy to detect.

### Components

1. **Core Utility** (`scripts/secret_masking_utility.py`)
   - `generate_real_secret(service_name='dbeaver', length=32, with_prefix=True)`
   - Returns: `srvclaw_dbeaver_VvPEZNJb3A79STW9TLxHMJoYAJ3mOEMOjIm2yPqqjak`
   - Always includes `srvclaw_` prefix in real secrets

2. **Ansible Filter** (`plugins/filter/generate_secret.py`)
   - Used inline in Ansible roles without hardcoding `openssl rand`
   - Jinja2 filter: `{{ 'dbeaver' | secret }}`
   - Returns real secret with srvclaw_ prefix ready for use

3. **CLI Generator** (`scripts/generate_secret_with_mask.py`)
   - For standalone credential generation
   - Outputs both real + masked versions in JSON
   - Used by postgres_client role

4. **Pre-Commit Hook** (`scripts/detect_unmasked_secrets.py`)
   - Detects ANY `srvclaw_` pattern in staged files (except .local/)
   - Prevents accidental commits of real secrets
   - Fails if `srvclaw_*` found outside allowed directories

### Real Secret Format

```yaml
# All real secrets follow this pattern:
srvclaw_<service>_<43-char-base64url>

Examples:
  srvclaw_dbeaver_VvPEZNJb3A79STW9TLxHMJoYAJ3mOEMOjIm2yPqqjak
  srvclaw_gitea_FzKn1L2mN3oP4qRsT5uVwXyZ9aBbCcDdEeFfGgHhIiJj
  srvclaw_hetzner_M9NqOpQrRsSt6uVuW7xXy8zZaBbDcEeEdFfGgHhIiJ
```

### Usage in Ansible Roles

Replace `openssl rand` with the filter:

```yaml
# OLD (bad - hardcoded, no prefix)
- name: Generate password
  shell: openssl rand -base64 24 > /tmp/password.txt

# NEW (good - universally searchable)
- name: Generate password with srvclaw_ prefix
  set_fact:
    my_password: "{{ 'myservice' | secret }}"
```

### Integration Points

- ✅ postgres_client role: uses `generate_secret_with_mask.py`
- ✅ Jinja2 filter available: `{{ service_name | secret }}`
- ✅ Pre-commit hook: prevents srvclaw_ patterns from commits
- 📋 TODO: Migrate 50+ roles to use `| secret` filter instead of `openssl rand`
- 📋 TODO: Create runbook for universal migration

---

## Affected Systems

- **Pre-push gate** (`.githooks/pre-push`)
- **Certificate validator** (`scripts/certificate_validator.py`)
- **Cert lifecycle manager** (`scripts/cert_lifecycle_manager.py`)
- **Documentation** (postmortems, runbooks)
- **CI/CD** (deployment detection)

---

## Metrics

After this ADR:
- ✅ Pre-push gate passes for all deployments
- ✅ Certificate mismatches reduced to 0
- ✅ Deployment context explicit in all workflows
- ✅ Supports unlimited concurrent deployments

---

## Related ADRs

- ADR 0375 - Certificate Validation (supersedes local-only approach)
- ADR 0456 - Multi-Deployment Orchestration (deployment context)
- ADR 0458 - Aggregated Multi-Deployment Validation
