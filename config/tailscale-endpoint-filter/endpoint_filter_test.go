package netmon

import (
    "net"
    "net/netip"
    "testing"

    "tailscale.com/envknob"
    "tailscale.com/tstest"
)

func TestEndpointFilterPreservesLANAndExcludesContainerBridges(t *testing.T) {
    envknob.SetenvForTest(t, "TS_AVOID_INTERFACES", "br-*,docker*,veth*")
    envknob.SetenvForTest(t, "TS_ONLY_INTERFACES", "")
    envknob.SetenvForTest(t, "TS_AVOID_PREFIX", "")
    addr := func(s string) net.Addr { ip, n, err := net.ParseCIDR(s); if err != nil { t.Fatal(err) }; n.IP = ip; return n }
    ifaces := []Interface{
        {Interface: &net.Interface{Name: "ens18", Flags: net.FlagUp}, AltAddrs: []net.Addr{addr("10.88.0.2/24")}},
        {Interface: &net.Interface{Name: "br-deadbeef", Flags: net.FlagUp}, AltAddrs: []net.Addr{addr("172.18.0.1/24")}},
        {Interface: &net.Interface{Name: "docker0", Flags: net.FlagUp}, AltAddrs: []net.Addr{addr("172.19.0.1/24")}},
    }
    tstest.Replace(t, &altNetInterfaces, func() ([]Interface, error) { return ifaces, nil })
    regular, _, err := LocalAddresses()
    if err != nil { t.Fatal(err) }
    want := netip.MustParseAddr("10.88.0.2")
    if len(regular) != 1 || regular[0] != want { t.Fatalf("endpoints = %v; want only %v", regular, want) }
}

func TestEndpointFilterNoConfigurationPreservesAllInterfaces(t *testing.T) {
    envknob.SetenvForTest(t, "TS_AVOID_INTERFACES", "")
    envknob.SetenvForTest(t, "TS_ONLY_INTERFACES", "")
    envknob.SetenvForTest(t, "TS_AVOID_PREFIX", "")
    if !isAllowedInterface(&net.Interface{Name: "br-example"}) { t.Fatal("default unexpectedly excludes interface") }
}
