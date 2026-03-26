# LLM Implementation Prompts — ADRs 0082–0091

Feed these prompts **in order** to an LLM with repo access.
Each prompt is self-contained: it names what to read, what to build, and how to verify before committing.
Do **not** skip ahead — each prompt's work is a dependency for the next.

---

## PROMPT 1 — ADR 0082: Remote Build Execution Gateway
> **Lane A · Step 1 · No dependencies**

```
You are implementing ADR 0082 in the proxmox_florin_server repo.

Read these files before writing anything:
- docs/adr/0082-remote-build-execution-gateway.md   (the full spec)
- docs/workstreams/adr-0082-remote-build-gateway.md  (scope + verification)
- Makefile                                            (so you can append targets correctly)
- ansible.cfg                                         (so you can see existing inventory conventions)

Create exactly these files:

1. scripts/remote_exec.sh
   - Accepts a command label as $1 and optional --local-fallback flag
   - rsyncs only changed files to build-lv3:/opt/builds/proxmox_florin_server/
     using: rsync --checksum --delete --exclude-from=.rsync-exclude
   - reads config/build-server.json to get host, ssh key, workspace root
   - runs the command on the build server inside the correct Docker container
     (image is looked up from config/check-runner-manifest.json by command label)
   - streams stdout/stderr back over SSH; forwards exit code exactly
   - if build-lv3 is unreachable AND --local-fallback is set, runs locally
   - when REMOTE_EXEC_VERBOSE=1 is set, prints the exact docker run command
   - uses: ssh -o ConnectTimeout=5 -o BatchMode=yes

2. .rsync-exclude
   - Excludes: .local/, *.vault, .env, receipts/, .git/, __pycache__/,
     *.pyc, .terraform/, .packer_cache/, config/build-cache-manifest.json

3. inventory/build_server.yml
   - Group: build_server
   - Host: build-lv3
   - ansible_host: 100.64.0.1   (placeholder — note in a comment that the
     operator should replace with the real Tailscale IP)
   - ansible_user: ops
   - ansible_ssh_private_key_file: ~/.ssh/id_ed25519

4. config/build-server.json
   - Fields: host, ssh_key, workspace_root, default_timeout_seconds,
     docker_socket, registry_base
   - Include a commands{} block mapping each make target to a command label

5. Append to Makefile (do not rewrite it — append a clearly marked section):
   ## Remote build execution (ADR 0082)
   - remote-lint
   - remote-validate
   - remote-pre-push
   - remote-packer-build (accepts IMAGE=)
   - remote-image-build (accepts SERVICE=)
   - remote-exec (accepts COMMAND=)
   - check-build-server  (ssh connectivity + rsync dry-run smoke test)

6. docs/runbooks/remote-build-gateway.md
   - Setup steps, daily usage examples, fallback mode, troubleshooting table

Verification before committing:
- bash -n scripts/remote_exec.sh  (no syntax errors)
- python3 -c "import json; json.load(open('config/build-server.json'))"
- grep -q "remote-lint" Makefile

Then commit to branch codex/adr-0082-remote-build-gateway with message:
"Implement ADR 0082: remote build execution gateway"

Mark ADR status as: Proposed → Accepted (update the Status line in the ADR file).
```

---

## PROMPT 2 — ADR 0083: Docker-Based Check Runner
> **Lane A · Step 2 · Requires PROMPT 1 merged**

```
You are implementing ADR 0083 in the proxmox_florin_server repo.

Read these files before writing anything:
- docs/adr/0083-docker-based-check-runner.md
- docs/workstreams/adr-0083-docker-check-runner.md
- config/build-server.json                 (written in PROMPT 1)
- scripts/remote_exec.sh                   (written in PROMPT 1)
- Makefile                                 (see existing remote targets)

Create exactly these files:

1. docker/check-runners/ansible/Dockerfile
   - Base: debian:12-slim (pin to a digest — use latest from hub.docker.com)
   - Installs: ansible-core==2.17.*, ansible-lint, yamllint, community.general collection
   - Pins all versions; writes them to a requirements.txt alongside

2. docker/check-runners/python/Dockerfile
   - Base: python:3.12-slim (pinned digest)
   - Installs: flake8, mypy, black, isort, pytest, jsonschema (all pinned)

3. docker/check-runners/infra/Dockerfile
   - Base: debian:12-slim (pinned digest)
   - Installs: opentofu (latest stable), packer (latest stable), yamllint, trivy

4. docker/check-runners/security/Dockerfile
   - Base: debian:12-slim (pinned digest)
   - Installs: trivy, gitleaks
   - Includes: RUN trivy db update  (so DB is baked in at build time)

5. config/check-runner-manifest.json
   - Keys: lint-ansible, lint-yaml, validate-schemas, type-check,
           security-scan, tofu-validate, packer-validate
   - Each entry: image, command, working_dir (/workspace), timeout_seconds
   - Image names follow: registry.lv3.org/check-runner/<name>:<version>

6. scripts/parallel_check.py
   - Reads config/check-runner-manifest.json
   - Accepts check label(s) as positional args, or --all for all checks
   - Launches each check as a subprocess: docker run --rm -v <workspace>:/workspace
     --cpus=4 <image> <command>
   - Runs all requested checks concurrently (threading or asyncio)
   - Prints a live spinner per check (use simple ASCII: ⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏)
   - On completion prints a table: CHECK | STATUS | DURATION
   - Exits non-zero if any check fails

7. Append to Makefile:
   ## Docker check runners (ADR 0083)
   - build-check-runners   (builds all 4 images locally)
   - push-check-runners    (pushes to registry.lv3.org)
   - run-checks            (accepts CHECKS= for specific labels, or runs all)

8. config/windmill/scripts/check-runner-rebuild.py
   - Windmill script that: builds all 4 images with BuildKit inline cache,
     pushes to registry.lv3.org, reads new digests, writes them back to
     config/check-runner-manifest.json, commits the manifest update

Verification before committing:
- docker build --no-cache docker/check-runners/ansible/ --tag test-ansible
  (must succeed with no errors)
- python3 scripts/parallel_check.py lint-yaml --help  (prints usage)
- python3 -c "import json; json.load(open('config/check-runner-manifest.json'))"

Then commit to branch codex/adr-0083-docker-check-runner:
"Implement ADR 0083: Docker-based check runner images and parallel executor"
```

