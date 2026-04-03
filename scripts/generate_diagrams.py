#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from controller_automation_toolkit import emit_cli_error, load_json, load_yaml, repo_path
from platform.workstream_registry import load_registry as load_workstream_registry


HOST_VARS_PATH = repo_path("inventory", "host_vars", "proxmox_florin.yml")
DEPENDENCY_GRAPH_PATH = repo_path("config", "dependency-graph.json")
OUTPUT_DIR = repo_path("docs", "diagrams")


def _element_id(*parts: str) -> str:
    return hashlib.sha1("::".join(parts).encode("utf-8")).hexdigest()[:16]


def _base_element(element_id: str, element_type: str, *, x: int, y: int, width: int, height: int) -> dict[str, Any]:
    return {
        "id": element_id,
        "type": element_type,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "angle": 0,
        "strokeColor": "#1f2933",
        "backgroundColor": "#f8fafc",
        "fillStyle": "solid",
        "strokeWidth": 2,
        "strokeStyle": "solid",
        "roughness": 1,
        "opacity": 100,
        "groupIds": [],
        "frameId": None,
        "roundness": {"type": 3},
        "seed": 1,
        "version": 1,
        "versionNonce": 1,
        "isDeleted": False,
        "boundElements": [],
        "updated": 0,
        "link": None,
        "locked": False,
    }


def rectangle(label: str, *, x: int, y: int, width: int = 220, height: int = 72, background: str = "#f8fafc") -> list[dict[str, Any]]:
    rect_id = _element_id("rect", label, str(x), str(y))
    text_id = _element_id("text", label, str(x), str(y))
    rect = _base_element(rect_id, "rectangle", x=x, y=y, width=width, height=height)
    rect["backgroundColor"] = background
    text = _base_element(text_id, "text", x=x + 20, y=y + 22, width=width - 40, height=28)
    text.update(
        {
            "backgroundColor": "transparent",
            "strokeWidth": 1,
            "roughness": 0,
            "text": label,
            "fontSize": 20,
            "fontFamily": 1,
            "textAlign": "center",
            "verticalAlign": "middle",
            "baseline": 18,
            "containerId": None,
            "originalText": label,
            "lineHeight": 1.25,
        }
    )
    return [rect, text]


def arrow(label: str, *, x: int, y: int, dx: int, dy: int) -> dict[str, Any]:
    arrow_id = _element_id("arrow", label, str(x), str(y), str(dx), str(dy))
    return {
        **_base_element(arrow_id, "arrow", x=x, y=y, width=dx, height=dy),
        "backgroundColor": "transparent",
        "fillStyle": "hachure",
        "roundness": {"type": 2},
        "points": [[0, 0], [dx, dy]],
        "lastCommittedPoint": None,
        "startBinding": None,
        "endBinding": None,
        "startArrowhead": None,
        "endArrowhead": "triangle",
    }


def scene(elements: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "excalidraw",
        "version": 2,
        "source": "https://draw.lv3.org",
        "elements": elements,
        "appState": {
            "gridSize": None,
            "viewBackgroundColor": "#ffffff",
        },
        "files": {},
    }


def render_network_topology(host_vars: dict[str, Any]) -> dict[str, Any]:
    guests = {guest["name"]: guest for guest in host_vars["proxmox_guests"]}
    elements: list[dict[str, Any]] = []
    elements += rectangle("Public Internet", x=60, y=40, background="#dbeafe")
    elements += rectangle(
        f"proxmox_florin\n{host_vars['management_ipv4']}\nTailscale {host_vars['management_tailscale_ipv4']}",
        x=360,
        y=40,
        height=96,
        background="#e0f2fe",
    )
    elements += rectangle("vmbr0 public uplink", x=360, y=180, background="#fef3c7")
    elements += rectangle(f"vmbr10 guest LAN\n{host_vars['proxmox_internal_network']}", x=360, y=300, background="#dcfce7")
    elements += rectangle(f"nginx-lv3\n{guests['nginx-lv3']['ipv4']}", x=80, y=420, background="#fef9c3")
    elements += rectangle(f"docker-runtime-lv3\n{guests['docker-runtime-lv3']['ipv4']}", x=360, y=420, background="#ede9fe")
    elements += rectangle(f"monitoring-lv3\n{guests['monitoring-lv3']['ipv4']}", x=640, y=420, background="#fee2e2")
    elements += rectangle(f"postgres-lv3\n{guests['postgres-lv3']['ipv4']}", x=920, y=420, background="#fce7f3")
    elements.append(arrow("internet-host", x=280, y=88, dx=80, dy=0))
    elements.append(arrow("host-vmbr0", x=470, y=136, dx=0, dy=44))
    elements.append(arrow("vmbr0-vmbr10", x=470, y=252, dx=0, dy=48))
    elements.append(arrow("vmbr10-nginx", x=430, y=372, dx=-240, dy=48))
    elements.append(arrow("vmbr10-runtime", x=470, y=372, dx=0, dy=48))
    elements.append(arrow("vmbr10-monitoring", x=510, y=372, dx=240, dy=48))
    elements.append(arrow("vmbr10-postgres", x=550, y=372, dx=480, dy=48))
    return scene(elements)


