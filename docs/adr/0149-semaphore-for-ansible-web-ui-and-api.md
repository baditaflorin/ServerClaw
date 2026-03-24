# ADR 0149: Semaphore for Ansible Job Management UI and API

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

Ansible is the platform's primary convergence engine. Playbooks are run via:

- The platform CLI (`lv3 run <workflow>`) which invokes the Windmill-backed goal compiler pipeline.
- Direct `ansible-playbook` invocations on the controller machine for development and break-glass scenarios.
- The Windmill workflow engine (ADR 0044) for scheduled and agent-triggered runs.

Each of these surfaces has gaps:

**The platform CLI** is well-suited for declared workflows in the workflow catalog (ADR 0048). But it is not designed for ad hoc playbook runs, partial-play execution, or inventory inspection during development.

**Direct `ansible-playbook`** invocations are untracked: they do not write to the mutation ledger (ADR 0115), do not pass through the health check gate (ADR 0128) or conflict detector (ADR 0127), and are not visible to other agents or the observation loop.

**Windmill** is excellent for composable, event-driven workflows but is not an Ansible-native tool. It wraps Ansible in shell scripts, which means inventory browsing, host variable inspection, and dry-run output are not presented in an Ansible-native way. Debugging a failing playbook in Windmill requires reading raw job logs.

**Semaphore** is a self-hosted Ansible automation platform with:
- A web UI for browsing inventory, editing playbooks, and viewing detailed job output (task-by-task, host-by-host).
- A REST API for triggering playbook runs, retrieving job results, and managing inventory.
- Integration with git repositories (pulls playbooks from the platform repo via Gitea, ADR 0143).
- A job history with full Ansible output, diff mode results, and task-level status.

Semaphore is not a replacement for Windmill. It is an Ansible-specific complement: where Windmill is best for orchestrating multi-service workflows with conditional logic, Semaphore is best for Ansible convergence with rich diagnostic output and inventory inspection.

## Decision

We will deploy **Semaphore** on `docker-runtime-lv3` as an Ansible-native job management UI and API, complementing the existing Windmill-based automation pipeline.

### Deployment

```yaml
# In versions/stack.yaml
- service: semaphore
  vm: docker-runtime-lv3
  image: semaphoreui/semaphore:latest
  port: 3020
  access: tailscale_only
  database: postgres-lv3
  subdomain: ansible.lv3.org   # Tailscale-only
  keycloak_oidc: true
```

### Project and inventory configuration

Semaphore is configured with a single project ("LV3 Platform") that mirrors the structure of the platform repository:

```yaml
# Managed by Ansible (meta!) via the semaphore_setup role
project:
  name: LV3 Platform
  repositories:
    - name: proxmox-florin-server
      git_url: http://gitea:3030/ops/proxmox_florin_server.git
      git_branch: main
      ssh_key: semaphore-gitea-deploy-key

  inventories:
    - name: production
      inventory_file: inventory/hosts.yml
      ssh_key: semaphore-ansible-key

  environments:
    - name: production
      env_vars:
        ANSIBLE_DIFF_MODE: "true"
        ANSIBLE_FORCE_COLOR: "true"

  task_templates:
    - name: "Converge all"
      playbook: playbooks/site.yml
      inventory: production
      environment: production

    - name: "Converge netbox"
      playbook: playbooks/netbox.yml
      inventory: production
```

### REST API for agents

The Semaphore REST API is used by agents for Ansible-specific operations:

```python
# platform/ansible/semaphore.py

class SemaphoreClient:
    def run_task(self, template_name: str, dry_run: bool = False) -> SemaphoreJob:
        """Trigger a Semaphore task template and return the job."""

    def get_job_output(self, job_id: int) -> list[AnsibleTaskResult]:
        """Retrieve structured task-level output for a completed job."""

    def list_hosts(self, inventory: str = "production") -> list[InventoryHost]:
        """Return the current inventory with host variables."""

    def get_host_facts(self, hostname: str) -> dict:
        """Return gathered facts for a specific host."""
```

The diff engine adapter (ADR 0120) can use Semaphore's `--check --diff` job API to get structured diff output rather than parsing raw CLI output:

```python
# In the Ansible diff adapter (ADR 0120)
job = semaphore.run_task("Converge netbox", dry_run=True)
job.wait_for_completion()
results = semaphore.get_job_output(job.id)
changed_tasks = [r for r in results if r.status == "changed"]
```

### Windmill integration

Windmill workflows that run Ansible playbooks can delegate to Semaphore for the execution step, gaining Semaphore's structured output and job history:

```python
# In a Windmill script
semaphore_job = semaphore.run_task(template_name=workflow_id, dry_run=False)
semaphore_job.wait_for_completion()
if semaphore_job.status == "failed":
    raise WorkflowFailed(f"Ansible playbook failed: {semaphore_job.task_errors}")
ledger.write(event_type="execution.completed", metadata={"semaphore_job_id": semaphore_job.id})
```

### Job history and audit

Semaphore maintains its own job history in Postgres. Every triggered run — whether from the web UI, the REST API, or a Windmill delegation — is visible in the Semaphore UI with full task-level output. This is the primary Ansible-specific debugging surface; the mutation ledger (ADR 0115) records that a run happened, while Semaphore records what each Ansible task did.

## Consequences

**Positive**

- Operators have a native Ansible web interface for browsing inventory, inspecting host variables, and reading task-level job output — tasks that are cumbersome in both the platform CLI and Windmill's generic job log view.
- The Semaphore API gives the diff engine (ADR 0120) structured access to Ansible check-mode output rather than parsing raw stdout.
- Ad hoc Ansible runs via the Semaphore UI are still tracked (Semaphore job history) even though they don't go through the full goal compiler pipeline.

**Negative / Trade-offs**

- Ad hoc runs via the Semaphore UI bypass the platform's health check (ADR 0128), conflict detector (ADR 0127), and ledger (ADR 0115). This is intentional for development use cases but must be clearly documented: Semaphore is for Ansible diagnostics and development, not for production change management. Production changes go through the platform CLI pipeline.
- Semaphore is another service to operate, maintain, and monitor. It must be included in the observation loop checks and PBS backup.
- Semaphore's LDAP/OIDC integration has historically lagged behind other open-source tools. If Keycloak OIDC integration is not supported in the deployed version, operators will need a separate local Semaphore account, which adds credential management overhead.

## Boundaries

- Semaphore complements Windmill; it does not replace it. Windmill is for multi-service workflows with conditional logic, event-driven triggers, and budget enforcement. Semaphore is for Ansible-native execution, diagnostic runs, and inventory inspection.
- Production changes that affect service availability must go through the platform CLI pipeline. Semaphore is permitted for development/diagnostic runs and for the diff engine adapter.

## Related ADRs

- ADR 0044: Windmill (primary workflow engine; not replaced)
- ADR 0056: Keycloak SSO (Semaphore OIDC login)
- ADR 0115: Event-sourced mutation ledger (Windmill-delegated Semaphore runs recorded here)
- ADR 0120: Dry-run semantic diff engine (uses Semaphore API for structured check-mode output)
- ADR 0125: Agent capability bounds (Semaphore API access requires T2+ for read, T3 for write)
- ADR 0143: Gitea (Semaphore pulls playbooks from local Gitea repo)