---

## PROMPT 3 — ADR 0089: Build Artifact Cache
> **Lane A · Step 3 · Requires PROMPTS 1 and 2 merged**

```
You are implementing ADR 0089 in the proxmox_florin_server repo.

Read these files before writing anything:
- docs/adr/0089-build-artifact-cache.md
- docs/workstreams/adr-0089-build-cache.md
- scripts/remote_exec.sh
- roles/  (look for an existing build_server role; if none, you will create one)

Create or modify exactly these files:

1. roles/build_server/tasks/main.yml  (create if absent)
   - Install and configure apt-cacher-ng (package + systemd enable/start)
   - Create /opt/builds/.packer.d/ directory (owned by ops user)
   - Create /opt/builds/.ansible/collections/ directory
   - Write /etc/buildkit/buildkitd.toml with:
       [worker.containerd]
       gc = true
       [[worker.containerd.gcpolicy]]
       keepDuration = "336h"
       keepBytes = 53687091200   # 50 GB

2. roles/build_server/defaults/main.yml
   - buildkit_cache_gb: 50
   - apt_cacher_port: 3142
   - packer_plugin_cache: /opt/builds/.packer.d
   - ansible_collection_cache: /opt/builds/.ansible/collections
   - pip_cache_volume: pip-cache
   - build_workspace: /opt/builds/proxmox_florin_server

3. Update scripts/remote_exec.sh  (edit the existing file)
   - Add -v pip-cache:/root/.cache/pip to all Python container invocations
   - Add -v /opt/builds/.packer.d:/root/.packer.d to all Packer invocations
   - Add Galaxy SHA-gate logic before any ansible-galaxy collection install:
       sha256sum requirements.yml > /tmp/req.sha
       if ! diff -q /tmp/req.sha /opt/builds/.ansible/requirements.sha; then
         ansible-galaxy collection install ...
         cp /tmp/req.sha /opt/builds/.ansible/requirements.sha
       fi

4. config/build-cache-manifest.json
   - Start as an empty skeleton:
       { "docker_images": [], "pip_cache_size_mb": 0,
         "packer_plugins": [], "ansible_collections": [],
         "last_warmed": null }
   - (The warm-build-cache workflow populates this at runtime)

5. config/windmill/scripts/warm-build-cache.py
   - Windmill script: pulls all images in check-runner-manifest.json,
     runs pip install -r requirements.txt with the pip-cache volume mounted,
     pre-downloads packer plugins by running packer init on each template,
     runs ansible-galaxy collection install from requirements.yml,
     writes updated sizes + digests to config/build-cache-manifest.json,
     commits the manifest change to main

6. Append to Makefile:
   ## Build cache (ADR 0089)
   - warm-cache     (triggers warm-build-cache Windmill workflow)
   - cache-status   (reads config/build-cache-manifest.json, prints summary table)

Verification before committing:
- python3 -c "import json; json.load(open('config/build-cache-manifest.json'))"
- ansible-lint roles/build_server/   (must pass with no errors)
- grep "pip-cache" scripts/remote_exec.sh

Commit to codex/adr-0089-build-cache:
"Implement ADR 0089: build artifact cache (BuildKit, pip, apt-cacher-ng, Packer, Galaxy)"
```

---

## PROMPT 4 — ADR 0087: Repository Validation Gate
> **Lane C · Requires PROMPTS 1, 2, 3 merged · Can run in parallel with PROMPT 5**

