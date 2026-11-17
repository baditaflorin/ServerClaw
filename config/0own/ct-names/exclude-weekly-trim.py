#!/usr/bin/env python3
"""Exclude the mounted CT volume from fstrim --listed-in; no remount or trim."""
import argparse
import os
import re
import shutil
import stat
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

MOUNT = "/srv/ct-names"
OPTION = "X-fstrim.notrim"


def updated_fstab(text, mount, uuid):
    lines = text.splitlines(keepends=True)
    matches = []
    for i, line in enumerate(lines):
        match = re.match(r"^(\s*)(\S+)(\s+)(\S+)(\s+)(\S+)(\s+)(\S+)([^\n]*)(\n?)$", line)
        if match and not line.lstrip().startswith("#") and match.group(4) == mount:
            matches.append((i, match))
    if len(matches) != 1:
        raise ValueError(f"expected exactly one fstab entry for {mount}, found {len(matches)}")
    i, m = matches[0]
    if m.group(2) != f"UUID={uuid}" or m.group(6) != "ext4":
        raise ValueError("fstab source or filesystem does not match the mounted CT disk")
    opts = m.group(8).split(",")
    if OPTION not in opts:
        opts.append(OPTION)
    lines[i] = "".join(m.group(j) for j in range(1, 8)) + ",".join(opts) + m.group(9) + m.group(10)
    return "".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    source = subprocess.check_output(["findmnt", "-n", "-o", "SOURCE", "--mountpoint", MOUNT], text=True).strip()
    label = subprocess.check_output(["blkid", "-s", "LABEL", "-o", "value", source], text=True).strip()
    uuid = subprocess.check_output(["blkid", "-s", "UUID", "-o", "value", source], text=True).strip()
    if label != "ctnames" or not uuid:
        raise ValueError("mounted disk is not the expected ctnames filesystem")
    path = Path("/etc/fstab")
    if path.is_symlink() or not path.is_file():
        raise ValueError("fstab must be a regular file")
    original = path.read_text()
    updated = updated_fstab(original, MOUNT, uuid)
    if original == updated:
        print("CT disk already excluded from scheduled fstrim")
        return
    if not args.apply:
        print("Plan: add X-fstrim.notrim to the CT disk fstab entry; other mounts unchanged")
        return
    backupdir = Path("/root/ct-names-backups")
    backupdir.mkdir(mode=0o700, exist_ok=True)
    backup = backupdir / ("fstab.pre-trim-policy-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    shutil.copy2(path, backup)
    info = path.stat()
    fd, name = tempfile.mkstemp(prefix=".fstab-ct-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(updated)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(name, stat.S_IMODE(info.st_mode))
        os.chown(name, info.st_uid, info.st_gid)
        subprocess.run(["findmnt", "--verify", "--tab-file", name], check=True, stdout=subprocess.DEVNULL)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    print(f"Applied CT trim exclusion; backup: {backup}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"REFUSING: {exc}")
