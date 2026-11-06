# A host that logs in but hangs: diagnosing a wedged VM without hanging yourself

## Purpose

Find out what a wedged Linux host (usually the Docker host, `ubuntu-24-04` / `dockerhost`, VM 100 on 0docker) is blocked on, and unblock it, using only
commands that cannot join the pile of stuck processes. Written after the 2026-10-19 13:03-13:34Z wedge (six public services down, `FleetEdgeManyDown`), where
`ps`, `docker ps`, `systemctl`, `tailscale status` and `qm guest exec` all hung and made it worse.

## Recognise it

- `ssh` still logs in, but ordinary commands take minutes or never return; the load average is far above what the CPU shows (CPU mostly idle).
- The host's node_exporter target is `up == 0` while the VM is running (its scrape stalls, most likely on the filesystem collector's `statfs` of the dead mount).
- `FleetEdgeManyDown` / many `FleetServiceEdgeDown` from both vantages at once, and `NodeExporterMissing` 15 to 20 minutes later.
- `/proc/pressure/memory` `some` near 100 % with idle CPU, no swap traffic and an idle disk: the stall is something else than memory.

## What not to run

`ps -eo ...args` (reading `/proc/PID/cmdline` of a stuck process blocks in `__access_remote_vm`), `docker ps` and `docker info`, `systemctl is-active docker`,
`tailscale status` / `tailscale ping`, `df` without `-l`, `qm guest exec` (the guest agent blocks on the dead mount's `statfs`), `lsof`. Each one that hangs adds a
stuck process. Use a short script on stdin over `ssh` (the LAN path through the bastion, not the tailnet: a tailscaled restart would cut a tailnet session).

## Safe reads

`sudo -n python3 -` over ssh, reading only `/proc/<pid>/stat`, `/proc/<pid>/statm`, `/proc/<pid>/task/*/stat` and `.../wchan`, `/proc/pressure/*`, `/proc/meminfo`,
`/proc/vmstat` (twice, a few seconds apart), `/proc/diskstats`, `/proc/loadavg`, cgroup files (`memory.current`, `memory.pressure`, `cpu.stat`) and `dmesg -T`:

```python
import os, collections
def rd(p):
    try: return open(p).read()
    except Exception: return ''
c = collections.Counter()
for pid in os.listdir('/proc'):
    if not pid.isdigit(): continue
    comm = rd(f'/proc/{pid}/comm').strip()
    try: tasks = os.listdir(f'/proc/{pid}/task')
    except Exception: continue
    for t in tasks:
        st = rd(f'/proc/{pid}/task/{t}/stat')
        if st and st[st.rindex(')') + 2] == 'D':          # uninterruptible THREADS, not just processes
            c[(comm[:20], rd(f'/proc/{pid}/task/{t}/wchan').strip())] += 1
for (comm, wchan), n in c.most_common(14): print(n, comm, wchan)
```

Container names come from `/var/lib/docker/containers/<id>/config.v2.json` field `Name` only (the file holds the container's environment: never print it).

## Reading the wait channels

| wchan | Means | Then |
|---|---|---|
| `wait_on_commit` | waiting for an NFS COMMIT to finish | a hung NFS mount: `grep ' nfs' /proc/mounts`, `dmesg -T \| grep 'nfs:'`, `ss -tn state syn-sent` |
| `rpc_wait_bit_killable` (kernel thread `<server>-manager`) | the NFSv4 state manager cannot reach the server | the same; the server may be fine and the path broken (`tcpdump` on the server) |
| `lock_mm_and_find_vma`, `vma_expand`, `vma_merge` | page faults and mmap calls waiting for an mmap lock that another thread of the same process holds while it waits on something | find that thread's wchan: it is the root |
| `__access_remote_vm` | something reading another process's memory or cmdline (`ps`, a debugger) | stop running that |
| `folio_wait_bit_common`, `__wait_on_buffer`, `jbd2_log_wait_commit`, `wb_wait_for_completion` | ordinary disk waits | look at `/proc/pressure/io` and the hypervisor (a running vzdump) |

All of these waits are killable (SIGKILL ends them).

## Unblock

1. The process that carries the network path of the dead mount (on the Docker host: `tailscaled`) is the usual root: `sudo systemctl restart tailscaled` (it returned the
   VM to normal within a few minutes on 2026-10-19: stuck threads 74 to 7, memory pressure 98 % to 10 %; `umount -f -l` of the NFS mount alone did not release the waiters).
2. NFS mounts on a host that runs the fleet's control plane must be `soft`, never `hard`: `fleet-backup_backup-destination` is `soft,timeo=200,retrans=3` since
   2026-10-19 (a dead server gives EIO after about 140 s instead of blocking everything). `docker volume` options are immutable: recreate the volume.
3. Do not reboot the VM before reading the table above: a reboot loses the evidence and the hung mount comes back at boot.

## After the unblock

- Public edge: run the edge probe on both vantages (`systemctl start fleet-edge-probe.service` on CT108 and on the monitoring VM) and wait for `fleet_edge_probe_hard_fail_total` 0.
- Published ports without a listener (a Docker userland proxy that exited): compare `docker ps` published ports with `ss -tln`; one was lost (`go-apikey-service` :18021, containers
  reached the keystore as `host.docker.internal:18021` and got "connection refused" while outside callers, which go through iptables DNAT, did not notice). Fix by restarting
  that container (`docker restart`), not by hand-starting a `docker-proxy`; a `docker-proxy` started by hand (even socket-activated) exits at once, and a `systemd-socket-proxyd` stand-in
  works but would make the next container recreate fail with the port in use.
- The keystore: `/health` on `127.0.0.1:18021`, `keystore_mesh_isolated` 0, and a vault read (the tailnet reconciler on CT108 logs `decision in_sync`).
- Backups that ran during the wedge fail with an errno on `sync` and retry at the next cycle (`go-fleet-backup`: every 6 h at xx:59:50Z).

## Related

`docs/runbooks/fleet-observability.md` (alerts), `docs/runbooks/docker-runtime-disk-pressure.md` (a different way a Docker host stops).
