// Copyright (c) Tailscale Inc & contributors
// SPDX-License-Identifier: BSD-3-Clause

package magicsock

import (
	"net/netip"
	"path"
	"strings"

	"tailscale.com/envknob"
	"tailscale.com/net/netmon"
	"tailscale.com/util/clientmetric"
)

// Opt-in: prevent off-link private IPv4 discovery attempts from reaching a
// public default route. Public endpoints and DERP remain available.
var privateDiscoOnLinkOnly = envknob.RegisterBool("TS_DISCO_PRIVATE_ONLINK_ONLY")
var privateDiscoExcludedInterfaces = envknob.RegisterString("TS_AVOID_INTERFACES")
var metricPrivateDiscoOffLinkSuppressed = clientmetric.NewCounter("magicsock_private_disco_offlink_suppressed")

var privateDiscoScopes = [...]netip.Prefix{
	netip.MustParsePrefix("10.0.0.0/8"),
	netip.MustParsePrefix("172.16.0.0/12"),
	netip.MustParsePrefix("192.168.0.0/16"),
	netip.MustParsePrefix("100.64.0.0/10"),
	netip.MustParsePrefix("169.254.0.0/16"),
}

// suppressOffLinkPrivateDisco permits private probes only on a directly
// connected, active non-container interface. Routed private subnets fall
// back to public or relay paths instead of taking the default uplink.
// A missing interface snapshot fails closed for private destinations.
func suppressOffLinkPrivateDisco(addr netip.Addr, state *netmon.State, excluded string) bool {
	addr = addr.Unmap()
	if !addr.Is4() {
		return false
	}
	var scope netip.Prefix
	for _, candidate := range privateDiscoScopes {
		if candidate.Contains(addr) {
			scope = candidate
			break
		}
	}
	if !scope.IsValid() {
		return false
	}
	if state == nil {
		return true
	}
	for name, iface := range state.Interface {
		if !iface.IsUp() || iface.IsLoopback() || strings.HasPrefix(name, "tailscale") || excludedDiscoInterface(name, excluded) {
			continue
		}
		for _, prefix := range state.InterfaceIPs[name] {
			prefix = prefix.Masked()
			// Avoid treating an overly broad or unrelated interface prefix
			// as authorization for an entire private address block.
			if prefix.IsValid() && prefix.Addr().Is4() && prefix.Bits() >= scope.Bits() && scope.Contains(prefix.Addr()) && prefix.Contains(addr) {
				return false
			}
		}
	}
	return true
}

// Use the same configured exclusions as endpoint advertisement.
func excludedDiscoInterface(name, patterns string) bool {
	for _, pattern := range strings.Split(patterns, ",") {
		pattern = strings.TrimSpace(pattern)
		if pattern != "" {
			if matched, err := path.Match(pattern, name); err == nil && matched {
				return true
			}
		}
	}
	return false
}
