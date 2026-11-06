#!/usr/bin/env python3
"""netpolicy: one source of truth for per-VM network rules.

A VM on a Proxmox host is filtered by up to four layers that used to be edited separately, by hand:

  pve          the Proxmox VM firewall, /etc/pve/firewall/<vmid>.fw on the hypervisor (outside the VM: what it drops, the VM never sees)
  input        the guest's own nftables, table inet filter, chain input (services that listen on the VM itself)
  forward      the guest's nftables, chain forward (traffic Docker DNATs to a container)
  docker_user  the guest's iptables DOCKER-USER chain and the chains it jumps to (port-level limits in front of Docker's rules)

The canonical file, config/network-policy/<host>.yaml, lists per VM the flows that are allowed (source, protocol, ports) and in
which layers each one must exist, with a purpose and an owner. This tool reads the live state of all layers, compares it with
the file and says what differs, and answers "which layer blocks this flow?". It never changes a host.

  netpolicy.py check    [--policy FILE]                 offline: the file(s) are valid and break no rule beyond the baseline (CI runs this)
  netpolicy.py snapshot --host 0mcp [--ssh ALIAS]       read the live state of every VM of that hypervisor (read-only)
  netpolicy.py import   --snapshot S --out FILE         write the canonical file from a snapshot (keeps purposes of an existing file)
  netpolicy.py drift    [--policy FILE] [--snapshot S | --live] [--textfile-dir D]   live vs file, per VM and layer
  netpolicy.py render   pve|nft --policy FILE --vm ID   print what the file says one layer should contain
  netpolicy.py why      --policy FILE --vm ID --src IP --port N [--proto tcp] [--snapshot S]   verdict per layer for one flow
  netpolicy.py apply    --policy FILE --vm ID [--layers pve,input,forward] [--allow-remove] [--yes]   plan, and with --yes apply one VM

Exit codes: 0 in sync / ok, 1 findings that fail `check` (or an apply that was refused or aborted before any change), 2 drift, 3 could not
look, 4 an apply failed AND its rollback could not be verified (a human must look now), 5 an apply failed and was rolled back and verified.
`apply` changes only `pve` rules and the guest's `table inet filter` (and persists them in /etc/nftables.conf without ever reloading it);
a rollback timer is armed on the hypervisor before anything is touched. Python 3 standard library plus PyYAML.
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import ipaddress
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Iterable

try:
    import yaml
except ImportError:  # pragma: no cover - the CI step installs it
    yaml = None

REPO = Path(__file__).resolve().parents[1]
POLICY_DIR = REPO / "config" / "network-policy"
LAYERS = ("pve", "input", "forward", "docker_user")
GUEST_LAYERS = ("input", "forward", "docker_user")
DEFAULT_TEXTFILE_DIR = "/var/lib/prometheus-node-exporter/textfile"  # what the builder's node exporter reads (--collector.textfile.directory)
WIDE_PREFIX = 24  # a source CIDR wider than this needs `wide_ok` with a reason
# Sources whose traffic never crosses the VM's network card as plain IP (Docker bridges, the tailnet inside the guest): the Proxmox
# layer cannot see them, so a guest-only rule for them is normal and a wide range there is not a finding. Overridable per policy file.
DEFAULT_INNER_SOURCES = ["172.16.0.0/12", "192.168.0.0/16", "10.200.0.0/16", "100.64.0.0/10"]

# PVE macros we understand (action names are case-sensitive in the file); anything else is reported, never guessed.
PVE_MACROS: dict[str, list[tuple[str, str]]] = {
    "SSH": [("tcp", "22")],
    "Ping": [("icmp", "*")],
    "HTTP": [("tcp", "80")],
    "HTTPS": [("tcp", "443")],
    "DNS": [("tcp", "53"), ("udp", "53")],
}


class PolicyError(Exception):
    """The policy file or a live reading is not usable."""


# ───────────────────────────── flows ─────────────────────────────


@dataclasses.dataclass(frozen=True, order=True)
class Flow:
    """One allowed (source, protocol, port) arriving at the VM; `iif` is set for an interface-qualified guest rule."""

    src: str  # 'any' or an IPv4 address / CIDR ('10.10.10.10' for a /32)
    proto: str  # tcp udp icmp vrrp any
    port: str  # '22', '1000-2000' or '*' (every port, or not applicable)
    iif: str = ""

    def text(self) -> str:
        extra = f" iif={self.iif}" if self.iif else ""
        return f"{self.src} {self.proto}/{self.port}{extra}"


def norm_src(value: str) -> str:
    v = value.strip()
    if v in ("", "any", "0.0.0.0/0"):
        return "any"
    try:
        net = ipaddress.ip_network(v, strict=False)
    except ValueError as exc:
        raise PolicyError(f"not an IPv4 address or network: {value!r}") from exc
    if net.version != 4:
        raise PolicyError(f"IPv6 is not modelled: {value!r}")
    return str(net.network_address) if net.prefixlen == 32 else str(net)


def split_ports(spec: str) -> list[str]:
    """'80,443' / '3000:3010' / '{ 80, 443 }' / '18021' -> ['80', '443']; a range keeps one token, 'a-b'."""
    out: list[str] = []
    for part in re.split(r"[,\s]+", spec.strip().strip("{}").strip()):
        part = part.strip()
        if not part:
            continue
        part = part.replace(":", "-")
        if not re.fullmatch(r"\d{1,5}(-\d{1,5})?", part):
            raise PolicyError(f"not a port or port range: {part!r}")
        out.append(part)
    return out


def port_matches(token: str, port: int) -> bool:
    if token == "*":
        return True
    if "-" in token:
        lo, hi = token.split("-")
        return int(lo) <= port <= int(hi)
    return int(token) == port


def src_matches(src: str, ip: str) -> bool:
    if src == "any":
        return True
    return ipaddress.ip_address(ip) in ipaddress.ip_network(src, strict=False)


# ───────────────────────────── Proxmox VM firewall ─────────────────────────────


def parse_pve(text: str, ipsets: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """Parse a /etc/pve/firewall file. Returns options, flows (with the comment), disabled rules and what was not understood."""
    sets = {k: list(v) for k, v in (ipsets or {}).items()}
    options: dict[str, str] = {}
    flows: list[tuple[Flow, str]] = []
    unparsed: list[str] = []
    disabled = 0
    section = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^\[(.*)\]$", line)
        if m:
            section = m.group(1).strip()
            if section.upper().startswith("IPSET"):
                sets.setdefault(section.split()[1], [])
            continue
        kind = section.split()[0].upper() if section else ""
        if kind == "OPTIONS":
            key, _, value = line.partition(":")
            options[key.strip()] = value.strip()
        elif kind == "IPSET":
            name = section.split()[1]
            sets.setdefault(name, []).append(norm_src(line.split("#")[0].split()[0]))
        elif kind == "RULES":
            if line.startswith("|"):
                disabled += 1
                continue
            body, _, comment = line.partition("#")
            try:
                for fl in _pve_rule(body.split(), sets):
                    flows.append((fl, comment.strip()))
            except PolicyError as exc:
                unparsed.append(f"{raw.strip()}  <- {exc}")
        elif kind not in ("ALIASES",):
            unparsed.append(raw.strip())
    return {"options": options, "flows": flows, "unparsed": unparsed, "disabled": disabled, "ipsets": sets}


def _pve_rule(tok: list[str], sets: dict[str, list[str]]) -> list[Flow]:
    if len(tok) < 2 or tok[0] != "IN":
        raise PolicyError("only IN rules are modelled")
    action = tok[1]
    macro = re.fullmatch(r"(\w+)\(ACCEPT\)", action)
    if action != "ACCEPT" and not macro:
        raise PolicyError(f"action {action} is not modelled")
    opts: dict[str, str] = {}
    i = 2
    while i < len(tok):
        if tok[i] in ("-source", "-p", "-dport", "-i", "-log", "-dest", "-sport", "-iface"):
            if i + 1 >= len(tok):
                raise PolicyError(f"{tok[i]} without a value")
            opts[tok[i][1:]] = tok[i + 1]
            i += 2
        else:
            raise PolicyError(f"unknown token {tok[i]}")
    for bad in ("dest", "sport", "iface"):
        if bad in opts:
            raise PolicyError(f"-{bad} is not modelled")
    iif = opts.get("i", "")
    sources: list[str] = []
    for s in opts.get("source", "any").split(","):
        if s.startswith("+"):
            name = s[1:]
            if name not in sets:
                raise PolicyError(f"unknown ipset {name}")
            sources.extend(sets[name])
        else:
            sources.append(norm_src(s))
    if macro:
        name = macro.group(1)
        if name not in PVE_MACROS:
            raise PolicyError(f"macro {name} is not modelled")
        pairs = PVE_MACROS[name]
        return [Flow(s, p, port, iif) for s in sources for p, port in pairs]
    proto = opts.get("p", "any")
    if proto in ("icmp", "vrrp") or "dport" not in opts:
        return [Flow(s, proto, "*", iif) for s in sources]
    return [Flow(s, proto, port, iif) for s in sources for port in split_ports(opts["dport"])]


def render_pve(vm: dict[str, Any]) -> str:
    """The text of /etc/pve/firewall/<vmid>.fw for one VM of the policy: options, then one rule per flow, sorted."""
    pve = vm.get("pve", {})
    lines = ["[OPTIONS]", ""]
    for key in ("enable", "policy_in", "policy_out"):
        if key in pve:
            lines.append(f"{key}: {pve[key]}")
    lines += ["", "[RULES]", ""]
    comments: dict[Flow, str] = {}
    for g in vm.get("groups", []):
        if "pve" in g["layers"]:
            for fl in group_flows(g):
                comments.setdefault(fl, str(g.get("purpose", "")).strip())
    for fl in sorted(comments, key=_flow_sort):
        lines.append(_pve_line(fl, comments[fl]))
    return "\n".join(lines) + "\n"


def _flow_sort(fl: Flow) -> tuple:
    first = fl.port.split("-")[0]
    return (fl.proto, int(first) if first.isdigit() else -1, fl.port, fl.src, fl.iif)


def _pve_line(fl: Flow, comment: str) -> str:
    parts = ["IN ACCEPT"]
    if fl.src != "any":
        parts.append(f"-source {fl.src if '/' in fl.src else fl.src + '/32'}")
    if fl.proto != "any":
        parts.append(f"-p {fl.proto}")
    if fl.port != "*" and fl.proto in ("tcp", "udp"):
        parts.append(f"-dport {fl.port.replace('-', ':')}")
    if fl.iif:
        parts.append(f"-i {fl.iif}")
    line = " ".join(parts)
    return f"{line} # {comment}" if comment else line


# ───────────────────────────── guest nftables ─────────────────────────────

_COUNTER = re.compile(r"\s*counter(?:\s+packets\s+\d+\s+bytes\s+\d+)?")


def _nft_line(raw: str) -> str:
    """One rule line as the parser sees it: no trailing `# comment` (the hand written conf has many), no counter, no `;`."""
    line = re.sub(r"\s*#.*$", "", raw.strip())
    return _COUNTER.sub("", line).rstrip(";").strip()


def _table_block(text: str, family: str, name: str) -> str:
    m = re.search(rf"^table {family} {name} \{{", text, re.M)
    if not m:
        return ""
    depth, i = 0, m.end() - 1
    start = i
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1 : i]
        i += 1
    return text[start + 1 :]


def _chain_blocks(block: str) -> list[tuple[str, str]]:
    """(name, body) of every chain of a table body, by brace depth: works for `nft list` output and for the hand written conf layout."""
    out: list[tuple[str, str]] = []
    for m in re.finditer(r"\bchain (\w+) \{", block):
        depth, i = 1, m.end()
        while i < len(block) and depth:
            if block[i] == "{":
                depth += 1
            elif block[i] == "}":
                depth -= 1
            i += 1
        out.append((m.group(1), block[m.end() : i - 1]))
    return out


def parse_nft(text: str) -> dict[str, Any]:
    """Parse `nft list ruleset` or /etc/nftables.conf, looking ONLY at `table inet filter` (Docker's and Tailscale's own tables are theirs)."""
    block = _table_block(text, "inet", "filter")
    chains: dict[str, dict[str, Any]] = {}
    unparsed: list[str] = []
    for name, body in _chain_blocks(block):
        hook = re.search(r"type filter hook (\w+) priority \S+;", body)
        policy = re.search(r"\bpolicy (\w+);", body)
        flows: list[Flow] = []
        baseline: list[str] = []
        for raw in body.splitlines():
            line = _nft_line(raw)
            if not line or line.startswith("type filter") or line.startswith("policy "):
                continue
            if line in ("ct state established,related accept", "iifname \"lo\" accept"):
                baseline.append(line)
                continue
            try:
                parsed = _nft_rule(line)
            except PolicyError as exc:
                unparsed.append(f"{name}: {line}  <- {exc}")
                continue
            if parsed is None:  # a drop, reject, log, jump...: never silently filed as harmless, the policy cannot see what it does
                unparsed.append(f"{name}: {line}  <- not an accept rule (drop, reject, log, jump...): not modelled")
            else:
                flows.extend(parsed)
        chains[name] = {"hook": hook.group(1) if hook else "", "policy": policy.group(1) if policy else "", "flows": flows, "baseline": baseline}
    return {"present": bool(block), "chains": chains, "unparsed": unparsed}


def _nft_rule(line: str) -> list[Flow] | None:
    """Flows of one `... accept` rule; None for a rule that is not an allow (drop, log, jump, set mark...)."""
    if not line.endswith("accept"):
        return None
    core = line[: -len("accept")].strip()
    iif = ""
    m = re.match(r'^iifname "([^"]+)"\s*', core)
    if m:
        iif, core = m.group(1), core[m.end() :]
    sources = ["any"]
    m = re.match(r"^ip saddr (\{[^}]*\}|\S+)\s*", core)
    if m:
        sources = [norm_src(s) for s in re.split(r"[,\s]+", m.group(1).strip("{} ")) if s]
        core = core[m.end() :]
    proto, ports = "any", ["*"]
    if not core:
        pass
    elif re.fullmatch(r"icmp type echo-request", core):
        proto = "icmp"
    elif core == "ip protocol vrrp":
        proto = "vrrp"
    elif (m := re.fullmatch(r"(tcp|udp) dport (\{[^}]*\}|\S+)", core)):
        proto, ports = m.group(1), split_ports(m.group(2))
    elif (m := re.fullmatch(r"ct original proto-dst (\{[^}]*\}|\S+)", core)):
        ports = split_ports(m.group(1))
    else:
        raise PolicyError("rule shape is not modelled")
    return [Flow(s, proto, p, iif) for s in sources for p in ports]


# ───────────────────────────── iptables DOCKER-USER ─────────────────────────────


def parse_docker_user(text: str) -> dict[str, Any]:
    """`iptables -S DOCKER-USER` followed by `iptables -S <chain>` of every chain it jumps to."""
    rules: dict[str, list[str]] = collections.defaultdict(list)
    for line in text.splitlines():
        m = re.match(r"^-A (\S+) (.*)$", line.strip())
        if m:
            rules[m.group(1)].append(m.group(2))
    flows: list[Flow] = []
    baseline: list[str] = []
    unparsed: list[str] = []
    for rule in rules.get("DOCKER-USER", []):
        jump = re.search(r"-j (\S+)$", rule)
        target = jump.group(1) if jump else ""
        if target == "RETURN" and rule == "-j RETURN":
            baseline.append(rule)
            continue
        port = re.search(r"--ctorigdstport (\d+)", rule)
        proto = re.search(r"-p (tcp|udp)", rule)
        if not (target in rules and port and proto):
            unparsed.append(f"DOCKER-USER: {rule}")
            continue
        for sub in rules[target]:
            s = re.fullmatch(r"-s (\S+) -j RETURN", sub)
            if s:
                flows.append(Flow(norm_src(s.group(1)), proto.group(1), port.group(1)))
            elif sub == "-j DROP":
                baseline.append(f"{target}: -j DROP")
            else:
                unparsed.append(f"{target}: {sub}")
    return {"flows": flows, "baseline": baseline, "unparsed": unparsed}


# ───────────────────────────── editing the files (pure text functions) ─────────────────────────────
# These change as little as possible: a rule line is removed or added, or, when only some of the flows it carries are to go, rewritten in
# place with the sources and ports that stay (REPLACE); everything else stays byte for byte, and the result is parsed again and must equal
# the intended flows exactly, or the edit is refused.


def render_nft_rule(fl: Flow) -> str:
    """The nftables rule line for one flow, in the shape `nft list` prints and this tool parses back."""
    parts: list[str] = []
    if fl.iif:
        parts.append(f'iifname "{fl.iif}"')
    if fl.src != "any":
        parts.append(f"ip saddr {fl.src}")
    if fl.proto in ("tcp", "udp"):
        if fl.port == "*":
            raise PolicyError(f"cannot render {fl.text()}: a protocol without ports is not modelled for nftables")
        parts.append(f"{fl.proto} dport {fl.port}")
    elif fl.proto == "icmp":
        parts.append("icmp type echo-request")
    elif fl.proto == "vrrp":
        parts.append("ip protocol vrrp")
    elif fl.port != "*":
        parts.append(f"ct original proto-dst {fl.port}")
    parts.append("accept")
    return " ".join(parts)


def render_nft_rules(flows: Iterable[Flow]) -> list[str]:
    """Rule lines for several flows: ports of the same (interface, source, protocol) share one line `tcp dport { a, b }`."""
    grouped: dict[tuple[str, str, str], list[str]] = {}
    lines: list[str] = []
    for fl in sorted(set(flows), key=_flow_sort):
        if fl.proto in ("tcp", "udp") and fl.port != "*":
            grouped.setdefault((fl.iif, fl.src, fl.proto), []).append(fl.port)
        else:
            lines.append(render_nft_rule(fl))
    for (iif, src, proto), ports in grouped.items():
        ports = sorted(set(ports), key=_port_key)
        spec = ports[0] if len(ports) == 1 else "{ " + ", ".join(ports) + " }"
        head = (f'iifname "{iif}" ' if iif else "") + (f"ip saddr {src} " if src != "any" else "")
        lines.append(f"{head}{proto} dport {spec} accept")
    return lines


def _table_span(text: str, family: str, name: str) -> tuple[int, int] | None:
    m = re.search(rf"^table {family} {name} \{{", text, re.M)
    if not m:
        return None
    depth, i = 1, m.end()
    while i < len(text) and depth:
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
    return m.end(), i - 1  # between the braces


def _chain_spans(text: str, lo: int, hi: int) -> dict[str, tuple[int, int]]:
    spans: dict[str, tuple[int, int]] = {}
    for m in re.finditer(r"\bchain (\w+) \{", text[lo:hi]):
        start = lo + m.end()
        depth, i = 1, start
        while i < hi and depth:
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        spans[m.group(1)] = (start, i - 1)
    return spans


def _shrink_set(code: str, head: str, keep: Callable[[str], bool], rule: str) -> str:
    """`code` with the set (or single value) after `head` cut to the tokens `keep` accepts; written as nft prints it."""
    m = re.search(rf"(?:{head})(\{{[^}}]*\}}|\S+)", code)
    if not m:
        raise PolicyError(f"the rule `{rule}` could not be rewritten: no {head.strip()} found")
    left = [t for t in re.split(r"[,\s]+", m.group(1).strip("{} ")) if t and keep(t)]
    spec = left[0] if len(left) == 1 else "{ " + ", ".join(left) + " }"
    return code[: m.start(1)] + spec + code[m.end(1) :]


def _one_product(keep: list[Flow], rule: str, total: int) -> tuple[set[str], set[tuple[str, str]]]:
    """The sources and the (protocol, port) pairs of `keep`, if every source goes with every pair (one rule can say exactly that)."""
    srcs, kinds = {f.src for f in keep}, {(f.proto, f.port) for f in keep}
    if {(s, k) for s in srcs for k in kinds} != {(f.src, (f.proto, f.port)) for f in keep}:
        raise PolicyError(f"the rule `{rule}` carries {total} flows and the {len(set(keep))} that stay are not one set of sources times one set "
                          "of ports, so no single rule can hold them: split it by hand first")
    return srcs, kinds


def _shrink_nft_rule(raw: str, flows: list[Flow], keep: list[Flow]) -> str:
    """The same rule line holding only the sources and ports of `keep`: indent, counter, trailing comment and position stay as they were."""
    clean = _nft_line(raw)
    srcs, kinds = _one_product(keep, clean, len(flows))
    code, sep, comment = raw.partition("#")
    if srcs != {f.src for f in flows}:
        code = _shrink_set(code, "ip saddr ", lambda t: norm_src(t) in srcs, clean)
    if kinds != {(f.proto, f.port) for f in flows}:
        ports = {p for _, p in kinds}
        code = _shrink_set(code, "(?:tcp|udp) dport |ct original proto-dst ", lambda t: t.replace(":", "-") in ports, clean)
    new = code + sep + comment
    try:
        got = set(_nft_rule(_nft_line(new)) or [])
    except PolicyError:
        got = set()
    if got != set(keep):
        raise PolicyError(f"the rule `{clean}` could not be rewritten to exactly the flows that stay")
    return new


def edit_nft(text: str, removals: dict[str, set[Flow]] | None = None, adds: dict[str, list[Flow]] | None = None,
             replaced: list[dict[str, str]] | None = None) -> str:
    """Remove and add rule lines in the chains of `table inet filter`, in `nft list` output or in the hand written conf alike.

    A rule that carries flows to remove and flows that stay is rewritten where it is; each such rule is appended to `replaced`."""
    removals, adds = removals or {}, adds or {}
    span = _table_span(text, "inet", "filter")
    if span is None:
        raise PolicyError("no table inet filter in the text")
    before = parse_nft(text)
    chains = _chain_spans(text, *span)
    for chain in set(removals) | set(adds):
        if chain not in chains:
            raise PolicyError(f"no chain {chain} in table inet filter")
    out = text
    for chain in sorted(chains, key=lambda c: -chains[c][0]):  # last chain first, so earlier offsets stay valid
        if chain not in removals and chain not in adds:
            continue
        start, end = chains[chain]
        lines = out[start:end].split("\n")
        closing = lines[-1]  # the whitespace before the closing brace
        kept: list[str] = []
        drop_blank = False
        last_rule_indent = ""
        for line in lines[:-1]:
            clean = _nft_line(line)
            if drop_blank and not line.strip():
                drop_blank = False
                continue
            drop_blank = False
            if clean and not clean.startswith(("type filter", "policy ")):
                try:
                    flows = _nft_rule(clean)
                except PolicyError:
                    flows = None
                if flows:
                    last_rule_indent = line[: len(line) - len(line.lstrip())]
                    gone = removals.get(chain, set())
                    inter = [f for f in flows if f in gone]
                    if inter and len(inter) == len(flows):
                        if kept and not kept[-1].strip():
                            drop_blank = True
                        continue
                    if inter:
                        line = _shrink_nft_rule(line, flows, [f for f in flows if f not in gone])
                        if replaced is not None:
                            replaced.append({"chain": chain, "old": clean, "new": _nft_line(line)})
            kept.append(line)
        if adds.get(chain):
            indent = last_rule_indent or next((l[: len(l) - len(l.lstrip())] for l in kept if l.strip()), "    ")
            have = {f for l in kept for f in (_safe_nft_rule(l) or [])}
            kept += [f"{indent}{line}" for line in render_nft_rules(f for f in adds[chain] if f not in have)]
        out = out[:start] + "\n".join(kept + [closing]) + out[end:]
    after = parse_nft(out)
    for chain, info in before["chains"].items():
        want = (set(info["flows"]) - removals.get(chain, set())) | set(adds.get(chain, []))
        got = set(after["chains"][chain]["flows"])
        if got != want or after["chains"][chain]["policy"] != info["policy"] or after["chains"][chain]["baseline"] != info["baseline"]:
            raise PolicyError(f"self-check failed on chain {chain}: the edited text does not hold exactly the intended flows")
    if after["unparsed"] != before["unparsed"]:
        raise PolicyError("self-check failed: the edit changed what the parser cannot read")
    return out


def _safe_nft_rule(line: str) -> list[Flow] | None:
    clean = _nft_line(line)
    if not clean or clean.startswith(("type filter", "policy ")):
        return None
    try:
        return _nft_rule(clean)
    except PolicyError:
        return None


def _shrink_pve_opt(body: str, opt: str, keep: Callable[[str], bool]) -> str:
    m = re.search(rf"(?<!\S){opt}\s+(\S+)", body)
    if not m:
        raise PolicyError(f"the rule `{body.strip()}` could not be rewritten: no {opt} found")
    left = [t for t in m.group(1).split(",") if keep(t)]
    return body[: m.start(1)] + ",".join(left) + body[m.end(1) :]


def _shrink_pve_rule(raw: str, flows: list[Flow], keep: list[Flow], sets: dict[str, list[str]]) -> str:
    """The same `IN ...` line holding only the sources and ports of `keep`; options, comment and position stay as they were.

    Refused: cutting a macro to some of its protocols and ports (DNS is tcp and udp), and cutting an ipset (it is shared by every rule and VM
    that names it)."""
    stripped = raw.strip()
    srcs, kinds = _one_product(keep, stripped, len(flows))
    body, sep, comment = raw.partition("#")
    tok = body.split()
    if kinds != {(f.proto, f.port) for f in flows}:
        if re.fullmatch(r"\w+\(ACCEPT\)", tok[1]):
            have = ", ".join(f"{p}/{port}" for p, port in sorted({(f.proto, f.port) for f in flows}))
            raise PolicyError(f"the rule `{stripped}` uses the macro {tok[1]} ({have}): a macro cannot be cut to some of its protocols and ports, "
                              "split it by hand first")
        ports = {p for _, p in kinds}
        body = _shrink_pve_opt(body, "-dport", lambda t: t.replace(":", "-") in ports)
    if srcs != {f.src for f in flows}:
        names = [t for t in tok[tok.index("-source") + 1].split(",") if t.startswith("+")]
        for name in names:
            if not set(sets.get(name[1:], [])) <= srcs:
                raise PolicyError(f"the rule `{stripped}` takes sources from the ipset {name[1:]}, which other rules and VMs share: "
                                  "change the ipset or the rule by hand")
        body = _shrink_pve_opt(body, "-source", lambda t: t.startswith("+") or norm_src(t) in srcs)
    new = body + sep + comment
    try:
        got = set(_pve_rule(body.split(), sets))
    except PolicyError:
        got = set()
    if got != set(keep):
        raise PolicyError(f"the rule `{stripped}` could not be rewritten to exactly the flows that stay")
    return new


def edit_pve(text: str, remove: set[Flow], add: list[tuple[Flow, str]], ipsets: dict[str, list[str]] | None = None,
             replaced: list[dict[str, str]] | None = None) -> str:
    """Remove and add `IN ACCEPT` rule lines of a /etc/pve/firewall/<vmid>.fw; everything else stays byte for byte.

    A rule that carries flows to remove and flows that stay is rewritten where it is; each such rule is appended to `replaced`."""
    before = parse_pve(text, ipsets)
    lines = text.split("\n")
    out: list[str] = []
    section = ""
    last_rule = -1
    sets = dict(before["ipsets"])
    for raw in lines:
        stripped = raw.strip()
        m = re.match(r"^\[(.*)\]$", stripped)
        if m:
            section = m.group(1).split()[0].upper()
            out.append(raw)
            continue
        if section == "RULES" and stripped and not stripped.startswith(("#", "|")):
            try:
                flows = _pve_rule(stripped.split("#")[0].split(), sets)
            except PolicyError:
                flows = []
            if flows:
                inter = [f for f in flows if f in remove]
                if inter and len(inter) == len(flows):
                    continue
                if inter:
                    raw = _shrink_pve_rule(raw, flows, [f for f in flows if f not in remove], sets)
                    if replaced is not None:
                        replaced.append({"old": stripped, "new": raw.strip()})
                out.append(raw)
                last_rule = len(out) - 1
                continue
        out.append(raw)
        if section == "RULES" and stripped and not stripped.startswith("#"):
            last_rule = len(out) - 1
    have = {f for f, _ in before["flows"]}
    new_lines = [_pve_line(f, c) for f, c in add if f not in have]
    if new_lines:
        if last_rule >= 0:
            out[last_rule + 1 : last_rule + 1] = new_lines
        else:
            idx = next((i for i, l in enumerate(out) if l.strip().upper() == "[RULES]"), None)
            if idx is None:
                out += ["", "[RULES]", ""] + new_lines
            else:
                out[idx + 1 : idx + 1] = new_lines
    result = "\n".join(out)
    if not result.endswith("\n"):
        result += "\n"
    after = parse_pve(result, ipsets)
    want = ({f for f, _ in before["flows"]} - remove) | {f for f, _ in add}
    if {f for f, _ in after["flows"]} != want or after["options"] != before["options"] or after["unparsed"] != before["unparsed"]:
        raise PolicyError("self-check failed: the edited firewall file does not hold exactly the intended flows")
    return result


# ───────────────────────────── observed state ─────────────────────────────


def observe(snapshot: dict[str, Any]) -> dict[str, Any]:
    """snapshot (what `snapshot` collected) -> per VM: attributes and per-layer Flow sets, plus everything not understood."""
    cluster = parse_pve(snapshot.get("cluster_fw", ""))
    sets = cluster["ipsets"]
    out: dict[str, Any] = {}
    for vmid, vm in snapshot.get("vms", {}).items():
        entry: dict[str, Any] = {"name": vm.get("name", ""), "status": vm.get("status", ""), "layers": {l: set() for l in LAYERS},
                                 "comments": {}, "unparsed": [], "attrs": {}}
        if vm.get("fw") is not None:
            pve = parse_pve(vm["fw"], sets)
            entry["attrs"]["pve_options"] = pve["options"]
            for fl, comment in pve["flows"]:
                entry["layers"]["pve"].add(fl)
                entry["comments"].setdefault(("pve", fl), comment)
            entry["unparsed"] += [f"pve: {u}" for u in pve["unparsed"]]
            entry["attrs"]["pve_disabled_rules"] = pve["disabled"]
        entry["attrs"]["pve_file"] = vm.get("fw") is not None
        g = vm.get("guest") or {}
        entry["attrs"]["guest_readable"] = bool(g.get("ok"))
        if g.get("ok"):
            nft = parse_nft(g.get("nft", ""))
            entry["attrs"]["guest_nft"] = nft["present"]
            for chain, layer in (("input", "input"), ("forward", "forward")):
                c = nft["chains"].get(chain)
                if c:
                    entry["layers"][layer].update(c["flows"])
                    entry["attrs"][f"{chain}_policy"] = c["policy"]
            entry["unparsed"] += [f"nft: {u}" for u in nft["unparsed"]]
            if "conf" in g:  # what a reboot loads: /etc/nftables.conf of the guest
                conf = parse_nft(g["conf"])
                entry["attrs"]["conf_present"] = conf["present"]
                entry["conf"] = {"input": set(), "forward": set()}
                for chain in ("input", "forward"):
                    c = conf["chains"].get(chain)
                    if c:
                        entry["conf"][chain].update(c["flows"])
                        entry["attrs"][f"conf_{chain}_policy"] = c["policy"]
                entry["unparsed"] += [f"conf: {u}" for u in conf["unparsed"]]
            du = parse_docker_user(g.get("iptables", ""))
            entry["layers"]["docker_user"].update(du["flows"])
            entry["unparsed"] += [f"docker_user: {u}" for u in du["unparsed"]]
        out[str(vmid)] = entry
    return {"ipsets": sets, "vms": out}


# ───────────────────────────── the canonical file ─────────────────────────────


PROTOCOLS = ("tcp", "udp", "icmp", "vrrp", "any")


def _valid_port(token: str) -> bool:
    if token == "*":
        return True
    m = re.fullmatch(r"(\d{1,5})(?:-(\d{1,5}))?", token)
    if not m:
        return False
    lo = int(m.group(1))
    hi = int(m.group(2)) if m.group(2) else lo
    return 1 <= lo <= hi <= 65535


def group_flows(group: dict[str, Any]) -> list[Flow]:
    srcs = [norm_src(s) for s in group.get("from", ["any"])]
    ports = group.get("ports", "*")
    plist = ["*"] if ports in ("*", None, []) else [str(p).replace(":", "-") for p in ports]
    proto = group.get("proto", "any")
    if proto not in PROTOCOLS:
        raise PolicyError(f"unknown protocol {proto!r}")
    for p in plist:
        if not _valid_port(p):
            raise PolicyError(f"not a valid port or range: {p!r}")
        if p != "*" and proto not in ("tcp", "udp", "any"):
            raise PolicyError(f"{proto} takes no ports, got {p!r}")
    iif = group.get("iif", "")
    return [Flow(s, proto, p, iif) for s in srcs for p in plist]


def load_policy(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise PolicyError("PyYAML is required")
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict) or data.get("version") != 1:
        raise PolicyError(f"{path}: version 1 policy expected")
    for key in ("host", "vms"):
        if key not in data:
            raise PolicyError(f"{path}: missing {key}")
    data.setdefault("ipsets", {})
    data.setdefault("inner_sources", list(DEFAULT_INNER_SOURCES))
    for net in data["inner_sources"]:
        norm_src(net)
    guard = data.get("guard", [])
    if not isinstance(guard, list):
        raise PolicyError("guard must be a list")
    for g in guard:
        if g.get("src") in (None, "any") or not set(g.get("layers", [])) <= {"pve", "input"} or not g.get("layers"):
            raise PolicyError(f"guard entry {g}: a named source and layers from pve, input are required")
        norm_src(g["src"])
        group_flows({"from": [g["src"]], "proto": g.get("proto", "tcp"), "ports": [str(g.get("port", "22"))]})
    data["guard"] = guard
    if "lan_networks" not in data:
        nets = {str(ipaddress.ip_network(f"{v['ip']}/24", strict=False)) for v in data["vms"].values() if (v or {}).get("ip")}
        data["lan_networks"] = sorted(nets)
    for net in data["lan_networks"]:
        norm_src(net)
    vms: dict[str, Any] = {}
    for vmid, vm in data["vms"].items():
        vm = dict(vm or {})
        vm.setdefault("groups", [])
        vm.setdefault("pve", {})
        vm.setdefault("guest", {})
        for gi, g in enumerate(vm["groups"]):
            bad = [l for l in g.get("layers", []) if l not in LAYERS]
            if bad or not g.get("layers"):
                raise PolicyError(f"VM {vmid} group {gi}: layers must be a non-empty subset of {LAYERS}")
            group_flows(g)  # validates every source and port
        vms[str(vmid)] = vm
    data["vms"] = vms
    return data


def expected(vm: dict[str, Any]) -> dict[str, set[Flow]]:
    out: dict[str, set[Flow]] = {l: set() for l in LAYERS}
    for g in vm.get("groups", []):
        for fl in group_flows(g):
            for layer in g["layers"]:
                out[layer].add(fl)
    return out


def compact_groups(layer_flows: dict[str, set[Flow]], comments: dict[tuple[str, Flow], str] | None = None,
                   previous: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Group flows into readable policy groups: flows that share layers, protocol and port set share one entry with many sources."""
    comments = comments or {}
    layers_of: dict[Flow, frozenset[str]] = {}
    for layer, flows in layer_flows.items():
        for fl in flows:
            layers_of[fl] = layers_of.get(fl, frozenset()) | {layer}
    per_src: dict[tuple, set[str]] = collections.defaultdict(set)
    for fl, layers in layers_of.items():
        per_src[(layers, fl.proto, fl.src, fl.iif)].add(fl.port)
    per_ports: dict[tuple, set[str]] = collections.defaultdict(set)
    for (layers, proto, src, iif), ports in per_src.items():
        per_ports[(layers, proto, tuple(sorted(ports, key=_port_key)), iif)].add(src)
    old_meta = {}
    for g in previous or []:
        old_meta[(tuple(sorted(g["layers"])), g.get("proto", "any"), tuple(sorted(group_flows_key(g))))] = g
    groups: list[dict[str, Any]] = []
    for (layers, proto, ports, iif), srcs in sorted(per_ports.items(), key=lambda kv: (sorted(kv[0][0]), kv[0][1], kv[0][2], kv[0][3])):
        g: dict[str, Any] = {"from": sorted(srcs, key=_src_key)}
        if proto != "any":
            g["proto"] = proto
        g["ports"] = "*" if ports == ("*",) else list(ports)
        if iif:
            g["iif"] = iif
        g["layers"] = [l for l in LAYERS if l in layers]
        sample = Flow(sorted(srcs, key=_src_key)[0], proto, ports[0], iif)
        purpose = ""
        for layer in LAYERS:
            if (layer, sample) in comments and comments[(layer, sample)]:
                purpose = comments[(layer, sample)]
                break
        meta = old_meta.get((tuple(sorted(g["layers"])), proto, tuple(sorted(f.text() for f in group_flows(g)))))
        if meta:
            for k in ("purpose", "owner", "public", "wide_ok", "decided", "unit"):
                if k in meta:
                    g[k] = meta[k]
        g.setdefault("purpose", purpose or "imported from the live state, purpose not recorded yet")
        groups.append(g)
    return groups


