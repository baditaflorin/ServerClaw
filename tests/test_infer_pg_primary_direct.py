"""VM701 (infer-pg-primary) direct tailnet path and the prepared client routes.

The UDP port must agree in four places (the VM's tailscaled port, the hypervisor DNAT, the SNAT that keeps the source port, the forward accept), the nft must stay as
narrow as it was reviewed, and the tailnet grants for the three database clients must stay in step with the SPIRE relay. Editing one place without the others
silently gives back the DERP relay (22 ms per query) or opens more than intended.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import tailscale_policy_sync as tps  # noqa: E402

D = REPO / "config/0infer/pg-primary-tailscale-direct"
NFT = (D / "infer-pg-primary-tailscale-direct.nft").read_text()
POLICY = tps.parse_hujson((REPO / "config/tailscale/policy.hujson").read_text())
VM, PORT, VM_TS = "10.70.10.10", 41643, "100.64.0.22"


def rules(text):
    return [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]


def test_direct_path_port_is_the_same_everywhere():
    assert f'udp dport {PORT} dnat to {VM}:{PORT}' in NFT
    assert f'ip saddr {VM} udp sport {PORT} oifname "eno1" snat to 203.0.113.20:{PORT}' in NFT   # the VM's source port is kept
    assert f"udp dport {PORT} accept" in (D / "install-host.sh").read_text()
    assert f"want={PORT}" in (D / "install-vm.sh").read_text()
    assert PORT not in (41641, 41642)                                                             # 41641 is the hypervisor's tailscaled, 41642 infer-runtime's


def test_direct_path_nft_is_one_udp_port_for_one_vm():
    body = "\n".join(r for r in rules(NFT) if not r.startswith("type "))
    assert len([r for r in rules(NFT) if "dnat to" in r]) == 1
    for forbidden in ("tcp", "masquerade", "accept", "drop", "daddr 0.0.0.0", "/16", "/8", "dport {"):
        assert forbidden not in body, forbidden
    assert 'iifname "eno1" ip daddr 203.0.113.20' in NFT                                          # only what arrives from the Internet at the hypervisor address


def test_the_spire_relay_left_with_pve01():
    """The SPIRE relay ran on the 0database hypervisor (pve01), cancelled 2026-10-22; its config left the repository with it."""
    assert not (REPO / "config/0database/spire-vm701-relay").exists()


def _grant(src):
    gs = [g for g in POLICY["grants"] if g.get("src") == [src] and g.get("dst") == [f"{VM_TS}/32"]]
    assert len(gs) == 1, src
    assert gs[0]["ip"] == ["tcp:5432"]                                                            # PostgreSQL only
    return gs[0]


def test_grants_for_the_three_clients_and_their_policy_tests():
    for src in ("100.100.84.8/32", "100.64.0.7/32", "100.64.0.5/32"):  # docker-prod, dockerhost, 0docker hypervisor (Outline + builder relays)
        _grant(src)
    accept = {(t["src"], a) for t in POLICY["tests"] for a in t.get("accept", [])}
    deny = {(t["src"], d) for t in POLICY["tests"] for d in t.get("deny", [])}
    for src in ("100.100.84.8", "100.64.0.7", "100.64.0.5"):
        assert (src, f"{VM_TS}:5432") in accept
    for src in ("100.64.0.7", "100.64.0.5"):
        assert (src, f"{VM_TS}:22") in deny                                                        # the grant does not open ssh


def test_the_retired_pve01_clients_have_no_path_to_vm701():
    """pve01 (0database.com) was retired on 2026-10-21: its hypervisor (the SPIRE relay, 100.64.0.9) and VM100 (the hot standby,
    100.64.0.10) left the tailnet. A Tailscale address can be handed to a new node, so no grant or test may still name them."""
    for g in POLICY["grants"]:
        if f"{VM_TS}/32" in g.get("dst", []):
            assert not {"100.64.0.9/32", "100.64.0.10/32"} & set(g.get("src", [])), g
    assert not [t for t in POLICY["tests"] if t["src"] in ("100.64.0.9", "100.64.0.10")]


def test_installers_are_valid_shell_and_undoable():
    for f in (D / "install-host.sh", D / "install-vm.sh"):
        subprocess.run(["bash", "-n", str(f)], check=True)
        assert "--undo" in f.read_text(), f
