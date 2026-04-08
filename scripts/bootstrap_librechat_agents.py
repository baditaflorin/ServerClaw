#!/usr/bin/env python3
"""Bootstrap LibreChat agents with platform tool packs via MongoDB.

Creates pre-configured ServerClaw agents directly in LibreChat's MongoDB
so users get tool-calling agents out of the box with zero manual setup.

This script connects via SSH to the Docker host and runs mongosh commands
inside the librechat-mongodb container.

Usage (from Ansible):
    python3 scripts/bootstrap_librechat_agents.py \
        --ssh-target root@10.10.10.70 \
        --ssh-key .local/ssh/bootstrap.id_ed25519 \
        --ssh-proxy root@10.10.10.1 \
        --admin-email ops@lv3.org \
        --system-prompt-file config/serverclaw/system-prompt.md

Idempotent: skips agents that already exist (matched by stable id).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

AGENT_PACKS = [
    {
        "id": "agent_serverclaw_ops",
        "name": "ServerClaw Ops",
        "description": "Infrastructure observability — platform status, containers, logs, deployments, maintenance windows.",
        "specialty": "You specialize in infrastructure observability — checking platform status, listing containers, reading logs, and reviewing deployment history.",
        "model": "claude-sonnet-4-6-20250725",
        "provider": "anthropic",
        "conversation_starters": [
            "What's the current platform status?",
            "Show me running containers",
            "What was deployed recently?",
            "Are there any maintenance windows?",
        ],
    },
    {
        "id": "agent_serverclaw_tasks",
        "name": "ServerClaw Tasks",
        "description": "Project management — create, view, update Plane tasks and comments.",
        "specialty": "You specialize in project management using Plane. You can list, create, update tasks and add comments.",
        "model": "claude-sonnet-4-6-20250725",
        "provider": "anthropic",
        "conversation_starters": [
            "List my open tasks",
            "Create a new task for fixing the DNS issue",
            "What's the status of the deployment task?",
        ],
    },
    {
        "id": "agent_serverclaw_docs",
        "name": "ServerClaw Docs",
        "description": "Knowledge base — search, read, and manage Outline wiki documents and collections.",
        "specialty": "You specialize in knowledge management using Outline wiki. You can search, read, create, and update documents and collections.",
        "model": "claude-sonnet-4-6-20250725",
        "provider": "anthropic",
        "conversation_starters": [
            "Search the wiki for deployment procedures",
            "List all document collections",
            "Show me the runbook for Keycloak",
        ],
    },
    {
        "id": "agent_serverclaw_admin",
        "name": "ServerClaw Admin",
        "description": "Governed operations — execute commands, manage Nomad jobs, approval workflows. Elevated access required.",
        "specialty": "You specialize in governed operations and platform administration. You can execute governed commands, manage Nomad jobs, and check approval workflows.",
        "model": "claude-sonnet-4-6-20250725",
        "provider": "anthropic",
        "conversation_starters": [
            "List available governed commands",
            "Show Nomad job status",
            "What workflows are available?",
        ],
    },
]


def build_mongosh_script(admin_email: str, system_prompt: str) -> str:
    """Build a mongosh script that seeds agents idempotently."""
    # Escape for JS string literal
    prompt_escaped = system_prompt.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

    agents_js = []
    for pack in AGENT_PACKS:
        starters = json.dumps(pack["conversation_starters"])
        # Build actions array with tool specs from /tools-openapi/
        tool_pack_id = pack["id"].replace("agent_serverclaw_", "")  # e.g., "ops" from "agent_serverclaw_ops"
        actions_js = json.dumps([
            {
                "name": f"{tool_pack_id}_tools",
                "url": f"/tools-openapi/{tool_pack_id}.openapi.json",
                "auth_required": False
            }
        ])
        agents_js.append(f"""  {{
    id: "{pack['id']}",
    author: userId,
    name: "{pack['name']}",
    description: "{pack['description']}",
    instructions: systemPrompt + "\\n\\n## Your Specialty\\n\\n{pack['specialty']}",
    model: "{pack['model']}",
    provider: "{pack['provider']}",
    actions: {actions_js},
    conversation_starters: {starters},
    isCollaborative: true,
    enableActions: true,
    createdAt: now,
    updatedAt: now
  }}""")

    agents_array = ",\n".join(agents_js)

    return f"""
