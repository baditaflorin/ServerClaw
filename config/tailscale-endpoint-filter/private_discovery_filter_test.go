// Copyright (c) Tailscale Inc & contributors
// SPDX-License-Identifier: BSD-3-Clause

package magicsock

import (
	"net"
	"net/netip"
	"testing"

	"tailscale.com/net/netmon"
)

func TestSuppressOffLinkPrivateDisco(t *testing.T) {
	state := &netmon.State{
		Interface: map[string]netmon.Interface{
			"eth0":       {Interface: &net.Interface{Name: "eth0", Flags: net.FlagUp}},
			"vmbr1":      {Interface: &net.Interface{Name: "vmbr1", Flags: net.FlagUp}},
			"br-docker":  {Interface: &net.Interface{Name: "br-docker", Flags: net.FlagUp}},
			"down0":      {Interface: &net.Interface{Name: "down0"}},
			"tailscale0": {Interface: &net.Interface{Name: "tailscale0", Flags: net.FlagUp}},
		},
		InterfaceIPs: map[string][]netip.Prefix{
			"eth0":       {netip.MustParsePrefix("10.41.10.40/24"), netip.MustParsePrefix("169.254.1.2/16")},
			"vmbr1":      {netip.MustParsePrefix("10.42.10.1/24")},
			"br-docker":  {netip.MustParsePrefix("10.43.0.1/16")},
			"down0":      {netip.MustParsePrefix("192.168.1.1/24")},
			"tailscale0": {netip.MustParsePrefix("100.80.0.1/10")},
		},
	}
	for _, tt := range []struct {
		name  string
		addr  string
		state *netmon.State
		want  bool
	}{
		{"same LAN", "10.41.10.20", state, false},
		{"local hypervisor bridge", "10.42.10.107", state, false},
		{"other site", "10.44.10.60", state, true},
		{"container bridge", "10.43.1.1", state, true},
		{"down interface", "192.168.1.2", state, true},
		{"tailnet interface", "100.80.0.2", state, true},
		{"on-link local address", "169.254.1.3", state, false},
		{"off-link local address", "169.254.1.3", nil, true},
		{"public endpoint", "8.8.8.8", nil, false},
		{"DERP sentinel", "127.3.3.40", nil, false},
		{"IPv6 unchanged", "fd00::1", nil, false},
	} {
		t.Run(tt.name, func(t *testing.T) {
			if got := suppressOffLinkPrivateDisco(netip.MustParseAddr(tt.addr), tt.state, "br-*,docker*,veth*"); got != tt.want {
				t.Fatalf("suppressOffLinkPrivateDisco(%s) = %v; want %v", tt.addr, got, tt.want)
			}
		})
	}
	if suppressOffLinkPrivateDisco(netip.MustParseAddr("10.43.1.1"), state, "") {
		t.Fatal("an allowed on-link interface should permit private discovery")
	}
	state.InterfaceIPs["eth0"] = []netip.Prefix{netip.MustParsePrefix("0.0.0.0/0")}
	if !suppressOffLinkPrivateDisco(netip.MustParseAddr("10.44.10.60"), state, "br-*,docker*,veth*") {
		t.Fatal("a default-route prefix must not authorize private discovery")
	}
}

func TestOffLinkDiscoveryStopsBeforeSocketWrite(t *testing.T) {
	old, oldExcluded := privateDiscoOnLinkOnly, privateDiscoExcludedInterfaces
	privateDiscoOnLinkOnly = func() bool { return true }
	privateDiscoExcludedInterfaces = func() string { return "br-*,docker*,veth*" }
	defer func() { privateDiscoOnLinkOnly, privateDiscoExcludedInterfaces = old, oldExcluded }()

	c := &Conn{netMon: netmon.NewStatic()}
	var target netip.Addr
	for _, candidate := range []string{"10.255.255.254", "172.31.255.254", "192.168.255.254", "100.127.255.254"} {
		addr := netip.MustParseAddr(candidate)
		if suppressOffLinkPrivateDisco(addr, c.netMon.InterfaceState(), "br-*,docker*,veth*") {
			target = addr
			break
		}
	}
	if !target.IsValid() {
		t.Skip("all test destinations happen to be on directly connected subnets")
	}
	sent, err := c.sendUDP(netip.AddrPortFrom(target, 41641), []byte("probe"), true, false)
	if sent || err != nil {
		t.Fatalf("off-link discovery send = (%v, %v), want (false, nil)", sent, err)
	}
}
