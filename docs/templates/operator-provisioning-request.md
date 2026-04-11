# Operator Provisioning Request Template

Use this template when requesting a new platform account.
Fill in the fields and hand to the provisioning agent or admin.

---

## Request Details

| Field | Value | Notes |
|-------|-------|-------|
| **Full Name** | | e.g. "Platform Operator" |
| **Email** | | Account details will be sent here |
| **Role** | `admin` / `operator` / `viewer` | See role table below |
| **Duration** | | e.g. "3 days", "1 week", "permanent" |
| **Requester** | | Email of person authorizing access |
| **Reason** | | Brief justification for access |

## Role Reference

| Role | Keycloak | Groups | SSH | Use Case |
|------|----------|--------|-----|----------|
| `admin` | `platform-operator` | `lv3-platform-admins`, `grafana-admins` | Yes | Full platform control |
| `operator` | `platform-operator` | `lv3-platform-operators`, `grafana-viewers` | Yes | Day-to-day ops |
| `viewer` | `platform-read` | `lv3-platform-viewers`, `grafana-viewers` | No | Read-only dashboards |

---

## Provisioning Command

Once approved, run from the repo root (or ops host):

```bash
python3 scripts/provision_operator.py \
  --id <OPERATOR_ID> \
  --name "<FULL_NAME>" \
  --email <EMAIL> \
  --username <KEYCLOAK_USERNAME> \
  --role <ROLE> \
  --expires <EXPIRY_ISO8601> \
  --requester <REQUESTER_EMAIL>
```

### Naming Conventions

| Field | Pattern | Example |
|-------|---------|---------|
| `--id` | `<firstname>-<lastname>-tmp-NNN` | `florin-badita-tmp-003` |
| `--username` | `<firstname>.<lastname>-tmp-NNN` | `florin.badita-tmp-003` |
| `--expires` | ISO 8601 UTC | `2026-04-11T00:00:00Z` |

### If Keycloak API is unreachable from your machine

1. Forward Keycloak through SSH:
   ```bash
   ssh -f -N -L 18080:10.10.10.20:8443 ops@100.64.0.1 \
     -i .local/ssh/bootstrap.id_ed25519
   ```
2. Run with override:
   ```bash
   LV3_KEYCLOAK_URL=https://127.0.0.1:18080 python3 scripts/provision_operator.py ...
   ```
3. Or if bootstrap password was rotated:
   ```bash
   LV3_KEYCLOAK_BOOTSTRAP_PASSWORD=<current_password> python3 scripts/provision_operator.py ...
   ```

---

## Post-Provisioning Checklist

- [ ] `config/operators.yaml` updated with new entry
- [ ] Onboarding email sent (automatic via script, or manual via Gmail draft)
- [ ] Commit operators.yaml change to branch and merge to main
- [ ] Verify operator can log in at https://sso.example.com
- [ ] Set calendar reminder for expiry date to offboard
