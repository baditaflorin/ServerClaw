# ADR 0188 PostgreSQL Rehearsal Evidence

Observed on 2026-03-27 from workstream `ws-0188-live-apply`.

## Proxmox host inventory

```text
$ ssh ops@100.64.0.1 'sudo qm list'
      VMID NAME                 STATUS
       150 postgres-lv3         running
```

VM `151` is absent from the live Proxmox inventory.

## Guest runtime state

```text
$ ssh ops@100.64.0.1 'sudo qm guest exec 150 -- bash -lc "hostname; systemctl is-active patroni keepalived; ls -l /etc/patroni"'
postgres-lv3
inactive
inactive
total 12
-rw-r--r-- 1 root root 5388 Oct 20 12:55 config.yml.in
-rw-r--r-- 1 root root  101 Jun  3  2020 dcs.yml
```

`postgresql` itself is still serving on the primary guest:

```text
$ ssh ops@100.64.0.1 'sudo qm guest exec 150 -- bash -lc "systemctl is-active postgresql; ss -ltnp | grep 5432; pg_isready -h 127.0.0.1 -p 5432"'
active
LISTEN 0      200      10.10.10.50:5432
127.0.0.1:5432 - accepting connections
```

## VIP reachability

```text
$ ssh ops@100.64.0.1 'timeout 5 bash -lc "echo > /dev/tcp/10.10.10.55/5432" && echo vip-open || echo vip-closed'
vip-closed

$ ssh ops@100.64.0.1 'timeout 5 bash -lc "echo > /dev/tcp/10.10.10.50/5432" && echo primary-open || echo primary-closed'
primary-open
```

## Result

The planned `R2` rehearsal could not proceed because the expected standby guest and HA control-plane path are missing. Under ADR 0188 this means the declared `R2` design remains, but the implemented claim must fall back until a repaired standby path completes a fresh passing rehearsal.
