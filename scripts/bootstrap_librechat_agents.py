#!/usr/bin/env python3
"""Bootstrap LibreChat agents with platform tool packs via MongoDB.

Creates pre-configured ServerClaw agents directly in LibreChat's MongoDB
so users get tool-calling agents out of the box with zero manual setup.

This script:
  1. Creates Action documents in the `actions` collection (one per tool pack)
  2. Creates Agent documents in the `agents` collection with proper tool references
  3. Wires agents to actions using LibreChat's internal naming convention:
     {operationId}_action_{base64EncodedDomain}

This matches the exact schema that LibreChat's UI-based action creator uses,
so agents appear with fully functional tool calling.

All connection details, paths, and addresses are passed as CLI arguments
by the Ansible task in librechat_runtime/tasks/main.yml. This script has
NO hardcoded IPs or paths — the Ansible role defaults are the single
source of truth.

Idempotent: updates agents and actions that already exist.
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
from pathlib import Path

# LibreChat internal constants (from packages/data-provider/src/types/assistants.ts)
ACTION_DELIMITER = "_action_"
ACTION_DOMAIN_SEPARATOR = "---"
ENCODED_DOMAIN_LENGTH = 10

AGENT_PACKS = [
    {
        "id": "agent_serverclaw_ops",
        "name": "ServerClaw Ops",
        "description": "Infrastructure observability and host execution — platform status, containers, logs, deployments, disk usage, and shell commands on any platform host.",
        "specialty": "You specialize in infrastructure observability and host-level diagnostics. You can check platform status, list containers, read logs, review deployment history, AND execute shell commands on any platform host (runtime-control, proxmox, docker-runtime, postgres, build-server, coolify, runtime-comms). When users ask about disk space, memory, CPU, network, or any system-level information — use the execute-host-command tool to run the appropriate command (df -h, free -m, top -bn1, ip addr, etc.) on the relevant host. You also have a dedicated get-disk-usage tool for quick disk space checks. Always prefer running actual commands over saying you can't check.",
        "model": "claude-sonnet-4-6-20250725",
        "provider": "anthropic",
        "tool_pack": "ops",
        "conversation_starters": [
            "What's the disk space status across all VMs?",
            "Show me running containers",
            "Check memory usage on docker-runtime",
            "What was deployed recently?",
        ],
    },
    {
        "id": "agent_serverclaw_tasks",
        "name": "ServerClaw Tasks",
        "description": "Project management — create, view, update Plane tasks and comments.",
        "specialty": "You specialize in project management using Plane. You can list, create, update tasks and add comments. You have tools to interact with the Plane API directly.",
        "model": "claude-sonnet-4-6-20250725",
        "provider": "anthropic",
        "tool_pack": "tasks",
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
        "specialty": "You specialize in knowledge management using Outline wiki. You can search, read, create, and update documents and collections. You have tools for direct wiki API access.",
        "model": "claude-sonnet-4-6-20250725",
        "provider": "anthropic",
        "tool_pack": "docs",
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
        "specialty": "You specialize in governed operations and platform administration. You can execute governed commands, manage Nomad jobs, and check approval workflows. You have tools with direct API access.",
        "model": "claude-sonnet-4-6-20250725",
        "provider": "anthropic",
        "tool_pack": "admin",
        "conversation_starters": [
            "List available governed commands",
            "Show Nomad job status",
            "What workflows are available?",
        ],
    },
]


def encode_domain(domain: str) -> str:
    """Encode a domain using LibreChat's domainParser logic.

    Short domains (<=10 chars): replace dots with '---'
    Long domains (>10 chars): base64 encode and truncate to 10 chars
    """
    # Strip protocol if present
    for prefix in ("https://", "http://"):
        if domain.startswith(prefix):
            domain = domain[len(prefix) :]
            break

    if len(domain) <= ENCODED_DOMAIN_LENGTH:
        return domain.replace(".", ACTION_DOMAIN_SEPARATOR)

    b64 = base64.b64encode(domain.encode()).decode()
    return b64[:ENCODED_DOMAIN_LENGTH]


def extract_operation_ids(spec_path: Path) -> list[str]:
    """Extract operationIds from an OpenAPI spec file."""
    spec = json.loads(spec_path.read_text())
    ops = []
    for path_obj in spec.get("paths", {}).values():
        for method_obj in path_obj.values():
            if isinstance(method_obj, dict) and "operationId" in method_obj:
                ops.append(method_obj["operationId"])
    return ops


def build_mongosh_script(
    admin_email: str,
    system_prompt: str,
    specs_dir: Path,
    gateway_base_url: str,
    tools_api_key: str,
) -> str:
    """Build a mongosh script that seeds agents and actions idempotently."""
    # Escape for JS string literal
    prompt_escaped = system_prompt.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")

    # Compute encoded domain for tool name references
    encoded_domain = encode_domain(gateway_base_url)
    # Raw domain without protocol for Action.metadata.domain
    # IMPORTANT: must be hostname only (no port), because LibreChat's
    # validateActionDomain compares metadata.domain against
    # new URL(specServerUrl).hostname, which strips the port.
    raw_domain = gateway_base_url
    for prefix in ("https://", "http://"):
        if raw_domain.startswith(prefix):
            raw_domain = raw_domain[len(prefix) :]
            break
    # Strip port — LibreChat's URL parser removes it during validation
    if ":" in raw_domain:
        raw_domain = raw_domain.rsplit(":", 1)[0]

    # Build actions and agents JS
    actions_js_parts = []
    agents_js_parts = []

    for pack in AGENT_PACKS:
        spec_file = specs_dir / f"{pack['tool_pack']}.openapi.json"
        if not spec_file.exists():
            print(f"WARNING: spec file not found: {spec_file}, skipping {pack['name']}")
            continue

        operation_ids = extract_operation_ids(spec_file)
        raw_spec = spec_file.read_text()
        raw_spec_escaped = raw_spec.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")

        action_id = f"action_{pack['tool_pack']}_tools"

        # Build tool name strings: {operationId}_action_{encodedDomain}
        tool_names = [f"{op_id}{ACTION_DELIMITER}{encoded_domain}" for op_id in operation_ids]
        tool_names_js = json.dumps(tool_names)

        starters = json.dumps(pack["conversation_starters"])

        # Action document — LibreChat queries by agent_id for agents endpoint,
        # and by assistant_id for assistants endpoint. Set both for compatibility.
        actions_js_parts.append(f"""  {{
    action_id: "{action_id}",
    agent_id: "{pack["id"]}",
    assistant_id: "{pack["id"]}",
    type: "action_prototype",
    metadata: {{
      domain: "{raw_domain}",
      raw_spec: "{raw_spec_escaped}",
      auth: {{
        type: "service_http",
        authorization_type: "custom",
        custom_auth_header: "X-LV3-Dify-Api-Key"
      }}
    }}
  }}""")

        # Agent document — must match LibreChat v0.8.4 Mongoose schema exactly.
        # Missing fields (versions, model_parameters, category, etc.) cause agents
        # to be invisible in the UI even though they exist in MongoDB.
        agents_js_parts.append(f"""  {{
    id: "{pack["id"]}",
    author: userId,
    name: "{pack["name"]}",
    description: "{pack["description"]}",
    instructions: systemPrompt + "\\n\\n## Your Specialty\\n\\n{pack["specialty"]}",
    model: "{pack["model"]}",
    provider: "{pack["provider"]}",
    model_parameters: {{}},
    artifacts: "",
    tools: {tool_names_js},
    tool_kwargs: [],
    actions: ["{action_id}"],
    agent_ids: [],
    edges: [],
    conversation_starters: {starters},
    projectIds: [],
    category: "general",
    support_contact: {{name: "", email: ""}},
    is_promoted: false,
    isCollaborative: false,
    isPublic: true,
    mcpServerNames: [],
    tool_options: {{}},
    version: 1,
    versions: [{{
      name: "{pack["name"]}",
      description: "{pack["description"]}",
      model_parameters: {{}},
      agent_ids: [],
      edges: [],
      artifacts: "",
      support_contact: {{name: "", email: ""}},
      category: "general",
      provider: "{pack["provider"]}",
      model: "{pack["model"]}",
      id: "{pack["id"]}",
      tools: {tool_names_js},
      createdAt: now,
      updatedAt: now
    }}],
    createdAt: now,
    updatedAt: now
  }}""")

    actions_array = ",\n".join(actions_js_parts)
    agents_array = ",\n".join(agents_js_parts)

    # Escape tools_api_key for JS
    api_key_escaped = tools_api_key.replace("\\", "\\\\").replace('"', '\\"')

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
var apiKey = "{api_key_escaped}";

// --- Actions (tool pack OpenAPI specs) ---
var actionDefs = [
{actions_array}
];

// Ensure both agent_id and assistant_id exist on all actions.
// Agents endpoint queries by agent_id; assistants endpoint by assistant_id.
db.actions.updateMany(
  {{agent_id: {{$exists: true}}, assistant_id: {{$exists: false}}}},
  [{{$set: {{assistant_id: "$agent_id"}}}}]
);
db.actions.updateMany(
  {{assistant_id: {{$exists: true}}, agent_id: {{$exists: false}}}},
  [{{$set: {{agent_id: "$assistant_id"}}}}]
);

var actionsCreated = 0;
var actionsUpdated = 0;
actionDefs.forEach(function(actionDef) {{
  // Encrypt API key into metadata
  actionDef.metadata.api_key = apiKey;
  actionDef.user = userId;

  var existing = db.actions.findOne({{action_id: actionDef.action_id}});
  if (!existing) {{
    db.actions.insertOne(actionDef);
    actionsCreated++;
    print("Creating action " + actionDef.action_id);
  }} else {{
    db.actions.updateOne(
      {{action_id: actionDef.action_id}},
      {{$set: {{
        metadata: actionDef.metadata,
        agent_id: actionDef.agent_id,
        assistant_id: actionDef.assistant_id,
        user: userId
      }}}}
    );
    actionsUpdated++;
    print("Updated action " + actionDef.action_id);
  }}
}});

// --- Agents ---
var agents = [
{agents_array}
];

var agentsCreated = 0;
var agentsUpdated = 0;
agents.forEach(function(agent) {{
  var existing = db.agents.findOne({{id: agent.id}});
  if (!existing) {{
    db.agents.insertOne(agent);
    agentsCreated++;
    print("Creating " + agent.name);
  }} else {{
    db.agents.updateOne(
      {{id: agent.id}},
      {{$set: {{
        author: agent.author,
        tools: agent.tools,
        actions: agent.actions,
        instructions: agent.instructions,
        conversation_starters: agent.conversation_starters,
        model_parameters: agent.model_parameters,
        artifacts: agent.artifacts,
        tool_kwargs: agent.tool_kwargs,
        agent_ids: agent.agent_ids,
        edges: agent.edges,
        projectIds: agent.projectIds,
        category: agent.category,
        support_contact: agent.support_contact,
        is_promoted: agent.is_promoted,
        isCollaborative: agent.isCollaborative,
        isPublic: agent.isPublic,
        mcpServerNames: agent.mcpServerNames,
        tool_options: agent.tool_options,
        version: agent.version,
        versions: agent.versions,
        updatedAt: now
      }}}}
    );
    agentsUpdated++;
    print("Updated " + agent.name);
  }}
}});

// Enable SHARED_GLOBAL permissions so all users see agents
db.roles.updateOne({{name: "ADMIN"}}, {{$set: {{"permissions.AGENTS.SHARED_GLOBAL": true, "permissions.AGENTS.USE": true, "permissions.AGENTS.CREATE": true}}}});
db.roles.updateOne({{name: "USER"}}, {{$set: {{"permissions.AGENTS.SHARED_GLOBAL": true, "permissions.AGENTS.USE": true}}}});

// Register agents in the instance project for global visibility
db.projects.updateOne(
  {{name: "instance"}},
  {{$addToSet: {{agentIds: {{$each: agents.map(function(a) {{ return a.id; }})}}}}}}
);

// --- ACL Entries ---
// LibreChat v0.8.4 uses an ACL system for agent visibility.
// Without ACL entries, agents exist in MongoDB but are invisible via the API.
// Create PUBLIC view entries (all users can see) and OWNER entries (author can edit).
var viewerRole = db.accessroles.findOne({{name: "com_ui_role_viewer", resourceType: "agent"}});
var ownerRole = db.accessroles.findOne({{name: "com_ui_role_owner", resourceType: "agent"}});

if (viewerRole && ownerRole) {{
  var aclCreated = 0;
  agents.forEach(function(agent) {{
    var agentDoc = db.agents.findOne({{id: agent.id}});
    if (!agentDoc) return;

    // PUBLIC view access — so all users can see the agent
    var pubResult = db.aclentries.updateOne(
      {{resourceId: agentDoc._id, resourceType: "agent", principalType: "public"}},
      {{$set: {{
        resourceId: agentDoc._id,
        resourceType: "agent",
        principalType: "public",
        principalId: "public",
        principalModel: "Public",
        permBits: viewerRole.permBits,
        roleId: viewerRole._id,
        grantedBy: userId,
        grantedAt: now,
        __v: 0,
        createdAt: now,
        updatedAt: now
      }}}},
      {{upsert: true}}
    );
    if (pubResult.upsertedCount > 0) aclCreated++;

    // OWNER access for the admin user
    var ownResult = db.aclentries.updateOne(
      {{resourceId: agentDoc._id, resourceType: "agent", principalType: "user", principalId: userId}},
      {{$set: {{
        resourceId: agentDoc._id,
        resourceType: "agent",
        principalType: "user",
        principalId: userId,
        principalModel: "User",
        permBits: ownerRole.permBits,
        roleId: ownerRole._id,
        grantedBy: userId,
        grantedAt: now,
        __v: 0,
        createdAt: now,
        updatedAt: now
      }}}},
      {{upsert: true}}
    );
    if (ownResult.upsertedCount > 0) aclCreated++;
  }});
  print("ACL entries: " + aclCreated + " created");
}} else {{
  print("WARNING: access roles not found, skipping ACL entries");
}}

// Ensure all agents have Mongoose __v field (required for API queries)
db.agents.updateMany(
  {{__v: {{$exists: false}}}},
  {{$set: {{__v: 0}}}}
);

print("Done. Actions: " + actionsCreated + " created, " + actionsUpdated + " updated. Agents: " + agentsCreated + " created, " + agentsUpdated + " updated.");
"""