```
You are implementing ADR 0087 in the proxmox_florin_server repo.

Read these files before writing anything:
- docs/adr/0087-repository-validation-gate.md
- docs/workstreams/adr-0087-validation-gate.md
- .pre-commit-config.yaml                  (existing; you will replace its content)
- config/check-runner-manifest.json        (written in PROMPT 2)
- scripts/parallel_check.py               (written in PROMPT 2)

Create or modify exactly these files:

1. .pre-commit-config.yaml  (REPLACE entire content)
   - Keep only fast (<5s) hooks:
     pre-commit-hooks: check-yaml, check-json, detect-private-key,
                       end-of-file-fixer, trailing-whitespace
     gitleaks v8.18.2: gitleaks hook

2. .gitleaks.toml
   - Create with allowlist entries for:
     - Ansible vault ciphertext headers ($ANSIBLE_VAULT;1.1;AES256)
     - Test fixture placeholder API keys (CHANGEME, REPLACE_ME, <api_key>)
     - Any existing patterns in the repo that cause false positives
       (grep the repo for common token-like strings first)

3. .githooks/pre-push  (new file — committed template, not .git/hooks/)
   #!/usr/bin/env bash
   set -euo pipefail
   echo "Running validation gate on build server..."
   scripts/remote_exec.sh pre-push-gate --local-fallback

4. config/validation-gate.json
   - Define all 8 checks from the ADR:
     lint-ansible, lint-yaml, type-check, validate-schemas,
     playbook-syntax, tofu-validate, packer-validate, security-scan
   - Each entry: id, image (from check-runner-manifest), command,
     severity (error|warn), timeout_seconds

5. scripts/run_gate.py
   - Reads config/validation-gate.json
   - Calls scripts/parallel_check.py with all check IDs
   - Prints a final PASS/FAIL banner with total wall-clock time
   - Exits non-zero if any error-severity check fails

6. Append to Makefile:
   ## Validation gate (ADR 0087)
   - install-hooks   (copies .githooks/pre-push to .git/hooks/pre-push; chmod +x)
   - pre-push-gate   (runs scripts/run_gate.py directly; same as what the hook calls)
   - gate-status     (prints last gate run result + any bypass receipts from today)
   Update the existing `setup` target (or create it) to call install-hooks.

7. receipts/gate-bypasses/.gitkeep  (create empty directory marker)

8. config/windmill/scripts/post-merge-gate.py
   - Windmill script: clones main to a temp workspace on the build server,
     runs scripts/run_gate.py, emits NATS event platform.ci.gate-passed or
     platform.ci.gate-failed with the check results as JSON payload

9. docs/runbooks/validation-gate.md
   - Install, daily usage, bypass procedure, troubleshooting

Verification before committing:
- bash -n .githooks/pre-push
- python3 -m py_compile scripts/run_gate.py
- python3 -c "import json; json.load(open('config/validation-gate.json'))"
- Make sure all 8 checks are present in validation-gate.json

Commit to codex/adr-0087-validation-gate:
"Implement ADR 0087: two-layer repository validation gate with bypass audit trail"
```

---