def render_service_dependency_graph(dependency_graph: dict[str, Any]) -> dict[str, Any]:
    nodes = {node["id"]: node for node in dependency_graph["nodes"]}
    excalidraw_edges = [edge for edge in dependency_graph["edges"] if edge["from"] == "excalidraw"]
    ordered_nodes = ["excalidraw"] + [edge["to"] for edge in excalidraw_edges]
    positions = {
        "excalidraw": (400, 220),
        "docker_runtime": (80, 60),
        "nginx_edge": (720, 60),
        "keycloak": (80, 420),
        "homepage": (720, 420),
    }
    colors = {
        "excalidraw": "#ddd6fe",
        "docker_runtime": "#e0f2fe",
        "nginx_edge": "#fef3c7",
        "keycloak": "#fee2e2",
        "homepage": "#dcfce7",
    }
    elements: list[dict[str, Any]] = []
    for service_id in ordered_nodes:
        if service_id not in positions or service_id not in nodes:
            continue
        label = f"{nodes[service_id]['name']}\n{nodes[service_id]['vm']}"
        x, y = positions[service_id]
        elements += rectangle(label, x=x, y=y, height=96, background=colors[service_id])
    elements += rectangle(
        f"Total tracked services\n{len(dependency_graph['nodes'])}",
        x=1040,
        y=220,
        width=200,
        background="#f8fafc",
    )
    for edge in excalidraw_edges:
        start_x, start_y = positions["excalidraw"]
        end_x, end_y = positions[edge["to"]]
        elements.append(
            arrow(
                edge["description"],
                x=start_x + 110,
                y=start_y + 48,
                dx=(end_x + 110) - (start_x + 110),
                dy=(end_y + 48) - (start_y + 48),
            )
        )
    return scene(elements)


def render_trust_tier_model(host_vars: dict[str, Any]) -> dict[str, Any]:
    topology = host_vars["lv3_service_topology"]
    authenticated = sorted(
        service["public_hostname"]
        for service in topology.values()
        if service.get("public_hostname") in {"docs.lv3.org", "home.lv3.org", "langfuse.lv3.org", "logs.lv3.org", "n8n.lv3.org", "ops.lv3.org", "draw.lv3.org"}
    )
    private = sorted(
        service["service_name"]
        for service in topology.values()
        if service.get("exposure_model") == "private-only"
    )[:6]
    elements: list[dict[str, Any]] = []
    elements += rectangle("Public Edge\nnginx.lv3.org", x=80, y=60, height=96, background="#dbeafe")
    elements += rectangle("Authenticated Edge\n" + "\n".join(authenticated[:4]), x=420, y=60, height=148, background="#e0e7ff")
    elements += rectangle("Private Runtime\n" + "\n".join(private[:4]), x=760, y=60, height=148, background="#dcfce7")
    elements += rectangle("Tailnet / Host Access\n100.64.0.1 and private TCP proxies", x=1080, y=60, height=96, background="#fef3c7")
    elements += rectangle("draw.lv3.org\nshared oauth2-proxy auth\n/socket.io/ split route", x=420, y=300, height=120, background="#ede9fe")
    elements += rectangle("10.10.10.20:3095\nfrontend", x=760, y=280, background="#f5f3ff")
    elements += rectangle("10.10.10.20:3096\ncollaboration room", x=760, y=420, background="#f5f3ff")
    elements.append(arrow("public-auth", x=300, y=120, dx=120, dy=0))
    elements.append(arrow("auth-runtime", x=640, y=170, dx=120, dy=170))
    elements.append(arrow("runtime-tailnet", x=980, y=120, dx=100, dy=0))
    elements.append(arrow("draw-frontend", x=640, y=360, dx=120, dy=-20))
    elements.append(arrow("draw-room", x=640, y=360, dx=120, dy=120))
    return scene(elements)