def group_flows_key(g: dict[str, Any]) -> list[str]:
    return [f.text() for f in group_flows(g)]


def _port_key(p: str) -> tuple:
    first = p.split("-")[0]
    return (0, int(first), p) if first.isdigit() else (1, 0, p)


def _src_key(s: str) -> tuple:
    if s == "any":
        return (0, 0, 0)
    net = ipaddress.ip_network(s, strict=False)
    return (1, int(net.network_address), net.prefixlen)


# ───────────────────────────── import, drift, check, why ─────────────────────────────


def build_policy(snapshot: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    obs = observe(snapshot)
    policy: dict[str, Any] = {"version": 1, "host": snapshot.get("host", ""), "collect": {"ssh": ((previous or {}).get("collect") or {}).get("ssh") or snapshot.get("ssh", "")},
                              "ipsets": {k: v for k, v in obs["ipsets"].items()},
                              "inner_sources": list((previous or {}).get("inner_sources", DEFAULT_INNER_SOURCES)), "vms": {}}
    policy["guard"] = list((previous or {}).get("guard") or [])
    lan = (previous or {}).get("lan_networks")
    if not lan:
        ips = [v.get("ip", "") for v in snapshot["vms"].values() if v.get("ip")]
        lan = sorted({str(ipaddress.ip_network(f"{i}/24", strict=False)) for i in ips})
    policy["lan_networks"] = list(lan)
    for vmid in sorted(obs["vms"], key=int):
        o = obs["vms"][vmid]
        prev = (previous or {}).get("vms", {}).get(vmid, {})
        pve_opts = o["attrs"].get("pve_options", {})
        entry: dict[str, Any] = {"name": o["name"], "ip": snapshot["vms"][vmid].get("ip", "") or prev.get("ip", ""),
                                 "pve": {k: pve_opts[k] for k in ("enable", "policy_in", "policy_out") if k in pve_opts},
                                 "guest": {}}
        entry["guest"]["nft"] = "managed" if o["attrs"].get("guest_nft") else "absent"
        if o["attrs"].get("guest_nft"):
            entry["guest"]["input_policy"] = o["attrs"].get("input_policy", "")
            entry["guest"]["forward_policy"] = o["attrs"].get("forward_policy", "")
        for k in ("exception", "notes"):
            if k in prev:
                entry[k] = prev[k]
        entry["groups"] = compact_groups(o["layers"], o["comments"], prev.get("groups"))
        policy["vms"][vmid] = entry
    return policy


def write_policy(policy: dict[str, Any], path: Path) -> None:
    header = (
        "# Canonical network policy for one hypervisor: the ONE place the allowed flows of its VMs are decided.\n"
        "# Layers: pve = Proxmox VM firewall, input / forward = guest nftables, docker_user = guest iptables DOCKER-USER.\n"
        "# Edit this file in a PR; scripts/netpolicy.py drift tells how the live hosts differ. Every group needs a purpose.\n"
        "# `from` is one IPv4 address or CIDR per entry (no wildcard unless `public: true`), `wide_ok: <reason>` allows a CIDR wider than /24.\n"
    )
    order = ["version", "host", "collect", "ipsets", "inner_sources", "lan_networks", "guard", "vms"]
    ordered = {k: policy[k] for k in order if k in policy}
    ordered.update({k: v for k, v in policy.items() if k not in ordered})
    path.write_text(header + yaml.safe_dump(ordered, sort_keys=False, default_flow_style=None, width=140))


def diff_layers(exp: dict[str, set[Flow]], obs: dict[str, set[Flow]]) -> dict[str, dict[str, list[str]]]:
    out: dict[str, dict[str, list[str]]] = {}
    for layer in LAYERS:
        missing = sorted((exp[layer] - obs[layer]), key=_flow_sort)
        extra = sorted((obs[layer] - exp[layer]), key=_flow_sort)
        if missing or extra:
            out[layer] = {"missing": [f.text() for f in missing], "extra": [f.text() for f in extra]}
    return out


def drift(policy: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    obs = observe(snapshot)
    result: dict[str, Any] = {"host": policy["host"], "vms": {}, "summary": {"vms": 0, "vms_drifted": 0, "flows_missing": 0, "flows_extra": 0, "conf_flows_missing": 0, "conf_flows_extra": 0}}
    for vmid in sorted(set(policy["vms"]) | set(obs["vms"]), key=int):
        res: dict[str, Any] = {"layers": {}, "attrs": [], "unparsed": [], "state": "in_sync"}
        pv, ov = policy["vms"].get(vmid), obs["vms"].get(vmid)
        if pv is None:
            res.update(state="not_in_policy", attrs=[f"VM {vmid} ({ov['name']}) exists on the hypervisor and is not in the policy"])
        elif ov is None:
            res.update(state="not_on_host", attrs=[f"VM {vmid} is in the policy and not on the hypervisor"])
        else:
            res["layers"] = diff_layers(expected(pv), ov["layers"])
            want_pve, got_pve = pv.get("pve", {}), ov["attrs"].get("pve_options", {})
            for key, val in want_pve.items():
                if str(got_pve.get(key, "")) != str(val):
                    res["attrs"].append(f"pve option {key}: policy {val}, live {got_pve.get(key, '(unset)')}")
            guest = pv.get("guest", {})
            if ov["attrs"].get("guest_readable"):
                want_nft = guest.get("nft", "managed")
                if (want_nft == "managed") != bool(ov["attrs"].get("guest_nft")):
                    res["attrs"].append(f"guest nftables: policy {want_nft}, live {'present' if ov['attrs'].get('guest_nft') else 'absent'}")
                for chain in ("input", "forward"):
                    want = guest.get(f"{chain}_policy")
                    if want and ov["attrs"].get(f"{chain}_policy") != want:
                        res["attrs"].append(f"guest {chain} policy: policy {want}, live {ov['attrs'].get(f'{chain}_policy', '(none)')}")
            else:
                res["attrs"].append("guest not readable (guest agent): guest layers not compared")
                for layer in GUEST_LAYERS:
                    res["layers"].pop(layer, None)
            res["conf"] = {}
            if ov.get("conf") is not None and guest.get("nft", "managed") == "managed":
                exp = expected(pv)
                if not ov["attrs"].get("conf_present"):
                    res["attrs"].append("guest /etc/nftables.conf has no table inet filter: a reboot would load no rules")
                else:
                    for chain in ("input", "forward"):
                        missing = sorted(exp[chain] - ov["conf"][chain], key=_flow_sort)
                        extra = sorted(ov["conf"][chain] - exp[chain], key=_flow_sort)
                        if missing or extra:
                            res["conf"][chain] = {"missing": [f.text() for f in missing], "extra": [f.text() for f in extra]}
                        want = guest.get(f"{chain}_policy")
                        if want and ov["attrs"].get(f"conf_{chain}_policy") != want:
                            res["attrs"].append(f"guest /etc/nftables.conf {chain} policy: policy {want}, conf {ov['attrs'].get(f'conf_{chain}_policy') or '(none)'}")
            res["unparsed"] = ov["unparsed"]
            if res["layers"] or res["conf"] or [a for a in res["attrs"] if "not compared" not in a]:
                res["state"] = "drift"
        result["summary"]["vms"] += 1
        if res["state"] != "in_sync":
            result["summary"]["vms_drifted"] += 1
        for layer, d in res["layers"].items():
            result["summary"]["flows_missing"] += len(d["missing"])
            result["summary"]["flows_extra"] += len(d["extra"])
        for chain, d in res.get("conf", {}).items():
            result["summary"]["conf_flows_missing"] += len(d["missing"])
            result["summary"]["conf_flows_extra"] += len(d["extra"])
        result["vms"][vmid] = res
    return result


def _ports_overlap(a: str, b: str) -> bool:
    if "*" in (a, b):
        return True
    alo, ahi = (int(x) for x in (a.split("-") + [a])[:2]) if "-" in a else (int(a), int(a))
    blo, bhi = (int(x) for x in b.split("-")) if "-" in b else (int(b), int(b))
    return alo <= bhi and blo <= ahi


def overlaps(flows: Iterable[Flow], fl: Flow) -> bool:
    """True if some flow in `flows` lets at least part of what `fl` describes through (same or wider/narrower source, port, protocol)."""
    for c in flows:
        if c.iif not in ("", fl.iif) and fl.iif not in ("", c.iif):
            continue
        if "any" not in (c.proto, fl.proto) and c.proto != fl.proto:
            continue
        if "any" not in (c.src, fl.src) and not ipaddress.ip_network(c.src, strict=False).overlaps(ipaddress.ip_network(fl.src, strict=False)):
            continue
        if _ports_overlap(c.port, fl.port):
            return True
    return False


def _inner(src: str, inner: list[str]) -> bool:
    if src == "any":
        return False
    net = ipaddress.ip_network(src, strict=False)
    return any(net.subnet_of(ipaddress.ip_network(i, strict=False)) for i in inner)


def check(policy: dict[str, Any], baseline: set[str] | None = None) -> list[dict[str, str]]:
    """Offline rules on the file itself. A finding id is stable, so a baseline can accept today's known ones and CI fails on new ones."""
    findings: list[dict[str, str]] = []
    inner = policy.get("inner_sources", DEFAULT_INNER_SOURCES)
    lan = policy.get("lan_networks", [])

    def foreign(src: str) -> bool:
        return src != "any" and not _inner(src, inner) and not _inner(src, lan)

    def add(fid: str, severity: str, message: str) -> None:
        if fid not in {f["id"] for f in findings}:
            findings.append({"id": fid, "severity": severity, "message": message})

    for vmid, vm in policy["vms"].items():
        label = f"VM {vmid} {vm.get('name', '')}".strip()
        pve, guest = vm.get("pve", {}), vm.get("guest", {})
        managed = guest.get("nft", "managed") == "managed"
        if str(pve.get("enable", "")) != "1":
            add(f"{vmid}:pve-off", "high", f"{label}: the Proxmox firewall is not enabled for this VM")
        if str(pve.get("policy_in", "")).upper() != "DROP":
            add(f"{vmid}:pve-policy", "high", f"{label}: pve policy_in is {pve.get('policy_in', '(unset)')}, not DROP")
        if not managed and not vm.get("exception"):
            add(f"{vmid}:no-guest-nft", "medium", f"{label}: no guest nftables (only the Proxmox layer filters this VM)")
        for chain in ("input", "forward"):
            if managed and str(guest.get(f"{chain}_policy", "drop")).lower() != "drop":
                add(f"{vmid}:guest-{chain}-policy", "high", f"{label}: guest {chain} policy is {guest.get(f'{chain}_policy')}, not drop")
        exp = expected(vm)
        stale = sorted({fl.src for layer in LAYERS for fl in exp[layer] if foreign(fl.src)}, key=_src_key)
        for src in stale:
            layers = sorted(layer for layer in LAYERS if any(fl.src == src for fl in exp[layer]))
            add(f"{vmid}:foreign-source:{src}", "medium",
                f"{label}: rules for source {src}, which is on no network of this host ({', '.join(lan)}), in {', '.join(layers)}: stale?")
        for gi, g in enumerate(vm.get("groups", [])):
            if not str(g.get("purpose", "")).strip() or str(g.get("purpose", "")).startswith("imported from the live state"):
                add(f"{vmid}:purpose:{_gid(g)}", "info", f"{label}: group {_gid(g)} has no recorded purpose")
            for fl in group_flows(g):
                if fl.src == "any" and fl.proto == "any" and fl.port == "*" and not fl.iif and set(g["layers"]) & {"input", "forward"}:
                    layer = "forward" if "forward" in g["layers"] else "input"
                    add(f"{vmid}:open-chain:{layer}", "high",
                        f"{label}: the guest {layer} chain accepts every packet (a bare `accept`); the rules after it never apply")
                elif fl.src == "any" and not g.get("public"):
                    add(f"{vmid}:any-source:{fl.proto}/{fl.port}", "high", f"{label}: {fl.proto}/{fl.port} is open to any source without `public: true`")
                elif fl.src != "any" and not _inner(fl.src, inner) and ipaddress.ip_network(fl.src, strict=False).prefixlen < WIDE_PREFIX \
                        and not g.get("wide_ok"):
                    add(f"{vmid}:wide:{fl.src}:{fl.proto}/{fl.port}", "medium",
                        f"{label}: source {fl.src} is wider than /{WIDE_PREFIX} for {fl.proto}/{fl.port} without `wide_ok`")
        if not managed:
            continue
        # a Proxmox-allowed flow that no guest chain accepts at all never reaches anything; a specific guest rule that Proxmox drops entirely never fires
        for fl in sorted(exp["pve"], key=_flow_sort):
            if foreign(fl.src):
                continue
            if not overlaps(list(exp["input"]) + list(exp["forward"]), fl):
                add(f"{vmid}:dead-at-guest:{fl.text()}", "medium", f"{label}: {fl.text()} passes the Proxmox firewall and no guest chain accepts it")
        for layer in ("input", "forward"):
            for fl in sorted(exp[layer], key=_flow_sort):
                if fl.port == "*" and fl.proto == "any":
                    continue
                if _inner(fl.src, inner) or foreign(fl.src) or fl.iif:
                    continue
                if not overlaps(exp["pve"], fl):
                    add(f"{vmid}:shadowed:{layer}:{fl.text()}", "medium",
                        f"{label}: the guest {layer} chain allows {fl.text()} but the Proxmox firewall drops it first")
    if baseline is not None:
        for f in findings:
            f["known"] = "yes" if f["id"] in baseline else "no"
    return findings


def _gid(g: dict[str, Any]) -> str:
    return f"{','.join(g.get('from', []))[:60]}|{g.get('proto', 'any')}|{g.get('ports', '*')}"


def why(policy: dict[str, Any], vmid: str, src: str, proto: str, port: int, snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    """Verdict per layer for one flow, from the policy and (if given) from the live snapshot.

    A layer only drops what it filters: the Proxmox layer when the VM firewall is enabled with `policy_in: DROP`, a guest chain when the guest
    has nftables and the chain's policy is drop, and DOCKER-USER only for the ports it has a rule for (its chains jump per port; any other port
    passes it). A flow no rule allows in a layer that does not filter it is "not filtered (why)", never "NOT allowed"."""
    vm = policy["vms"].get(str(vmid))
    if vm is None:
        raise PolicyError(f"VM {vmid} is not in the policy")
    out: dict[str, Any] = {"vm": vmid, "flow": f"{src} {proto}/{port}", "layers": {}}

    def verdict(flows: Iterable[Flow], unfiltered: str = "") -> str:
        flows = list(flows)
        for fl in sorted(flows, key=_flow_sort):
            if fl.proto not in (proto, "any"):
                continue
            if not port_matches(fl.port, port):
                continue
            if src_matches(fl.src, src):
                return f"allowed by {fl.text()}"
        return f"not filtered ({unfiltered})" if unfiltered else "NOT allowed"

    def du_unfiltered(flows: Iterable[Flow]) -> str:
        covered = any(fl.proto in (proto, "any") and port_matches(fl.port, port) for fl in flows)
        return "" if covered else f"no DOCKER-USER rule for {proto}/{port}"

    def pve_unfiltered(opts: dict[str, Any], where: str) -> str:
        if str(opts.get("enable", "")) != "1":
            return f"the Proxmox firewall is off for this VM{where}"
        if str(opts.get("policy_in", "")).upper() != "DROP":
            return f"policy_in {opts.get('policy_in') or '(unset)'}{where}"
        return ""

    def chain_unfiltered(has_nft: bool, chain_policy: str, where: str) -> str:
        if not has_nft:
            return f"no guest nftables{where}"
        if str(chain_policy).lower() != "drop":
            return f"chain policy {chain_policy or '(none)'}{where}"
        return ""

    exp = expected(vm)
    guest = vm.get("guest", {})
    managed = guest.get("nft", "managed") == "managed"
    reasons = {"pve": pve_unfiltered(vm.get("pve", {}), ""), "docker_user": du_unfiltered(exp["docker_user"])}
    for chain in ("input", "forward"):
        reasons[chain] = chain_unfiltered(managed, guest.get(f"{chain}_policy", "drop") if managed else "", "")
    for layer in LAYERS:
        out["layers"][layer] = {"policy": verdict(exp[layer], reasons[layer])}
    if snapshot is not None:
        obs = observe(snapshot)["vms"].get(str(vmid))
        if obs is None:
            for layer in LAYERS:
                out["layers"][layer]["live"] = "VM not found live"
        else:
            attrs = obs["attrs"]
            live = {"pve": pve_unfiltered(attrs.get("pve_options", {}), ""), "docker_user": du_unfiltered(obs["layers"]["docker_user"])}
            for chain in ("input", "forward"):
                if not attrs.get("guest_readable"):
                    live[chain] = "guest not readable"
                else:
                    live[chain] = chain_unfiltered(bool(attrs.get("guest_nft")), attrs.get(f"{chain}_policy", ""), "")
            if not attrs.get("guest_readable"):
                live["docker_user"] = live["docker_user"] and "guest not readable"
            for layer in LAYERS:
                out["layers"][layer]["live"] = verdict(obs["layers"][layer], live[layer])
    for side in ("policy", "live"):
        if all(side in d for d in out["layers"].values()):
            dropped = [l for l, d in out["layers"].items() if d[side] == "NOT allowed"]
            out.setdefault("verdict", {})[side] = f"dropped by {', '.join(dropped)}" if dropped else "passes every layer"
    return out


# ───────────────────────────── apply: the plan ─────────────────────────────

APPLY_LAYERS = ("pve", "input", "forward")
DEFAULT_MAX_CHANGES = 40


def _flow_tuple(fl: Flow) -> list[str]:
    return [fl.src, fl.proto, fl.port, fl.iif]


def sha(text: str) -> str:
    import hashlib  # noqa: PLC0415

    return hashlib.sha256(text.encode()).hexdigest()


def _table_text(raw_ruleset: str) -> str:
    """`table inet filter {...}` as `nft list table inet filter` prints it, taken out of a full `nft list ruleset`."""
    span = _table_span(raw_ruleset, "inet", "filter")
    if span is None:
        return ""
    head = raw_ruleset.rfind("table inet filter {", 0, span[0])
    return raw_ruleset[head : span[1] + 1] + "\n"


def plan_apply(policy: dict[str, Any], snapshot: dict[str, Any], vmid: str, layers: Iterable[str] | None = None, *,
               allow_remove: bool = False, max_changes: int = DEFAULT_MAX_CHANGES) -> dict[str, Any]:
    """What an apply would change on one VM so that the live Proxmox rules, the live guest table and the guest conf equal the policy.

    Pure: nothing is read from or written to a host. `refusals` non-empty means the plan must not be run; the guards are the lockout
    guard (the hypervisor must still reach the VM), removals only with `allow_remove`, a cap on the number of changes, and no VM whose
    live rules the tool cannot fully read."""
    vmid = str(vmid)
    wanted = list(layers) if layers else list(APPLY_LAYERS)
    bad = [l for l in wanted if l not in APPLY_LAYERS]
    if bad:
        raise PolicyError(f"layers that can be applied: {', '.join(APPLY_LAYERS)} (docker_user is managed by its own unit); got {', '.join(bad)}")
    pv = policy["vms"].get(vmid)
    raw = snapshot.get("vms", {}).get(vmid)
    plan: dict[str, Any] = {"vm": vmid, "name": (pv or {}).get("name", ""), "layers": {}, "conf": {}, "refusals": [], "notes": [], "changes": 0}
    if pv is None or raw is None:
        plan["refusals"].append(f"VM {vmid} is not both in the policy and on the hypervisor")
        return plan
    ov = observe(snapshot)["vms"][vmid]
    exp = expected(pv)
    plan["ip"] = raw.get("ip", "")
    if ov["unparsed"]:
        plan["refusals"].append(f"the live state has {len(ov['unparsed'])} rule line(s) this tool does not model (first: {ov['unparsed'][0][:120]}): it would edit blind")
    if exp["docker_user"] != ov["layers"]["docker_user"]:
        units = sorted({str(g["unit"]) for g in pv.get("groups", []) if "docker_user" in g["layers"] and g.get("unit")})
        missing = sorted(f.text() for f in exp["docker_user"] - ov["layers"]["docker_user"])
        extra = sorted(f.text() for f in ov["layers"]["docker_user"] - exp["docker_user"])
        plan["notes"].append(f"docker_user differs ({len(missing)} missing, {len(extra)} extra): it is managed by its own unit "
                             f"({', '.join(units) or 'see the group'}), not applied here")
        plan["docker_user"] = {"missing": missing, "extra": extra, "units": units}
    guest_layers = [l for l in wanted if l in ("input", "forward")]
    texts: dict[str, str] = {}
    old_sha: dict[str, str] = {}
    live_removals: dict[str, set[Flow]] = {}
    live_adds: dict[str, list[Flow]] = {}
    comments: dict[Flow, str] = {}
    for g in pv.get("groups", []):
        if "pve" in g["layers"]:
            for fl in group_flows(g):
                comments.setdefault(fl, str(g.get("purpose", "")).strip())
    # Proxmox layer
    if "pve" in wanted:
        rem = ov["layers"]["pve"] - exp["pve"]
        add = exp["pve"] - ov["layers"]["pve"]
        if (rem or add) and raw.get("fw") is None:
            plan["refusals"].append("this VM has no /etc/pve/firewall file: create it by hand first (enabling a firewall is not done by apply)")
        elif rem or add:
            try:
                rep: list[dict[str, str]] = []
                texts["pve"] = edit_pve(raw["fw"], rem, [(f, comments.get(f, "")) for f in sorted(add, key=_flow_sort)], observe(snapshot)["ipsets"], rep)
                old_sha["pve"] = sha(raw["fw"])
                plan["layers"]["pve"] = {"remove": sorted(f.text() for f in rem), "add": sorted(f.text() for f in add)}
                if rep:
                    plan["layers"]["pve"]["replace"] = rep
            except PolicyError as exc:
                plan["refusals"].append(f"pve: {exc}")
    # guest layers: the live table and the conf are separate texts with separate differences
    if guest_layers:
        g = raw.get("guest") or {}
        guest_diff = any(exp[l] != ov["layers"][l] for l in guest_layers) or any(
            ov.get("conf") is not None and exp[l] != ov["conf"][l] for l in guest_layers)
        if guest_diff and not g.get("ok"):
            plan["refusals"].append("the guest is not readable through the guest agent: guest layers cannot be planned")
        elif guest_diff and (pv.get("guest", {}).get("nft", "managed") != "managed" or not ov["attrs"].get("guest_nft")):
            plan["refusals"].append("this VM has no guest nftables to edit (enabling one is not done by apply)")
        elif guest_diff:
            table = g.get("nft_table") or _table_text(g.get("nft", ""))
            if not table:
                plan["refusals"].append("could not read the live table inet filter")
            else:
                for l in guest_layers:
                    rem, add = ov["layers"][l] - exp[l], exp[l] - ov["layers"][l]
                    if rem or add:
                        live_removals[l], live_adds[l] = rem, sorted(add, key=_flow_sort)
                        plan["layers"][l] = {"remove": sorted(f.text() for f in rem), "add": sorted(f.text() for f in add)}
                conf_rem: dict[str, set[Flow]] = {}
                conf_add: dict[str, list[Flow]] = {}
                if ov.get("conf") is None or not ov["attrs"].get("conf_present"):
                    if any(exp[l] != ov["layers"][l] for l in guest_layers):
                        plan["refusals"].append("the guest has no readable /etc/nftables.conf with a table inet filter: the change could not be made to survive a reboot")
                else:
                    for l in guest_layers:
                        rem, add = ov["conf"][l] - exp[l], exp[l] - ov["conf"][l]
                        if rem or add:
                            conf_rem[l], conf_add[l] = rem, sorted(add, key=_flow_sort)
                            plan["conf"][l] = {"remove": sorted(f.text() for f in rem), "add": sorted(f.text() for f in add)}
                try:
                    # a rule that keeps some of its flows is rewritten in its place: live through the same one-file load of the table, persisted
                    # as an edited line of the conf (never reloaded)
                    if live_removals or live_adds:
                        rep = []
                        texts["table"] = edit_nft(table, live_removals, live_adds, rep)
                        old_sha["table"] = sha(table)
                        for r in rep:
                            plan["layers"][r["chain"]].setdefault("replace", []).append({"old": r["old"], "new": r["new"]})
                    if conf_rem or conf_add:
                        rep = []
                        texts["conf"] = edit_nft(g["conf"], conf_rem, conf_add, rep)
                        old_sha["conf"] = sha(g["conf"])
                        for r in rep:
                            plan["conf"][r["chain"]].setdefault("replace", []).append({"old": r["old"], "new": r["new"]})
                except PolicyError as exc:
                    plan["refusals"].append(f"guest: {exc}")
    plan["changes"] = sum(len(d["remove"]) + len(d["add"]) for d in list(plan["layers"].values()) + list(plan["conf"].values()))
    removals = sum(len(d["remove"]) for d in list(plan["layers"].values()) + list(plan["conf"].values()))
    if removals and not allow_remove:
        plan["refusals"].append(f"{removals} rule(s) would be removed: pass --allow-remove if that is intended")
    if plan["changes"] > max_changes:
        plan["refusals"].append(f"{plan['changes']} changes exceed the cap of {max_changes} for one run: raise --max-changes only after reading the plan")
    # the lockout guard: after the change the hypervisor must still reach the VM, in every layer that is touched
    for guard in policy.get("guard", []):
        gflows = group_flows({"from": [guard["src"]], "proto": guard.get("proto", "tcp"), "ports": [str(guard.get("port", "22"))]})
        touched = [l for l in guard["layers"] if l in plan["layers"] or (l == "input" and plan["conf"])]
        for l in touched:
            for gf in gflows:
                if not overlaps(exp[l], gf) or gf not in exp[l]:
                    plan["refusals"].append(f"lockout guard: after this change the {l} layer would no longer allow {gf.text()}")
    plan["texts"], plan["old_sha"] = texts, old_sha
    after: dict[str, Any] = {}
    if "pve" in texts:
        after["pve"] = [_flow_tuple(f) for f in sorted(exp["pve"], key=_flow_sort)]
    if "table" in texts:
        for l in guest_layers:
            after[l] = [_flow_tuple(f) for f in sorted(exp[l], key=_flow_sort)]
    if "conf" in texts:
        for l in guest_layers:
            after["conf_" + l] = [_flow_tuple(f) for f in sorted(exp[l], key=_flow_sort)]
    plan["expect_after"] = after
    plan["probes"] = [{"host": plan["ip"], "port": int(g.get("port", 22))} for g in policy.get("guard", []) if g.get("proto", "tcp") == "tcp" and plan["ip"]]
    if not plan["changes"] and not plan["refusals"]:
        plan["notes"].append("nothing to apply: the VM already matches the policy in the layers asked for")
    return plan


# ───────────────────────────── collecting the live state ─────────────────────────────

# Runs on the hypervisor (python3 from stdin). Read-only: reads the firewall files, `qm config` and, through the guest agent,
# the guest's `nft list ruleset` and DOCKER-USER chains.
COLLECTOR = r'''
import glob, json, os, re, subprocess, sys, time
out = {"cluster_fw": open("/etc/pve/firewall/cluster.fw").read() if os.path.exists("/etc/pve/firewall/cluster.fw") else "", "vms": {}}
lst = subprocess.run(["qm", "list"], capture_output=True, text=True).stdout.splitlines()[1:]
GUEST = r"""echo '###NFT'; nft list ruleset 2>&1; echo '###NFTT'; nft list table inet filter 2>&1; echo '###IPT'; iptables -S DOCKER-USER 2>&1; for c in $(iptables -S DOCKER-USER 2>/dev/null | sed -n 's/.* -j \([A-Za-z0-9_-]*\)$/\1/p' | grep -v -E '^(RETURN|ACCEPT|DROP|REJECT)$' | sort -u); do iptables -S "$c" 2>&1; done; echo '###CONF'; cat /etc/nftables.conf 2>/dev/null; echo '###IP'; ip -4 -o addr show scope global | awk '{print $2, $4}' | head -3"""
ONLY = globals().get("ONLY")
for line in lst:
    f = line.split()
    if len(f) < 3 or not f[0].isdigit():
        continue
    vmid, name, status = f[0], f[1], f[2]
    if ONLY and vmid not in ONLY:
        continue
    fw = open(f"/etc/pve/firewall/{vmid}.fw").read() if os.path.exists(f"/etc/pve/firewall/{vmid}.fw") else None
    if fw is None and status != "running":
        continue
    cfg = subprocess.run(["qm", "config", vmid], capture_output=True, text=True).stdout
    ip = ""
    m = re.search(r"ip=(\d+\.\d+\.\d+\.\d+)", cfg)
    entry = {"name": name, "status": status, "fw": fw, "qm_net": [l for l in cfg.splitlines() if l.startswith("net")], "guest": {"ok": False}}
    if status == "running":
        try:
            r = subprocess.run(["qm", "guest", "exec", vmid, "--timeout", "25", "--", "/bin/sh", "-c", GUEST], capture_output=True, text=True, timeout=40)
            data = json.loads(r.stdout) if r.stdout.strip().startswith("{") else {}
            text = data.get("out-data", "")
            if data.get("exitcode", 1) == 0 and "###NFT" in text:
                parts = {}
                for m in re.finditer(r"^###(\w+)\n(.*?)(?=^###\w+\n|\Z)", text, re.S | re.M):
                    parts[m.group(1)] = m.group(2)
                mm = re.search(r"eth0 (\d+\.\d+\.\d+\.\d+)", parts.get("IP", ""))
                ip = mm.group(1) if mm else ip
                entry["guest"] = {"ok": True, "nft": parts.get("NFT", ""), "nft_table": parts.get("NFTT", ""), "iptables": parts.get("IPT", ""), "conf": parts.get("CONF", "")}
        except Exception as exc:
            entry["guest"] = {"ok": False, "error": str(exc)[:200]}
    entry["ip"] = ip
    out["vms"][vmid] = entry
print(json.dumps(out))
'''


def collect_live(host: str, ssh_alias: str, timeout: int = 600, only: list[str] | None = None) -> dict[str, Any]:
    script = (f"ONLY = {json.dumps([str(o) for o in only])}\n" if only else "") + COLLECTOR
    try:
        proc = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", ssh_alias, "python3", "-"],
                              input=script, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise PolicyError(f"could not read {ssh_alias}: {exc}") from exc
    if proc.returncode != 0 or not proc.stdout.strip().startswith("{"):
        raise PolicyError(f"could not read {ssh_alias}: exit {proc.returncode} {proc.stderr.strip()[:200]}")
    snap = json.loads(proc.stdout)
    snap.update({"host": host, "ssh": ssh_alias, "taken_at": int(time.time())})
    return snap


# ───────────────────────────── apply: what runs on the hypervisor ─────────────────────────────
# One self-contained script, sent over ssh with this module embedded as `np`. The order is the safety property:
#   1 re-read everything the plan was made from and refuse if any of it changed (nothing has been touched yet)
#   2 save backups and write rollback.py, which restores them without needing this script or the runner
#   3 ARM A TIMER on the hypervisor that runs rollback.py after `hold` seconds (if arming fails, stop: nothing is touched yet)
#   4 change: guest conf (persistence, never reloaded), guest live table (one atomic nft -f that flushes only table inet filter),
#     Proxmox file; `touched.json` is updated before each, so a crash in the middle is still undone by the timer
#   5 verify the result exactly, and that the hypervisor still reaches the VM (tcp probe) and the guest agent answers
#   6 only then disarm the timer; any failure runs rollback.py at once and checks the restore
# Exit: 0 applied and verified, 5 precondition failed (nothing changed), 6 failed and rolled back and verified, 7 failed and the restore
# could not be verified (page someone).

APPLY_REMOTE = r"""
import base64, hashlib, json, os, socket, subprocess, sys, time

PVE_DIR = os.environ.get("NETPOLICY_PVE_DIR", "/etc/pve/firewall")
STATE = os.environ.get("NETPOLICY_STATE_DIR", "/var/lib/netpolicy")
VM, IP = PLAN["vm"], PLAN.get("ip", "")
CONF = PLAN.get("guest_conf_path", "/etc/nftables.conf")
HOLD = int(PLAN.get("hold", 180))
SIM = PLAN.get("simulate_failure", "")
TS = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
RUN = f"{STATE}/apply/{TS}-vm{VM}"
UNIT = f"netpolicy-rollback-{VM}-{TS}"
TEXTS, OLD = PLAN["texts"], PLAN["old_sha"]
T0 = time.time()
touched = {"pve": False, "table": False, "conf": False}


def sha(t):
    return hashlib.sha256(t.encode()).hexdigest()


def log(event, **kw):
    line = json.dumps({"ts": int(time.time()), "vm": VM, "event": event, **kw})
    print(line, flush=True)
    try:
        with open(f"{STATE}/apply/events.jsonl", "a") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def sh(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)


def guest(cmd, timeout=30):
    r = sh(["qm", "guest", "exec", VM, "--timeout", str(timeout), "--", "/bin/sh", "-c", cmd], timeout=timeout + 20)
    try:
        d = json.loads(r.stdout)
    except ValueError:
        return 255, (r.stdout + r.stderr)[:300]
    return d.get("exitcode", 255), d.get("out-data", "") + d.get("err-data", "")


def guest_write(path, text, same_as=None):
    b64 = base64.b64encode(text.encode()).decode()
    tmp = path + ".netpolicy-new"
    chunks = [b64[i:i + 40000] for i in range(0, len(b64), 40000)] or [""]
    for i, ch in enumerate(chunks):
        rc, out = guest(f"echo {ch} {'>' if i == 0 else '>>'} {tmp}.b64")
        if rc != 0:
            raise RuntimeError(f"writing {path} in the guest failed: {out[:120]}")
    ref = f"&& chmod --reference={same_as} {tmp} && chown --reference={same_as} {tmp} " if same_as else ""
    rc, out = guest(f"base64 -d {tmp}.b64 > {tmp} {ref}&& mv {tmp} {path} && rm -f {tmp}.b64")
    if rc != 0:
        raise RuntimeError(f"installing {path} in the guest failed: {out[:120]}")


def flows_of(parsed_flows):
    return {(f.src, f.proto, f.port, f.iif) for f in parsed_flows}


def want(key):
    return {tuple(x) for x in PLAN["expect_after"][key]}


def abort_pre(msg):
    log("precondition_failed", error=msg, changed=False)
    sys.exit(5)


os.makedirs(f"{STATE}/apply", mode=0o700, exist_ok=True)
os.makedirs(RUN, mode=0o700, exist_ok=True)
cur = {}
fw_path = f"{PVE_DIR}/{VM}.fw"
use_guest = "table" in TEXTS or "conf" in TEXTS
log("start", run=RUN, layers=sorted(TEXTS), hold=HOLD)

# 1 preconditions: everything the plan was made from must still be what it was
if "pve" in TEXTS:
    cur["pve"] = open(fw_path).read() if os.path.exists(fw_path) else None
    if cur["pve"] is None or sha(cur["pve"]) != OLD["pve"]:
        abort_pre("the firewall file changed since the plan was made")
if use_guest:
    rc, out = guest("true")
    if rc != 0:
        abort_pre(f"the guest agent does not answer: {out[:100]}")
    if "table" in TEXTS:
        rc, cur["table"] = guest("nft list table inet filter")
        if rc != 0 or sha(cur["table"]) != OLD["table"]:
            abort_pre("the live table inet filter changed since the plan was made")
    if "conf" in TEXTS:
        rc, cur["conf"] = guest(f"cat {CONF}")
        if rc != 0 or sha(cur["conf"]) != OLD["conf"]:
            abort_pre(f"{CONF} changed since the plan was made")

# 2 backups, and the rollback script that needs nothing from this one
for key, name in (("pve", "fw.bak"), ("table", "nft_table.bak"), ("conf", "nftables.conf.bak")):
    if key in cur:
        with open(f"{RUN}/{name}", "w") as fh:
            fh.write(cur[key])
if "conf" in TEXTS:
    guest(f"cp -p {CONF} {CONF}.bak-netpolicy-{TS}")
CFG = {"vm": VM, "run": RUN, "state": STATE, "pve_dir": PVE_DIR, "conf": CONF}
with open(f"{RUN}/rollback.py", "w") as fh:
    fh.write(ROLLBACK_SRC.replace("__CFG__", json.dumps(CFG)))
os.chmod(f"{RUN}/rollback.py", 0o700)
json.dump(touched, open(f"{RUN}/touched.json", "w"))

# 3 arm the timer BEFORE touching anything; if it cannot be armed nothing has changed
armed = sh(["systemd-run", "--unit", UNIT, "--on-active", f"{HOLD}s", "--collect", "--description", f"netpolicy rollback of VM {VM}",
            sys.executable, f"{RUN}/rollback.py"])
if armed.returncode != 0:
    abort_pre(f"could not arm the rollback timer: {(armed.stderr or armed.stdout)[:150]}")
log("armed", unit=UNIT, seconds=HOLD)


def mark(layer):
    touched[layer] = True
    json.dump(touched, open(f"{RUN}/touched.json", "w"))


def rollback(reason):
    log("rolling_back", reason=reason)
    r = sh([sys.executable, f"{RUN}/rollback.py"])
    log("rollback_ran", rc=r.returncode, out=(r.stdout + r.stderr)[-300:])
    sh(["systemctl", "stop", UNIT + ".timer"])
    problems = []
    if touched["pve"]:
        if open(fw_path).read() != cur["pve"]:
            problems.append("the firewall file is not back to its saved text")
    if touched["table"]:
        rc, out = guest("nft list table inet filter")
        if rc != 0:
            problems.append(f"the live table could not be read to verify the restore: {out[:80]}")
        else:
            a, b = np.parse_nft(out), np.parse_nft(cur["table"])
            for ch in ("input", "forward"):
                ca, cb = a["chains"].get(ch), b["chains"].get(ch)
                if ca is None or cb is None or flows_of(ca["flows"]) != flows_of(cb["flows"]) or ca["policy"] != cb["policy"]:
                    problems.append(f"the live {ch} chain is not back to its saved rules")
    if touched["conf"]:
        rc, out = guest(f"cat {CONF}")
        if rc != 0 or out != cur["conf"]:
            problems.append(f"{CONF} is not back to its saved text")
    if problems or r.returncode != 0:
        log("rollback_unverified", problems=problems, rc=r.returncode)
        sys.exit(7)
    log("rolled_back", verified=True)
    sys.exit(6)


try:
    # 4 change
    if "conf" in TEXTS:
        mark("conf")
        guest_write("/var/tmp/netpolicy-conf-check.nft", TEXTS["conf"])
        rc, out = guest("nft -c -f /var/tmp/netpolicy-conf-check.nft; r=$?; rm -f /var/tmp/netpolicy-conf-check.nft; exit $r")
        if rc != 0:
            raise RuntimeError(f"the new {CONF} does not pass nft -c: {out[:200]}")
        guest_write(CONF, TEXTS["conf"], same_as=CONF)
        log("conf_written")
    if "table" in TEXTS:
        mark("table")
        guest_write("/var/tmp/netpolicy-live.nft", "flush table inet filter\n" + TEXTS["table"])
        rc, out = guest("nft -c -f /var/tmp/netpolicy-live.nft")
        if rc != 0:
            raise RuntimeError(f"the new table does not pass nft -c: {out[:200]}")
        rc, out = guest("nft -f /var/tmp/netpolicy-live.nft; r=$?; rm -f /var/tmp/netpolicy-live.nft; exit $r")
        if rc != 0:
            raise RuntimeError(f"loading the new table failed: {out[:200]}")
        log("table_loaded")
    if "pve" in TEXTS:
        mark("pve")
        with open(fw_path, "w") as fh:
            fh.write(TEXTS["pve"])
        c = sh(["pve-firewall", "compile"])
        if c.returncode != 0:
            raise RuntimeError(f"pve-firewall compile refused the new file: {(c.stderr or c.stdout)[:200]}")
        log("pve_written")
    if SIM == "crash":
        log("simulated_crash")
        os._exit(9)
    # 5 verify
    problems = []
    if SIM == "verify":
        problems.append("simulated failure")
    if "pve" in TEXTS:
        t = open(fw_path).read()
        if t != TEXTS["pve"]:
            problems.append("the firewall file is not what was written")
        got = flows_of(f for f, _ in np.parse_pve(t, PLAN.get("ipsets"))["flows"])
        if got != want("pve"):
            problems.append("the Proxmox flows after the change are not the intended ones")
    if "table" in TEXTS:
        rc, out = guest("nft list table inet filter")
        parsed, before = np.parse_nft(out), np.parse_nft(cur["table"])
        if rc != 0:
            problems.append(f"the live table could not be read to verify it: {out[:80]}")
        for ch in ("input", "forward"):
            got = parsed["chains"].get(ch)
            if got is None or flows_of(got["flows"]) != want(ch):
                problems.append(f"the live {ch} flows after the change are not the intended ones")
            elif got["policy"] != before["chains"][ch]["policy"]:
                problems.append(f"the {ch} policy changed")
    if "conf" in TEXTS:
        rc, out = guest(f"cat {CONF}")
        if rc != 0 or out != TEXTS["conf"]:
            problems.append(f"{CONF} is not what was written")
        parsed = np.parse_nft(out)
        for ch in ("input", "forward"):
            got = parsed["chains"].get(ch)
            if got is None or flows_of(got["flows"]) != want("conf_" + ch):
                problems.append(f"the conf {ch} flows are not the intended ones")
    for pr in PLAN.get("probes", []):
        try:
            socket.create_connection((pr["host"], pr["port"]), timeout=5).close()
        except OSError as exc:
            problems.append(f"the hypervisor can no longer reach {pr['host']}:{pr['port']} ({exc})")
    if use_guest:
        rc, out = guest("true")
        if rc != 0:
            problems.append("the guest agent no longer answers")
    if problems:
        raise RuntimeError("verification failed: " + "; ".join(problems))
    # 6 disarm: only after everything checked out, and only if the timer has not already acted
    sh(["systemctl", "stop", UNIT + ".timer"])
    if os.path.exists(f"{RUN}/rolled-back"):
        raise RuntimeError("the rollback timer fired during the run: the old state was restored")
    log("applied", seconds=int(time.time() - T0), run=RUN)
    json.dump({"ok": True, "run": RUN, "layers": sorted(TEXTS)}, open(f"{RUN}/summary.json", "w"))
    sys.exit(0)
except SystemExit:
    raise
except Exception as exc:
    rollback(str(exc)[:300])
"""

ROLLBACK_SRC = r"""
import base64, json, os, shutil, subprocess, sys, time
C = json.loads('__CFG__')
VM, RUN, CONF = C["vm"], C["run"], C["conf"]
T = json.load(open(RUN + "/touched.json")) if os.path.exists(RUN + "/touched.json") else {}
LOG = C["state"] + "/rollback.log"
failed = []


def log(msg):
    with open(LOG, "a") as fh:
        fh.write(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + f" vm{VM} {msg}\n")


def guest(cmd):
    r = subprocess.run(["qm", "guest", "exec", VM, "--timeout", "30", "--", "/bin/sh", "-c", cmd], capture_output=True, text=True, timeout=60)
    d = json.loads(r.stdout)
    return d.get("exitcode", 255), d.get("out-data", "") + d.get("err-data", "")


def put(path, text, ref=None):
    b64 = base64.b64encode(text.encode()).decode()
    tmp = path + ".netpolicy-rb"
    for i, ch in enumerate([b64[i:i + 40000] for i in range(0, len(b64), 40000)] or [""]):
        guest(f"echo {ch} {'>' if i == 0 else '>>'} {tmp}.b64")
    r = f"&& chmod --reference={ref} {tmp} && chown --reference={ref} {tmp} " if ref else ""
    rc, out = guest(f"base64 -d {tmp}.b64 > {tmp} {r}&& mv {tmp} {path} && rm -f {tmp}.b64")
    if rc != 0:
        raise RuntimeError(out[:120])


log(f"rollback starts, touched={T}")
if T.get("table") and os.path.exists(RUN + "/nft_table.bak"):
    try:
        put("/var/tmp/netpolicy-rb.nft", "flush table inet filter\n" + open(RUN + "/nft_table.bak").read())
        rc, out = guest("nft -c -f /var/tmp/netpolicy-rb.nft && nft -f /var/tmp/netpolicy-rb.nft; r=$?; rm -f /var/tmp/netpolicy-rb.nft; exit $r")
        if rc != 0:
            raise RuntimeError(out[:120])
        log("guest table restored")
    except Exception as exc:
        failed.append("table"); log(f"guest table NOT restored: {exc}")
if T.get("conf") and os.path.exists(RUN + "/nftables.conf.bak"):
    try:
        put(CONF, open(RUN + "/nftables.conf.bak").read(), ref=CONF)
        log("guest conf restored")
    except Exception as exc:
        failed.append("conf"); log(f"guest conf NOT restored: {exc}")
if T.get("pve") and os.path.exists(RUN + "/fw.bak"):
    try:
        with open(C["pve_dir"] + f"/{VM}.fw", "w") as fh:
            fh.write(open(RUN + "/fw.bak").read())
        r = subprocess.run(["pve-firewall", "compile"], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(r.stderr[:120])
        log("proxmox file restored")
    except Exception as exc:
        failed.append("pve"); log(f"proxmox file NOT restored: {exc}")
open(RUN + "/rolled-back", "w").write(json.dumps({"failed": failed}))
log("rollback done" + (f", FAILED: {failed}" if failed else ", all restored"))
sys.exit(1 if failed else 0)
"""


def build_remote_script(plan: dict[str, Any], *, hold: int = 180, simulate_failure: str = "", ipsets: dict[str, list[str]] | None = None,
                        guest_conf_path: str = "/etc/nftables.conf", source: str | None = None) -> str:
    """The script `apply` sends to the hypervisor: the plan, this module as `np`, then APPLY_REMOTE."""
    src = source if source is not None else Path(__file__).read_text()
    payload = {k: plan[k] for k in ("vm", "ip", "texts", "old_sha", "expect_after", "probes")}
    payload.update({"hold": hold, "simulate_failure": simulate_failure, "ipsets": ipsets or {}, "guest_conf_path": guest_conf_path})
    # pure ASCII (json escapes everything else): `python3 -` decodes stdin with the locale, which on a host without UTF-8 would choke on the module
    return (
        "# -*- coding: utf-8 -*-\n"
        "import json, sys, types\n"
        f"PLAN = json.loads({json.dumps(json.dumps(payload))})\n"
        f"NP_SRC = json.loads({json.dumps(json.dumps(src))})\n"
        f"ROLLBACK_SRC = json.loads({json.dumps(json.dumps(ROLLBACK_SRC))})\n"
        "np = types.ModuleType('netpolicy')\nsys.modules['netpolicy'] = np\n"
        "np.__dict__['__file__'] = '/usr/local/lib/netpolicy/netpolicy.py'\n"
        "exec(compile(NP_SRC, 'netpolicy.py', 'exec'), np.__dict__)\n" + APPLY_REMOTE
    )


# ───────────────────────────── metrics ─────────────────────────────


def metrics_text(result: dict[str, Any] | None, host: str, could_not_look: bool, findings: int = 0) -> str:
    now = int(time.time())
    lines = [
        "# HELP netpolicy_last_run_timestamp_seconds Time of the last drift run (dead-man's switch).",
        "# TYPE netpolicy_last_run_timestamp_seconds gauge",
        f'netpolicy_last_run_timestamp_seconds{{hypervisor="{host}"}} {now}',
        "# HELP netpolicy_could_not_look 1 when the live state could not be read.",
        "# TYPE netpolicy_could_not_look gauge",
        f'netpolicy_could_not_look{{hypervisor="{host}"}} {1 if could_not_look else 0}',
    ]
    if result is not None and not could_not_look:
        lines += ["# HELP netpolicy_flows Flows that differ between the policy file and the live state.", "# TYPE netpolicy_flows gauge"]
        for vmid, res in result["vms"].items():
            name = res.get("name", "")
            for layer in LAYERS:
                d = res["layers"].get(layer, {"missing": [], "extra": []})
                for kind in ("missing", "extra"):
                    lines.append(f'netpolicy_flows{{hypervisor="{host}",vm="{vmid}",layer="{layer}",kind="{kind}"}} {len(d[kind])}')
        lines += ["# HELP netpolicy_conf_flows Flows that differ between the policy file and the guest's /etc/nftables.conf (what a reboot would load).",
                  "# TYPE netpolicy_conf_flows gauge"]
        for vmid, res in result["vms"].items():
            for chain in ("input", "forward"):
                d = res.get("conf", {}).get(chain, {"missing": [], "extra": []})
                for kind in ("missing", "extra"):
                    lines.append(f'netpolicy_conf_flows{{hypervisor="{host}",vm="{vmid}",chain="{chain}",kind="{kind}"}} {len(d[kind])}')
        lines += ["# HELP netpolicy_vm_in_sync 1 when the VM matches the policy.", "# TYPE netpolicy_vm_in_sync gauge"]
        for vmid, res in result["vms"].items():
            lines.append(f'netpolicy_vm_in_sync{{hypervisor="{host}",vm="{vmid}"}} {1 if res["state"] == "in_sync" else 0}')
        lines += ["# HELP netpolicy_unparsed_lines Live rules the parser does not model (never silently ignored).", "# TYPE netpolicy_unparsed_lines gauge"]
        for vmid, res in result["vms"].items():
            lines.append(f'netpolicy_unparsed_lines{{hypervisor="{host}",vm="{vmid}"}} {len(res["unparsed"])}')
    return "\n".join(lines) + "\n"


# ───────────────────────────── CLI ─────────────────────────────


def _print_plan(plan: dict[str, Any]) -> None:
    print(f"VM {plan['vm']} {plan.get('name', '')}: {plan['changes']} change(s)")
    for title, block in (("live", plan["layers"]), ("persisted in /etc/nftables.conf (a reboot loads this)", plan["conf"])):
        for layer, d in block.items():
            for kind, sign in (("remove", "-"), ("add", "+")):
                for item in d[kind][:12]:
                    print(f"  {title} {layer} {sign} {item}")
                if len(d[kind]) > 12:
                    print(f"  {title} {layer} {sign} ... {len(d[kind]) - 12} more")
            for r in d.get("replace", []):
                print(f"  {title} {layer} REPLACE {r['old']}")
                print(f"  {title} {layer}    with {r['new']}  (same position)")
    du = plan.get("docker_user") or {}
    for kind, sign in (("extra", "-"), ("missing", "+")):
        for item in du.get(kind, [])[:12]:
            print(f"  docker_user (by its unit) {sign} {item}")
        if len(du.get(kind, [])) > 12:
            print(f"  docker_user (by its unit) {sign} ... {len(du[kind]) - 12} more")
    for n in plan["notes"]:
        print(f"  note: {n}")
    for r in plan["refusals"]:
        print(f"  REFUSED: {r}")


def _policy_path(arg: str | None, host: str | None = None) -> Path:
    if arg:
        return Path(arg)
    files = sorted(POLICY_DIR.glob("*.yaml"))
    if host:
        return POLICY_DIR / f"{host}.yaml"
    if len(files) == 1:
        return files[0]
    raise PolicyError("give --policy (several policy files exist)")


def _load_snapshot(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check")
    p.add_argument("--policy")
    p.add_argument("--baseline", help="JSON list of finding ids accepted as known (default: <policy>.baseline.json if it exists)")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("snapshot")
    p.add_argument("--host", required=True)
    p.add_argument("--ssh")
    p.add_argument("--out")
    p = sub.add_parser("import")
    p.add_argument("--snapshot", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("drift")
    p.add_argument("--policy")
    p.add_argument("--snapshot")
    p.add_argument("--live", action="store_true")
    p.add_argument("--textfile-dir", nargs="?", const=DEFAULT_TEXTFILE_DIR)
    p.add_argument("--ssh", help="ssh alias of the hypervisor (default: collect.ssh of the policy file)")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("render")
    p.add_argument("layer", choices=["pve"])
    p.add_argument("--policy")
    p.add_argument("--vm", required=True)
    p = sub.add_parser("why")
    p.add_argument("--policy")
    p.add_argument("--vm", required=True)
    p.add_argument("--src", required=True)
    p.add_argument("--port", required=True, type=int)
    p.add_argument("--proto", default="tcp")
    p.add_argument("--snapshot")
    p.add_argument("--live", action="store_true")
    p = sub.add_parser("apply")
    p.add_argument("--policy")
    p.add_argument("--vm", required=True)
    p.add_argument("--layers", help="comma separated subset of pve,input,forward (default: all that differ)")
    p.add_argument("--allow-remove", action="store_true")
    p.add_argument("--max-changes", type=int, default=DEFAULT_MAX_CHANGES)
    p.add_argument("--hold", type=int, default=180, help="seconds before the timer on the hypervisor rolls back by itself")
    p.add_argument("--yes", action="store_true", help="really apply (without it only the plan is printed)")
    p.add_argument("--snapshot", help="plan from a saved snapshot (plan only: --yes always reads the live state)")
    p.add_argument("--ssh", help="ssh alias of the hypervisor (default: collect.ssh of the policy file)")
    p.add_argument("--simulate-failure", choices=["verify", "crash"], default="", help="drill: fail the verification, or die after applying")
    p.add_argument("--guest-conf-path", default="/etc/nftables.conf", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)

    try:
        if a.cmd == "check":
            paths = [Path(a.policy)] if a.policy else sorted(POLICY_DIR.glob("*.yaml"))
            if not paths:
                raise PolicyError(f"no policy file in {POLICY_DIR}")
            total_new = 0
            report: list[dict[str, Any]] = []
            for path in paths:
                policy = load_policy(path)
                base_path = Path(a.baseline) if a.baseline else path.with_suffix(".baseline.json")
                baseline = set(json.loads(base_path.read_text())) if base_path.exists() else set()
                findings = check(policy, baseline)
                new = [f for f in findings if f["known"] == "no" and f["severity"] != "info"]
                total_new += len(new)
                report.append({"policy": path.name, "findings": findings, "new": len(new)})
                if not a.json:
                    by = collections.Counter((f["severity"], f["known"]) for f in findings)
                    print(f"{path.name}: {len(policy['vms'])} VMs, {sum(len(v['groups']) for v in policy['vms'].values())} groups, findings {dict(by)}")
                    for f in new:
                        print(f"  NEW {f['severity']}: {f['message']}")
            if a.json:
                print(json.dumps({"policies": report, "new": total_new}, indent=1))
            return 1 if total_new else 0
        if a.cmd == "snapshot":
            snap = collect_live(a.host, a.ssh or f"hv-{a.host}")
            text = json.dumps(snap)
            if a.out:
                Path(a.out).write_text(text)
                print(f"snapshot of {a.host}: {len(snap['vms'])} VMs -> {a.out}")
            else:
                print(text)
            return 0
        if a.cmd == "import":
            snap = _load_snapshot(a.snapshot)
            out = Path(a.out)
            previous = load_policy(out) if out.exists() else None
            policy = build_policy(snap, previous)
            write_policy(policy, out)
            n = sum(len(v["groups"]) for v in policy["vms"].values())
            print(f"wrote {out}: {len(policy['vms'])} VMs, {n} groups")
            return 0
        if a.cmd == "drift":
            policy = load_policy(_policy_path(a.policy))
            try:
                snap = _load_snapshot(a.snapshot) if a.snapshot else collect_live(policy["host"], a.ssh or policy.get("collect", {}).get("ssh") or f"hv-{policy['host']}")
            except PolicyError as exc:
                print(f"could not look: {exc}", file=sys.stderr)
                if a.textfile_dir:
                    _write_textfile(a.textfile_dir, metrics_text(None, policy["host"], True), policy["host"])
                return 3
            result = drift(policy, snap)
            for vmid, res in result["vms"].items():
                res["name"] = (policy["vms"].get(vmid) or {}).get("name") or snap["vms"].get(vmid, {}).get("name", "")
            if a.textfile_dir:
                _write_textfile(a.textfile_dir, metrics_text(result, policy["host"], False), policy["host"])
            if a.json:
                print(json.dumps(result, indent=1))
            else:
                s = result["summary"]
                print(f"{policy['host']}: {s['vms']} VMs, {s['vms_drifted']} drifted, {s['flows_missing']} flows missing, {s['flows_extra']} extra"
                      + (f"; reboot hazard: {s['conf_flows_missing']} missing from and {s['conf_flows_extra']} extra in /etc/nftables.conf" if s["conf_flows_missing"] or s["conf_flows_extra"] else ""))
                for vmid, res in result["vms"].items():
                    if res["state"] == "in_sync":
                        continue
                    print(f"  VM {vmid} {res.get('name', '')}: {res['state']}")
                    for layer, d in res["layers"].items():
                        for kind in ("missing", "extra"):
                            for item in d[kind][:8]:
                                print(f"    {layer} {kind}: {item}")
                            if len(d[kind]) > 8:
                                print(f"    {layer} {kind}: ... {len(d[kind]) - 8} more")
                    for chain, d in res.get("conf", {}).items():
                        for kind in ("missing", "extra"):
                            for item in d[kind][:8]:
                                print(f"    reboot (conf {chain}) {kind}: {item}")
                            if len(d[kind]) > 8:
                                print(f"    reboot (conf {chain}) {kind}: ... {len(d[kind]) - 8} more")
                    for attr in res["attrs"]:
                        print(f"    {attr}")
                    for u in res["unparsed"][:4]:
                        print(f"    not modelled: {u}")
            return 2 if result["summary"]["vms_drifted"] else 0
        if a.cmd == "render":
            policy = load_policy(_policy_path(a.policy))
            vm = policy["vms"].get(str(a.vm))
            if vm is None:
                raise PolicyError(f"VM {a.vm} is not in the policy")
            sys.stdout.write(render_pve(vm))
            return 0
        if a.cmd == "apply":
            policy = load_policy(_policy_path(a.policy))
            alias = a.ssh or policy.get("collect", {}).get("ssh") or f"hv-{policy['host']}"
            if a.yes and a.snapshot:
                raise PolicyError("--yes reads the live state itself; --snapshot is for planning only")
            snap = _load_snapshot(a.snapshot) if a.snapshot else collect_live(policy["host"], alias, only=[a.vm])
            plan = plan_apply(policy, snap, a.vm, a.layers.split(",") if a.layers else None, allow_remove=a.allow_remove, max_changes=a.max_changes)
            _print_plan(plan)
            if plan["refusals"]:
                return 1
            if not plan["changes"] or not a.yes:
                print("nothing to apply" if not plan["changes"] else "plan only: nothing was changed (add --yes to apply it)")
                return 0
            script = build_remote_script(plan, hold=a.hold, simulate_failure=a.simulate_failure, ipsets=observe(snap)["ipsets"], guest_conf_path=a.guest_conf_path)
            proc = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", alias, "python3", "-"], input=script, capture_output=True, text=True)
            for line in proc.stdout.splitlines():
                try:
                    ev = json.loads(line)
                    print(f"  [{ev.get('event')}] " + ", ".join(f"{k}={v}" for k, v in ev.items() if k not in ("ts", "vm", "event")))
                except ValueError:
                    print("  " + line)
            if proc.stderr.strip():
                print("  stderr: " + proc.stderr.strip()[-300:], file=sys.stderr)
            return {0: 0, 5: 1, 6: 5, 7: 4}.get(proc.returncode, 3)
        if a.cmd == "why":
            policy = load_policy(_policy_path(a.policy))
            snap = None
            if a.snapshot:
                snap = _load_snapshot(a.snapshot)
            elif a.live:
                snap = collect_live(policy["host"], a.ssh or policy.get("collect", {}).get("ssh") or f"hv-{policy['host']}")
            res = why(policy, a.vm, a.src, a.proto, a.port, snap)
            print(f"VM {a.vm}: {res['flow']}")
            for layer in LAYERS:
                d = res["layers"][layer]
                print(f"  {layer:12} policy: {d['policy']}" + (f" | live: {d['live']}" if "live" in d else ""))
            v = res["verdict"]
            print(f"  {'verdict':12} policy: {v['policy']}" + (f" | live: {v['live']}" if "live" in v else ""))
            return 0
    except PolicyError as exc:
        print(f"netpolicy: {exc}", file=sys.stderr)
        return 3
    return 0


def _write_textfile(directory: str, text: str, host: str) -> None:
    """One file per hypervisor (netpolicy_<host>.prom), replaced atomically and readable by the node exporter."""
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_]", "_", host)
    tmp = d / f".netpolicy_{safe}.prom.tmp"
    tmp.write_text(text)
    tmp.chmod(0o644)
    tmp.replace(d / f"netpolicy_{safe}.prom")


if __name__ == "__main__":
    sys.exit(main())
