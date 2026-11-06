# infer runtime VM: the host's own name in /etc/hosts

2026-10-18. On `infer-runtime` (VM, 10.70.10.30) a trivial `sudo -n true` took 10-22 s of **system** CPU time, so every command the fleet-runner runs
there through `sudo` was slow, and under concurrency (several deploys at once) the VM sat at 80% system CPU. A pool deploy to the VM took 6-13 minutes
instead of about 3; the rollout of go-common v0.103.0 slowed to a crawl at five deploys in parallel.

## Cause

`/etc/hosts` had no entry for the machine's own name (`infer-runtime.example.org`). Name resolution goes `files myhostname resolve dns`: the miss in `files`
sent the lookup to `nss-myhostname`, which answers for the own name with the local addresses and enumerates the interfaces to do it. The VM has about 460
interfaces (364 of them `veth` for the ~270 containers), and that enumeration takes 16-22 s. `sudo` resolves the local host name on every start.
(`getent hosts <own name>` looked fast only because it asks a different NSS entry point; Python's `socket.getaddrinfo(socket.gethostname(), None)` took
16.5 s with `AI_ADDRCONFIG` or without.) The kernel stack of a slow `sudo` was `rtnl_dumpit <- netlink_dump <- netlink_recvmsg`.
`Set probe_interfaces false` in `/etc/sudo.conf` did not help (tried, reverted); neither did the open-files limit.

## Fix

One line, `127.0.1.1 infer-runtime.example.org infer-runtime` (the Debian default shape), so `files` answers first. Measured on the VM after the change:
`sudo -n true` 0.009 s (was 10-22 s), `getaddrinfo(own name)` 0.02 s (was 17 s). The other runtime hosts (dockerhost, 0mcp runtime general, 0own staging runtime)
answer `sudo` in 0.008-0.04 s: they already resolve their own name.

```sh
scp config/0infer/runtime-own-hostname/install-vm.sh 0infer_runtime:/tmp/ && ssh 0infer_runtime 'sudo bash /tmp/install-vm.sh [--undo]'
```

The script is idempotent, backs `/etc/hosts` up first (`/etc/hosts.bak-ownname-*`) and restarts nothing. cloud-init does not manage `/etc/hosts` here
(`manage_etc_hosts` is unset), so the line survives reboots; a rebuilt VM needs the script again. Check a new runtime VM with
`time sudo -n true` right after provisioning: more than a second means the same thing.
