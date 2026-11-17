#!/usr/bin/env python3
"""Export CT zvol allocation from the owning hypervisor to node_exporter."""

import os
import subprocess
import tempfile
import time
from pathlib import Path

VOLUME = "rpool/data/vm-660-disk-1"
OUTPUT = Path("/var/lib/prometheus/node-exporter/textfile/ct_names_zvol.prom")


def collect():
    config = subprocess.check_output(["qm", "config", "660"], text=True, timeout=10)
    lines = [line for line in config.splitlines() if line.startswith("scsi1:")]
    if len(lines) != 1 or "local-zfs:vm-660-disk-1," not in lines[0] or "serial=CTNAMES0" not in lines[0]:
        raise ValueError("CT zvol ownership does not match VM configuration")
    raw = subprocess.check_output(["zfs", "list", "-Hp", "-o", "used,volsize", VOLUME], text=True, timeout=20).split()
    if len(raw) != 2:
        raise ValueError("unexpected zfs output")
    used, size = map(int, raw)
    if used < 0 or size <= 0:
        raise ValueError("invalid zvol usage")
    return used, size


def main():
    used, size = collect()
    text = (
        f"ct_names_zvol_allocated_bytes {used}\n"
        f"ct_names_zvol_size_bytes {size}\n"
        f"ct_names_zvol_sample_timestamp_seconds {int(time.time())}\n"
    )
    fd, name = tempfile.mkstemp(prefix=".ct_names_zvol.", dir=OUTPUT.parent)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(name, 0o644)
        os.replace(name, OUTPUT)
    finally:
        if os.path.exists(name):
            os.unlink(name)


if __name__ == "__main__":
    main()