## PROMPT 5 — ADR 0086: Ansible Collection Packaging
> **Lane C · Requires PROMPTS 1, 2, 3 merged · Largest effort — coordinate with any open branches touching roles/**

```
You are implementing ADR 0086 in the proxmox_florin_server repo.

IMPORTANT: This is a structural migration. Make ZERO functional changes.
All you are doing is moving files and updating import paths.

Read these files before writing anything:
- docs/adr/0086-ansible-collection-packaging.md
- docs/workstreams/adr-0086-ansible-collections.md
- ansible.cfg
- requirements.yml  (if it exists)
- ls roles/         (list all existing roles)

Execute in this exact order:

STEP A — Create collection scaffold
1. mkdir -p collections/lv3/platform/{roles,plugins/filter_plugins,playbooks,meta,molecule}
2. Create collections/lv3/platform/galaxy.yml:
     namespace: lv3
     name: platform
     version: 1.0.0
     description: lv3 homelab platform roles and plugins
     license: MIT
     min_ansible_version: "2.17"
3. Create collections/lv3/platform/meta/runtime.yml:
     requires_ansible: ">=2.17"

STEP B — Migrate all roles
4. Copy (do not delete yet) all directories from roles/ into
   collections/lv3/platform/roles/
   This is a straight copy: cp -r roles/* collections/lv3/platform/roles/

STEP C — Create the four DRY shared utility roles
5. Create collections/lv3/platform/roles/preflight/tasks/main.yml
   Extract from the most common pattern across roles:
   - Assert supported OS (Debian 11 or 12)
   - Assert required variables are defined (use a vars: block listing them)
   - Wait for SSH to be responsive (wait_for_connection)
   Add collections/lv3/platform/roles/preflight/meta/main.yml with
   galaxy_info block.

6. Create collections/lv3/platform/roles/common_handlers/handlers/main.yml
   Extract the most common handlers found across roles:
   - systemd daemon-reload
   - restart docker
   - reload nginx
   - restart service (generic, uses {{ handler_service_name }})
   This role has NO tasks — handlers only.

7. Create collections/lv3/platform/roles/secret_fact/tasks/main.yml
   - Fetches a secret from OpenBao using the URI module
   - Exposes it as an Ansible fact named {{ secret_fact_name }}
   - Uses vars: secret_path (required), secret_fact_name (required),
               openbao_url (default from group_vars)

8. Create collections/lv3/platform/roles/wait_for_healthy/tasks/main.yml
   - Polls a URL until it returns the expected HTTP status
   - Uses vars: health_url (required), expected_status (default 200),
               timeout_seconds (default 60), retry_delay (default 5)

STEP D — Update role metadata
9. For each role that currently copy-pastes preflight logic, add to its
   meta/main.yml:
     dependencies:
       - role: lv3.platform.preflight
   Do this for at least the 5 most common roles as a proof-of-concept.
   List in the commit message which roles were updated.

STEP E — Create backwards-compatibility symlink
10. In the repo root: create a symlink roles -> collections/lv3/platform/roles
    (do NOT delete the original roles/ directory yet — rename it roles_backup/
    first, then create the symlink)

STEP F — Update playbooks to use FQCNs
11. Run this sed command across all playbooks/*.yml and site.yml:
      sed -i 's/role: \([a-z_]*\)/role: lv3.platform.\1/g'
    Then manually verify 3–5 playbooks look correct.

STEP G — Update ansible.cfg
12. Add to ansible.cfg:
    [defaults]
    collections_paths = ./collections:~/.ansible/collections

STEP H — Galaxy server stub
13. Create config/windmill/scripts/collection-publish.py
    - Windmill script: runs ansible-galaxy collection build in
      collections/lv3/platform/, then pushes to galaxy.lv3.org
      (use the galaxy_server_url from config/build-server.json)

14. Append to Makefile:
    ## Ansible collection (ADR 0086)
    - collection-build     (ansible-galaxy collection build collections/lv3/platform/)
    - collection-publish   (builds then pushes to galaxy.lv3.org)
    - collection-install   (ansible-galaxy collection install lv3.platform:<ver>)

Verification before committing:
- ansible-galaxy collection build collections/lv3/platform/ --output-path /tmp/
  (must produce lv3-platform-1.0.0.tar.gz with no errors)
- ansible-playbook --syntax-check site.yml  (or your main playbook)
  (must pass — this proves the FQCN migration didn't break imports)
- ls -la roles  (must show it is a symlink pointing to collections/lv3/platform/roles)

Commit to codex/adr-0086-ansible-collections:
"Implement ADR 0086: lv3.platform collection with DRY shared utility roles"

List in the commit message body:
- How many roles were migrated
- Which 5+ roles now use the preflight dependency
- Whether syntax-check passes for all playbooks
```

---

## PROMPT 6 — ADR 0084: Packer VM Template Pipeline
> **Lane B · Step 1 · Requires PROMPTS 1, 2, 3 merged · Can run in parallel with PROMPTS 4 and 5**

```
You are implementing ADR 0084 in the proxmox_florin_server repo.

Read these files before writing anything:
- docs/adr/0084-packer-vm-template-pipeline.md
- docs/workstreams/adr-0084-packer-pipeline.md
- config/build-server.json
- inventory/  (understand the Proxmox host IP and API access pattern)
- roles/common/  (understand what base hardening currently does)

Create exactly these files:

1. packer/variables/common.pkrvars.hcl
   - proxmox_url = "https://<proxmox-host>:8006/api2/json"  (comment: replace with real IP)
   - proxmox_node = "pve"
   - proxmox_storage = "local-lvm"
   - proxmox_network_bridge = "vmbr10"
   - template_username = "ops"

2. packer/scripts/step-cli-install.sh
   - Downloads and installs the step CLI binary from smallstep releases
   - Pins the version (use latest stable from smallstep GitHub)

3. packer/scripts/base-hardening.sh
   - Injects apt-cacher-ng proxy: echo 'Acquire::http::Proxy "http://10.10.10.250:3142";'
   - apt-get update && apt-get upgrade -y
   - Installs: curl, wget, rsyslog, htop, tmux, vim, fail2ban, unattended-upgrades
   - Calls step-cli-install.sh
   - Configures sshd_config: PasswordAuthentication no, PermitRootLogin no
   - Enables and starts fail2ban and unattended-upgrades

4. packer/scripts/docker-install.sh
   - Installs Docker CE from the official Docker apt repo
   - Installs docker-compose-plugin
   - Adds the ops user to the docker group

5. packer/scripts/postgres-install.sh
   - Installs PostgreSQL 16 from the official PGDG apt repo
   - Does NOT start or configure it (that is left to Ansible)

6. packer/templates/lv3-debian-base.pkr.hcl
   - Source: proxmox-iso (Debian 12 netinstall ISO)
   - VM: cores=2, memory=2048, disk=20G on local-lvm
   - Communicator: SSH (ops user, key-based)
   - Provisioners (in order): shell base-hardening.sh
   - Post-processor: proxmox template (VMID 9000, name "lv3-debian-base")
   - Auth: reads PROXMOX_API_TOKEN_ID and PROXMOX_API_TOKEN_SECRET from env

7. packer/templates/lv3-docker-host.pkr.hcl
   - Source: proxmox-clone (clones from lv3-debian-base, VMID 9000)
   - Provisioners: shell docker-install.sh
   - Post-processor: proxmox template (VMID 9001, name "lv3-docker-host")

8. packer/templates/lv3-postgres-host.pkr.hcl
   - Source: proxmox-clone from lv3-debian-base (VMID 9000)
   - Provisioners: shell postgres-install.sh
   - Post-processor: VMID 9002, name "lv3-postgres-host"

9. packer/templates/lv3-ops-base.pkr.hcl
   - Source: proxmox-clone from lv3-debian-base (VMID 9000)
   - No additional provisioner (ops tools are already in base)
   - Post-processor: VMID 9003, name "lv3-ops-base"

10. config/vm-template-manifest.json
    - Skeleton with four entries (lv3-debian-base, lv3-docker-host,
      lv3-postgres-host, lv3-ops-base)
    - Each: vmid, name, build_date (null), version (null), packer_commit (null)

11. config/windmill/scripts/packer-template-rebuild.py
    - Windmill script: fetches Proxmox API token from OpenBao,
      calls make remote-packer-build for each template in order
      (base first, then derived templates),
      updates config/vm-template-manifest.json with build date and Packer commit

12. Append to Makefile:
    ## Packer templates (ADR 0084)
    - remote-packer-build  IMAGE=   (calls remote_exec.sh packer-build with IMAGE var)
    - validate-packer               (runs packer validate on all templates via build server)

13. docs/runbooks/packer-vm-templates.md

Verification before committing:
- packer validate -var-file=packer/variables/common.pkrvars.hcl \
    packer/templates/lv3-debian-base.pkr.hcl
  (run on the build server if Packer is not local; use: make validate-packer)
- bash -n packer/scripts/base-hardening.sh
- python3 -c "import json; json.load(open('config/vm-template-manifest.json'))"

Commit to codex/adr-0084-packer-pipeline:
"Implement ADR 0084: Packer VM template pipeline (4 layered templates)"
```

---

## PROMPT 7 — ADR 0085: OpenTofu VM Lifecycle
> **Lane B · Step 2 · Requires PROMPT 6 merged**

```
You are implementing ADR 0085 in the proxmox_florin_server repo.

Read these files before writing anything:
- docs/adr/0085-opentofu-vm-lifecycle.md
- docs/workstreams/adr-0085-opentofu-vm-lifecycle.md
- config/vm-template-manifest.json     (written in PROMPT 6)
- versions/stack.yaml                  (source of truth for current VM list)
- inventory/                           (understand how VMs are currently named)
- config/build-server.json

Create exactly these files:

1. tofu/modules/proxmox-vm/variables.tf
   - All input vars from the ADR: name, vmid, template, cores, memory_mb,
     disk_gb, ip_address, gateway, bridge, tags, startup_order
   - Add lifecycle_prevent_destroy (bool, default true)

2. tofu/modules/proxmox-vm/main.tf
   - Uses bpg/proxmox provider
   - resource "proxmox_virtual_environment_vm" with all variables wired in
   - lifecycle { prevent_destroy = var.lifecycle_prevent_destroy }

3. tofu/modules/proxmox-vm/outputs.tf
   - Outputs: vm_id, ip_address, name, node_name

4. tofu/environments/production/backend.tf
   - terraform { backend "s3" { ... } } pointing to MinIO:
     bucket = "tofu-state", key = "production/terraform.tfstate",
     endpoint = "https://minio.lv3.org" (comment: update with real endpoint)
     region = "us-east-1", skip_credentials_validation = true

5. tofu/environments/production/main.tf
   - Declare each VM currently in versions/stack.yaml as a module block
   - Use the proxmox-vm module for each
   - Start with the VMs you can see in inventory/ — name them accurately

6. tofu/environments/production/terraform.tfvars
   - proxmox_url, proxmox_node, proxmox_storage (non-secret values only)
   - A comment saying: proxmox API token is injected at runtime from OpenBao

7. tofu/environments/staging/backend.tf
   - Same as production but key = "staging/terraform.tfstate"

8. tofu/environments/staging/main.tf
   - Declare the staging VMs from ADR 0072 (docker-runtime-staging,
     postgres-staging) as module blocks
   - Use bridge = "vmbr20", ip range 10.20.10.x

9. .terraform.lock.hcl  per environment (create a stub with the bpg/proxmox
   provider version pinned to the latest stable release)

10. docs/runbooks/tofu-vm-import.md
    - Step-by-step: for each existing VM, run:
        tofu import module.<name>.proxmox_virtual_environment_vm.this <node>/<vmid>
      Verify after each import that `tofu plan` shows "No changes" for that VM
      before importing the next one.

11. docs/runbooks/tofu-vm-lifecycle.md
    - Day-to-day: how to resize a VM (edit main.tf, PR, review plan, merge),
      how to create a new VM, how to destroy a staging VM safely

12. Append to Makefile:
    ## OpenTofu (ADR 0085)
    - remote-tofu-plan   ENV=       (runs tofu plan on build server for given env)
    - remote-tofu-apply  ENV=       (runs tofu apply with saved plan)
    - tofu-drift         ENV=       (runs tofu plan -detailed-exitcode; exits 2 if drift)
    - tofu-import        VM=        (runs tofu import for a single VM by name)

Verification before committing:
- cd tofu/environments/production && tofu validate
  (run on build server: make remote-exec COMMAND="cd tofu/environments/production && tofu validate")
- python3 -c "import json" (trivial — just confirm files exist and are not empty)
- grep "prevent_destroy" tofu/modules/proxmox-vm/main.tf

Commit to codex/adr-0085-opentofu-vm-lifecycle:
"Implement ADR 0085: OpenTofu declarative VM lifecycle with import runbook"

Note in the commit body: list every VM declared in production/main.tf
```

---

## PROMPT 8 — ADR 0090: Unified Platform CLI (`lv3`)
> **Lane D · Requires PROMPT 1 merged and ADR 0075 (service capability catalog) already live**

```
You are implementing ADR 0090 in the proxmox_florin_server repo.

Read these files before writing anything:
- docs/adr/0090-unified-platform-cli.md
- docs/workstreams/adr-0090-platform-cli.md
- config/service-capability-catalog.json   (the service registry)
- config/build-server.json
- Makefile                                  (all remote-* targets to wrap)

Create exactly these files:

1. scripts/lv3_cli.py
   Implement all 14 command groups using Python's click library.
   For each command, implement the logic as described below:

   lv3 status
   - Reads config/service-capability-catalog.json
   - Probes each service health URL concurrently (3-second timeout per service)
   - Prints a table: SERVICE | VM | URL | HEALTH | LATENCY
   - Supports --no-color flag; honours NO_COLOR env var
   - Exits 0 if all healthy, 1 if any unhealthy

   lv3 deploy <service> [--env staging|production] [--dry-run]
   - Looks up the service in the catalog to find its tags and playbook
   - Runs: make remote-exec COMMAND="ansible-playbook site.yml --tags <tags>"
   - With --dry-run: prints the command but does not run it
   - After run: prints the path to the last matching receipt file

   lv3 lint [--local]
   - Runs make remote-lint (or make lint with --local)

   lv3 validate [--strict]
   - Runs make remote-validate

   lv3 diff [--env staging|production]
   - Runs make tofu-drift ENV=<env>
   - Prints human-readable diff summary from the plan output

   lv3 vm <create|destroy|resize|list>
   - create: runs make remote-tofu-apply ENV=production (or staging)
   - destroy: prompts for confirmation; runs targeted tofu destroy
   - resize: opens tofu/environments/<env>/main.tf in $EDITOR
   - list: calls Proxmox API and prints VM table

   lv3 secret get <path>
   - Calls OpenBao: GET /v1/<path> over Tailscale, prints the secret value
   lv3 secret rotate <path>
   - Triggers the matching Windmill secret-rotation workflow

   lv3 fixture <up|down> [<fixture-name>]
   - Runs make fixture-up FIXTURE=<name> or fixture-down

   lv3 scaffold <service-name>
   - Runs make scaffold-service SERVICE=<name>

   lv3 promote <adr-branch> [--to staging|production]
   - Triggers Windmill deploy-and-promote workflow

   lv3 run <workflow> [--args key=val ...]
   - Calls Windmill API to trigger a workflow by name

   lv3 logs <service> [--tail N] [--since 10m|2h|1d]
   - Calls Loki API with label filter {service="<name>"}
   - Converts --since to a Loki start timestamp

   lv3 ssh <vm-name>
   - Resolves the VM's Tailscale IP from inventory/<vm>.yml
   - Execs: ssh ops@<ip>

   lv3 open <service>
   - Looks up the service URL in the catalog
   - Calls: python3 -m webbrowser <url>

   lv3 --install-completion bash|zsh
   - Writes click shell completion to ~/.bashrc or ~/.zshrc

2. pyproject.toml  (create or update)
   [project]
   name = "lv3-platform-cli"
   version = "0.1.0"
   dependencies = ["click>=8.1"]
   [project.scripts]
   lv3 = "scripts.lv3_cli:cli"

3. Append to Makefile:
   ## Platform CLI (ADR 0090)
   - install-cli    (pipx install --editable . --force)
   - update-cli     (same as install-cli; alias for convenience)
   Update setup target to call install-cli.

4. docs/runbooks/platform-cli.md
   - Installation, one-page command reference, 5 worked examples

Verification before committing:
- python3 -m py_compile scripts/lv3_cli.py
- python3 scripts/lv3_cli.py --help            (prints all command groups)
- python3 scripts/lv3_cli.py status --help     (prints status flags)
- python3 scripts/lv3_cli.py deploy --dry-run grafana
  (prints the ansible command; does not execute it)

Commit to codex/adr-0090-platform-cli:
"Implement ADR 0090: unified lv3 CLI with 14 command groups"
```

---

## PROMPT 9 — ADR 0088: Ephemeral Infrastructure Fixtures
> **Lane B · Step 3 · Requires PROMPTS 6 and 7 merged**

```
You are implementing ADR 0088 in the proxmox_florin_server repo.

Read these files before writing anything:
- docs/adr/0088-ephemeral-infrastructure-fixtures.md
- docs/workstreams/adr-0088-ephemeral-fixtures.md
- tofu/modules/proxmox-vm/  (written in PROMPT 7 — reuse this module)
- tofu/environments/staging/ (understand the staging environment structure)
- config/vm-template-manifest.json

Create exactly these files:

1. tofu/modules/proxmox-fixture/main.tf
   - Wraps tofu/modules/proxmox-vm
   - Adds: lifetime_minutes variable (int, required)
   - Adds: vmid_range_start and vmid_range_end variables (defaults 9100, 9199)
   - Sets bridge = "vmbr20" and ip range from 10.20.10.0/24 as defaults
   - lifecycle { prevent_destroy = false }  (fixtures MUST be destroyable)

2. tofu/modules/proxmox-fixture/variables.tf  + outputs.tf

3. tests/fixtures/docker-host-fixture.yml
   fixture_id: docker-host
   template: lv3-docker-host
   vmid_range: [9100, 9199]
   network: { bridge: vmbr20, ip_cidr: 10.20.10.100/24, gateway: 10.20.10.1 }
   resources: { cores: 2, memory_mb: 2048, disk_gb: 20 }
   lifetime_minutes: 120
   tags: [ephemeral, fixture]
   roles_under_test: [lv3.platform.docker_runtime]
   verify:
     - url: http://10.20.10.100:9000
       expected_status: 200
       timeout_seconds: 60

4. tests/fixtures/postgres-host-fixture.yml
   (same pattern; template: lv3-postgres-host, port 5432 TCP probe)

5. tests/fixtures/ops-base-fixture.yml
   (same pattern; template: lv3-ops-base, SSH probe)

6. scripts/vmid_allocator.py
   - Calls Proxmox API to list all VMIDs in use
   - Scans range 9100–9199 and returns the first free slot
   - Writes a lock file /tmp/vmid-<slot>.lock for 60 seconds (race prevention)
   - CLI: python3 scripts/vmid_allocator.py --range 9100:9199 → prints a free VMID

7. scripts/fixture_manager.py
   - Commands: up <fixture-name>, down <fixture-name>, list
   - up: reads tests/fixtures/<name>.yml, calls vmid_allocator.py,
     runs tofu apply with the fixture module,
     waits for SSH readiness (max 120s),
     runs the roles_under_test Ansible roles,
     runs the verify health checks,
     writes receipt to receipts/fixtures/<name>-<timestamp>.json
   - down: reads the matching receipt, runs tofu destroy for the VMID,
     deletes the receipt
   - list: prints all active fixture receipts with age and health

8. config/windmill/scripts/fixture-expiry-reaper.py
   - Reads all files in receipts/fixtures/
   - For each: parse created_at + lifetime_minutes; if expired, call fixture down
   - Writes .local/fixtures/reaper-runs/reaper-run-<timestamp>.json with summary

9. molecule/drivers/proxmox-fixture/  (custom Molecule driver)
   - Create: (create.yml) calls scripts/fixture_manager.py up
   - Destroy: (destroy.yml) calls scripts/fixture_manager.py down
   - Sets MOLECULE_FIXTURE_IP from the receipt

10. receipts/fixtures/.gitkeep

11. Append to Makefile:
    ## Ephemeral fixtures (ADR 0088)
    - fixture-up    FIXTURE=    (calls scripts/fixture_manager.py up)
    - fixture-down  FIXTURE=    (calls scripts/fixture_manager.py down)
    - fixture-list              (calls scripts/fixture_manager.py list)

12. docs/runbooks/ephemeral-fixtures.md

Verification before committing:
- python3 -m py_compile scripts/vmid_allocator.py
- python3 -m py_compile scripts/fixture_manager.py
- python3 scripts/fixture_manager.py list   (prints "No active fixtures" on a clean repo)
- python3 -c "import yaml; yaml.safe_load(open('tests/fixtures/docker-host-fixture.yml'))"

Commit to codex/adr-0088-ephemeral-fixtures:
"Implement ADR 0088: ephemeral fixture VMs with Windmill expiry reaper and Molecule driver"
```

---

## PROMPT 10 — ADR 0091: Continuous Drift Detection
> **Lane D · Final · Requires PROMPTS 7 (OpenTofu), 3 (NATS via ADR 0058), and ADR 0074 (ops portal) merged**

```
You are implementing ADR 0091 in the proxmox_florin_server repo.

Read these files before writing anything:
- docs/adr/0091-continuous-drift-detection.md
- docs/workstreams/adr-0091-drift-detection.md
- config/service-capability-catalog.json    (list of services to probe)
- config/subdomain-catalog.json             (DNS entries to check)
- workstreams.yaml                           (for workstream-aware suppression)
- tofu/environments/production/main.tf      (VM declarations to check against)

Create exactly these files:

1. scripts/parse_ansible_drift.py
   - Parses the stdout of `ansible-playbook --check --diff`
   - Extracts per-host, per-role, per-task changes into structured dicts
   - Returns a list of DriftRecord objects:
       { host, role, task, diff_before, diff_after, severity: "warn" }
   - If a connection error occurs, returns a DriftRecord with type "unreachable"
   - CLI: python3 scripts/parse_ansible_drift.py < ansible-check-output.txt

2. scripts/docker_image_drift.py
   - For each service in config/service-capability-catalog.json that has
     an expected_image_digest field:
     - SSH to the service's VM (via Tailscale)
     - Run: docker inspect <container_name> | jq '.[0].Image'
     - Compare to catalog expected_image_digest
     - Emit DriftRecord if different
   - Uses concurrent SSH calls (ThreadPoolExecutor, max_workers=4)

3. scripts/dns_drift.py
   - For each entry in config/subdomain-catalog.json:
     - DNS query (use dnspython) for the declared record type and value
     - Compare to declared value
     - Emit DriftRecord if missing or wrong

4. scripts/tls_cert_drift.py
   - For each service URL in config/service-capability-catalog.json:
     - Open TLS connection, extract certificate expiry and issuer
     - If expiry < 14 days: severity = "warn"
     - If expiry < 7 days: severity = "critical"
     - If issuer doesn't match catalog expected_issuer field: severity = "warn"

5. scripts/drift_detector.py
   - Orchestrates all five drift sources:
     1. tofu plan -detailed-exitcode (subprocess call to make tofu-drift ENV=production)
     2. ansible-playbook --check --diff site.yml (piped to parse_ansible_drift.py)
     3. docker_image_drift.py
     4. dns_drift.py
     5. tls_cert_drift.py
   - For each DriftRecord:
     - Check workstreams.yaml: if any workstream status=in_progress has the
       affected service in shared_surfaces, set workstream_suppressed=true
     - If NOT suppressed AND severity=warn: publish NATS event platform.drift.warn
     - If NOT suppressed AND severity=critical: publish NATS event platform.drift.critical
   - Writes receipts/drift-reports/<timestamp>.json with all DriftRecords
   - Prints a summary table: SOURCE | RESOURCE | SEVERITY | SUPPRESSED | DETAIL
   - Exits 0 if no unsuppressed errors, 1 if critical drift found

   NATS event format:
   { "event": "platform.drift.<severity>", "source": "<detector>",
     "service": "<name>", "detail": "...", "detected_at": "<iso>",
     "workstream_suppressed": false }

6. config/windmill/scripts/continuous-drift-detection.py
   - Windmill script: runs scripts/drift_detector.py on the build server
     via make remote-exec, reads the receipt, publishes a summary NATS event
     platform.drift.run-complete with total counts per severity

7. Update config/grafana/dashboards/platform-overview.json
   - Add a "Drift Status" panel that queries the last drift-run receipt
     and shows: green (0 unsuppressed), yellow (warn-only), red (critical)
   - If this JSON file does not exist, create a minimal dashboard JSON
     with just the Drift Status panel and a note to import it

8. receipts/drift-reports/.gitkeep

9. Append to Makefile:
   ## Drift detection (ADR 0091)
   - drift-report  ENV=   (runs scripts/drift_detector.py for the given env)

10. docs/runbooks/drift-detection.md
    - How to read a drift report
    - How to resolve each drift type (OpenTofu: edit main.tf and apply;
      Ansible: re-run the playbook; image: redeploy the service;
      DNS: re-provision subdomain; TLS: trigger certificate renewal)
    - How workstream suppression works and how to override it

Verification before committing:
- python3 -m py_compile scripts/drift_detector.py
- python3 -m py_compile scripts/parse_ansible_drift.py
- python3 -m py_compile scripts/docker_image_drift.py
- python3 -m py_compile scripts/dns_drift.py
- python3 -m py_compile scripts/tls_cert_drift.py
- echo "" | python3 scripts/parse_ansible_drift.py  (empty input → empty list, exit 0)
- python3 scripts/drift_detector.py --help          (prints usage)

Commit to codex/adr-0091-drift-detection:
"Implement ADR 0091: continuous drift detection across 5 sources with NATS events"
```

---

## After All 10 Prompts: Final Integration Prompt

```
You are doing final integration after all ADRs 0082–0091 have been implemented
and their branches merged to main.

Read these files:
- docs/runbooks/plan-iac-potency-and-build-server.md  (success criteria)
- Makefile  (verify all new targets are present)
- scripts/  (verify all new scripts are present)

Run the success criteria checklist from the roadmap runbook:

1. make check-build-server           → must pass
2. make remote-lint                  → must complete in < 20s (warm cache)
3. make validate-packer              → must pass for all 4 templates
4. make tofu-drift ENV=production    → must exit 0
5. python3 scripts/lv3_cli.py status → must print a health table
6. python3 scripts/lv3_cli.py diff --env production → must show no critical drift
7. make pre-push-gate                → must pass on main
8. make fixture-list                 → must print "No active fixtures"
9. ansible-galaxy collection build collections/lv3/platform/ → must produce tar.gz

Then:
- Update docs/adr/0082 through 0091: change Status from "Proposed" to "Accepted"
  and Implementation Status from "Not Implemented" to "Implemented"
  (fill in the Implemented In Repo Version as 0.51.0 and today's date)
- Bump VERSION to 0.52.0
- Add a 0.52.0 entry to changelog.md summarising: all 10 ADRs now implemented
- Commit to main: "Mark ADRs 0082-0091 as implemented; bump to 0.52.0"
```

---

## Quick Reference Card

| Prompt | ADR | Effort | After which prompt |
|---|---|---|---|
| 1 | 0082 Remote Build Gateway | 4 h | — (first) |
| 2 | 0083 Docker Check Runner | 6 h | after 1 |
| 3 | 0089 Build Cache | 3 h | after 2 |
| 4 | 0087 Validation Gate | 4 h | after 3 (parallel with 5, 6) |
| 5 | 0086 Ansible Collections | 10 h | after 3 (parallel with 4, 6) |
| 6 | 0084 Packer Pipeline | 8 h | after 3 (parallel with 4, 5) |
| 7 | 0085 OpenTofu VM Lifecycle | 8 h | after 6 |
| 8 | 0090 Platform CLI | 6 h | after 1 (parallel with 4, 5, 6) |
| 9 | 0088 Ephemeral Fixtures | 5 h | after 7 |
| 10 | 0091 Drift Detection | 6 h | after 7 + NATS live |
| — | Final integration | 1 h | after all 10 |