def run_mongosh(
    script: str,
    ssh_target: str,
    ssh_key: str,
    ssh_proxy: str | None = None,
    mongo_container: str = "librechat-mongodb",
) -> tuple[int, str]:
    """Execute a mongosh script inside the MongoDB container via SSH."""
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

    result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=120)
    output = result.stdout + result.stderr
    return result.returncode, output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    # All values supplied by the Ansible task — no hardcoded defaults for
    # IPs, paths, or credentials.  The role defaults in
    # librechat_runtime/defaults/main.yml are the single source of truth.
    parser.add_argument("--ssh-target", required=True, help="SSH target, e.g. root@<host>")
    parser.add_argument("--ssh-key", required=True, help="SSH private key path")
    parser.add_argument("--ssh-proxy", default="", help="SSH proxy jump host")
    parser.add_argument("--admin-email", required=True, help="Admin email in LibreChat")
    parser.add_argument("--system-prompt-file", required=True, help="System prompt markdown file")
    parser.add_argument("--specs-dir", required=True, help="Directory with tool pack OpenAPI spec files")
    parser.add_argument("--gateway-base-url", required=True, help="API gateway base URL for tool calls")
    parser.add_argument("--tools-api-key-file", required=True, help="Path to tools API key file")
    parser.add_argument("--mongo-container", required=True, help="MongoDB container name")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print mongosh script without executing",
    )
    args = parser.parse_args()

    system_prompt = Path(args.system_prompt_file).read_text().strip()
    specs_dir = Path(args.specs_dir)

    # Read tools API key
    tools_api_key = ""
    if args.tools_api_key_file:
        key_path = Path(args.tools_api_key_file)
        if key_path.exists():
            tools_api_key = key_path.read_text().strip()
        else:
            print(f"WARNING: tools API key file not found: {key_path}")

    script = build_mongosh_script(
        admin_email=args.admin_email,
        system_prompt=system_prompt,
        specs_dir=specs_dir,
        gateway_base_url=args.gateway_base_url,
        tools_api_key=tools_api_key,
    )

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

    for line in output.strip().split("\n"):
        if line.strip():
            print(f"  {line.strip()}")

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