db = db.getSiblingDB("LibreChat");
var user = db.users.findOne({{email: "{admin_email}"}});
if (!user) {{
  print("ERROR: admin user {admin_email} not found");
  quit(1);
}}
var userId = user._id;
var now = new Date();
var systemPrompt = "{prompt_escaped}";

var agents = [
{agents_array}
];

var inserted = 0;
var updated = 0;
var skipped = 0;
agents.forEach(function(agent) {{
  var existing = db.agents.findOne({{id: agent.id}});
  if (!existing) {{
    db.agents.insertOne(agent);
    inserted++;
    print("Creating " + agent.name);
  }} else {{
    // Update actions and instructions in case they changed
    db.agents.updateOne(
      {{id: agent.id}},
      {{
        $set: {{
          actions: agent.actions,
          instructions: agent.instructions,
          conversation_starters: agent.conversation_starters,
          enableActions: agent.enableActions,
          updatedAt: now
        }}
      }}
    );
    updated++;
    print("Updated " + agent.name);
  }}
}});

// Enable SHARED_GLOBAL permissions so all users see agents
db.roles.updateOne({{name: "ADMIN"}}, {{$set: {{"permissions.AGENTS.SHARED_GLOBAL": true}}}});
db.roles.updateOne({{name: "USER"}}, {{$set: {{"permissions.AGENTS.SHARED_GLOBAL": true}}}});

print("Done. Created " + inserted + ", updated " + updated + ", skipped " + skipped + ".");
"""


def run_mongosh(
    script: str,
    ssh_target: str,
    ssh_key: str,
    ssh_proxy: str | None = None,
    mongo_container: str = "librechat-mongodb",
) -> tuple[int, str]:
    """Execute a mongosh script inside the MongoDB container via SSH."""
    # Build SSH command
    ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10"]
    if ssh_key:
        ssh_cmd.extend(["-i", ssh_key])
    if ssh_proxy:
        ssh_cmd.extend(["-o", f"ProxyJump={ssh_proxy}"])
    ssh_cmd.append(ssh_target)

    # Escape the script for shell
    escaped = script.replace("'", "'\\''")
    remote_cmd = f"docker exec {mongo_container} mongosh --eval '{escaped}'"
    ssh_cmd.append(remote_cmd)

    result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=60)
    output = result.stdout + result.stderr
    return result.returncode, output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ssh-target", required=True, help="SSH target (e.g., root@10.10.10.70)")
    parser.add_argument("--ssh-key", default="", help="SSH private key path")
    parser.add_argument("--ssh-proxy", default="", help="SSH proxy jump (e.g., root@10.10.10.1)")
    parser.add_argument("--admin-email", default="ops@lv3.org", help="Admin email in LibreChat")
    parser.add_argument("--system-prompt-file", default="config/serverclaw/system-prompt.md", help="System prompt file")
    parser.add_argument("--mongo-container", default="librechat-mongodb", help="MongoDB container name")
    parser.add_argument("--dry-run", action="store_true", help="Print mongosh script without executing")
    args = parser.parse_args()

    system_prompt = Path(args.system_prompt_file).read_text().strip()
    script = build_mongosh_script(args.admin_email, system_prompt)

    if args.dry_run:
        print(script)
        return 0

    print(f"Bootstrapping agents via {args.ssh_target}...")
    rc, output = run_mongosh(
        script,
        ssh_target=args.ssh_target,
        ssh_key=args.ssh_key,
        ssh_proxy=args.ssh_proxy or None,
        mongo_container=args.mongo_container,
    )

    # Print output lines
    for line in output.strip().split("\n"):
        if line.strip():
            print(f"  {line.strip()}")

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
