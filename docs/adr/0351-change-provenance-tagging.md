# ADR 0351: Change Provenance Tagging in All Generated and Managed Files

- Status: Accepted
- Implementation Status: Not Implemented
- Date: 2026-04-05
- Tags: audit, provenance, documentation, infrastructure, agent-coordination, dry

## Context

The platform now manages 153+ Ansible roles, 250+ runbooks, and 80+ services
deployed across multiple VMs. When an operator or agent inspects a deployed
file (e.g., `/opt/keycloak/runtime.env`, `/etc/nginx/fragments.d/0022-keycloak.conf`,
`/etc/systemd/system/lv3-cert-renew.service`), there is no reliable way to
answer:

1. Which ADR authorized this configuration block?
2. Which workstream last modified this file?
3. Which Ansible role and playbook rendered this file?
4. When was it last applied?
5. Which agent session performed the apply?

The mutation audit callback plugin (`plugins/callback/mutation_audit.py`)
records playbook events but its output is in a separate log file. The deployed
files themselves carry no provenance.

This creates a gap: files can drift from their expected state (manual edits,
partial applies, config management tool competing with a service's own
write-back mechanism) and the drift is not self-describing.

Provenance tags embedded in files close this gap. They are:
- Free to include (just a comment in most formats).
- Self-describing — surveyable by `grep`, no external log query needed.
- Consistent with the nginx fragment header established in ADR 0350.

## Decision

### 1. Provenance header block

Every file rendered from a Jinja2 template or written by an operator tool must
include the following provenance block, formatted as a comment appropriate to
the file type:

```
Managed by:  roles/<role_name>
ADR:         <adr_number> — <adr_short_title>
Workstream:  <workstream_id>
Playbook:    <playbook_path>
Agent:       <agent_session_id | "human-operator">
Applied:     <iso8601_timestamp>
Do not edit by hand — regenerated on each apply.
```

### 2. Comment syntax by file type

| File type | Comment syntax | Example header line |
|---|---|---|
| nginx `.conf` | `# ...` | `# Managed by: roles/keycloak_runtime` |
| systemd `.service`/`.timer` | `# ...` | `# Managed by: roles/cert_renewal_timer` |
| shell `.sh` | `# ...` | `# Managed by: roles/control_plane_recovery` |
| Python `.py` | `# ...` | `# Managed by: roles/alertmanager_runtime` |
| YAML `.yml`/`.yaml` | `# ...` | `# Managed by: roles/docker_runtime` |
| TOML `.toml` | `# ...` | `# Managed by: roles/build_server` |
| HCL `.hcl` | `# ...` | `# Managed by: roles/common` |
| env `.env` | `# ...` | `# Managed by: roles/keycloak_runtime` |
| JSON `.json` | No native comments — embed in `_provenance` key | see below |
| Docker Compose YAML | `# ...` | `# Managed by: roles/keycloak_runtime` |

For JSON files:

```json
{
  "_provenance": {
    "managed_by": "roles/keycloak_runtime",
    "adr": "0022",
    "workstream": "ws-0346",
    "applied": "2026-04-05T10:00:00Z",
    "agent": "agent-session-abc123"
  },
  ...actual content...
}
```

### 3. Jinja2 macro

A shared Jinja2 macro `macros/provenance_header.j2` provides the header block:

```jinja2
{# macros/provenance_header.j2 #}
{% macro provenance(role, adr, adr_title, comment_char='#') %}
{{ comment_char }} Managed by:  roles/{{ role }}
{{ comment_char }} ADR:         {{ adr }} — {{ adr_title }}
{{ comment_char }} Workstream:  {{ workstream_id | default('unset') }}
{{ comment_char }} Playbook:    {{ playbook_path | default('unset') }}
{{ comment_char }} Agent:       {{ agent_session_id | default('human-operator') }}
{{ comment_char }} Applied:     {{ ansible_date_time.iso8601 }}
{{ comment_char }} Do not edit by hand — regenerated on each apply.
{% endmacro %}
```

Usage in any template:

```jinja2
{% from 'macros/provenance_header.j2' import provenance %}
{{ provenance('keycloak_runtime', '0022', 'Keycloak as platform IdP') }}
# rest of file content...
```

### 4. Operator tool provenance

Operator tools (ADR 0343) that write files directly (not via Ansible templates)
must prepend the header programmatically using a helper from
`controller_automation_toolkit.py`:

```python
def write_with_provenance(path: Path, content: str, meta: dict, comment_char: str = '#') -> None:
    header = PROVENANCE_TEMPLATE.format(comment_char=comment_char, **meta)
    path.write_text(header + "\n" + content)
```

### 5. Provenance drift detection

`scripts/provenance_audit.py` (new):

```
provenance_audit.py scan --vmid <id>       # scan all managed files on VM for header
provenance_audit.py check --file <path>    # check single file provenance
provenance_audit.py stale --days 30        # files not re-applied in >30 days
provenance_audit.py missing --role <name>  # files rendered by role that lack header
```

A file is considered **stale** if its `Applied:` timestamp is older than
`max_stale_days` (default: 60 days, configurable per role). Stale files emit
alerts via ntfy. They are not auto-updated — stale detection triggers a
re-apply recommendation, not an automatic change.

### 6. Pre-commit gate

`.pre-commit-config.yaml` is extended with a hook that validates that all
Jinja2 templates in `roles/*/templates/` call the `provenance` macro.
Templates that render to binary files or templates where comments are
technically invalid are blocklisted.

## Places That Need to Change

### `roles/_template/service_scaffold/` templates

All `.j2.tpl` files get the `provenance` macro call prepended in the scaffold.

### `roles/common/templates/`

All existing templates get the `provenance` macro call added.

### `collections/ansible_collections/lv3/platform/roles/*/templates/`

Iterative migration: add macro call to all templates. Prioritised by apply
frequency (highest-traffic roles first).

### `controller_automation_toolkit.py`

Add `write_with_provenance()` helper and `PROVENANCE_TEMPLATE` constant.

### `scripts/provenance_audit.py` (new)

Layer 2 audit tool. Implements `scan`, `check`, `stale`, `missing` subcommands.

### `macros/provenance_header.j2` (new)

Shared Jinja2 macro file. Location: `collections/ansible_collections/lv3/platform/macros/`.

### `.pre-commit-config.yaml`

Add `check-provenance-macro` hook for templates.

## Consequences

### Positive

- Any deployed file is self-describing: ADR, workstream, timestamp, agent in one grep.
- Drift detection becomes trivial: files with no header or old `Applied:` date
  are candidates for re-apply.
- Debugging becomes faster — `grep "ADR:" /etc/nginx/fragments.d/*` immediately
  shows which ADR governed each nginx rule.

### Negative / Trade-offs

- Migrating 153 roles' templates is a large one-time effort (mechanical but not trivial).
- The provenance block adds ~8 lines to every rendered file. For compact configs
  this is noise; for binary-adjacent files (e.g., certificate bundles) it is inapplicable.
- `Applied:` timestamps are only accurate to the Ansible task execution time —
  if a file is not changed by an apply (idempotent no-op), the timestamp does
  not update, causing false "stale" positives for stable configs.

## Related ADRs

- ADR 0085: IaC Boundary
- ADR 0134: Changelog Redaction Config
- ADR 0165: Playbook and Role Metadata Standard
- ADR 0343: Operator Tool Interface Contract
- ADR 0347: Agent File-Domain Locking
- ADR 0350: Nginx Fragment-Based Atomic Configuration