def render_agent_coordination_map(workstreams: dict[str, Any]) -> dict[str, Any]:
    entries = workstreams["workstreams"]
    live_applied = sum(1 for entry in entries if entry.get("status") == "live_applied")
    active_branch_count = len({entry.get("branch") for entry in entries if entry.get("branch")})
    elements: list[dict[str, Any]] = []
    elements += rectangle("origin/main\nintegration truth", x=80, y=220, background="#dbeafe")
    elements += rectangle("codex/ws-0202-live-apply\nisolated worktree", x=400, y=220, background="#ede9fe")
    elements += rectangle("workstreams.yaml\nbranch registry", x=720, y=60, background="#dcfce7")
    elements += rectangle("docs/workstreams/\noperator handoff notes", x=720, y=220, background="#fef3c7")
    elements += rectangle("receipts/live-applies/\nverification evidence", x=720, y=380, background="#fee2e2")
    elements += rectangle(
        f"Parallel branch count\n{active_branch_count}\nLive-applied workstreams {live_applied}",
        x=1040,
        y=220,
        height=110,
        background="#f8fafc",
    )
    elements.append(arrow("main-branch", x=300, y=260, dx=100, dy=0))
    elements.append(arrow("branch-registry", x=510, y=220, dx=210, dy=-120))
    elements.append(arrow("branch-docs", x=620, y=260, dx=100, dy=0))
    elements.append(arrow("branch-receipt", x=620, y=290, dx=100, dy=140))
    elements.append(arrow("registry-metric", x=940, y=115, dx=100, dy=145))
    return scene(elements)


def render_diagrams() -> dict[str, str]:
    host_vars = load_yaml(HOST_VARS_PATH)
    workstreams = load_workstream_registry(repo_root=repo_path(), include_archive=True)
    dependency_graph = load_json(DEPENDENCY_GRAPH_PATH)

    diagrams = {
        "network-topology.excalidraw": scene_to_text(render_network_topology(host_vars)),
        "service-dependency-graph.excalidraw": scene_to_text(render_service_dependency_graph(dependency_graph)),
        "trust-tier-model.excalidraw": scene_to_text(render_trust_tier_model(host_vars)),
        "agent-coordination-map.excalidraw": scene_to_text(render_agent_coordination_map(workstreams)),
    }
    return diagrams


def scene_to_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate the committed Excalidraw architecture scenes.")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR, help="Destination directory for generated scenes.")
    parser.add_argument("--write", action="store_true", help="Write the generated scenes.")
    parser.add_argument("--check", action="store_true", help="Verify the generated scenes are current.")
    parser.add_argument("--stdout", action="store_true", help="Print a JSON summary of generated filenames.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if sum(bool(flag) for flag in (args.write, args.check, args.stdout)) != 1:
        parser.error("choose exactly one of --write, --check, or --stdout")

    try:
        diagrams = render_diagrams()
        if args.stdout:
            print(json.dumps(sorted(diagrams), indent=2))
            return 0
        if args.write:
            args.output_dir.mkdir(parents=True, exist_ok=True)
            for filename, rendered in diagrams.items():
                (args.output_dir / filename).write_text(rendered, encoding="utf-8")
            print(f"Updated diagrams in {args.output_dir}")
            return 0
        stale: list[str] = []
        for filename, rendered in diagrams.items():
            path = args.output_dir / filename
            current = path.read_text(encoding="utf-8") if path.exists() else ""
            if current != rendered:
                stale.append(filename)
        if stale:
            with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as handle:
                handle.write(json.dumps(stale, indent=2))
            raise ValueError(
                f"{args.output_dir} is stale for {', '.join(stale)}. Run 'python3 scripts/generate_diagrams.py --write'."
            )
        print("Architecture diagrams OK")
        return 0
    except Exception as exc:  # noqa: BLE001
        return emit_cli_error("architecture diagrams", exc)


if __name__ == "__main__":
    sys.exit(main())
