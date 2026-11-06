#!/usr/bin/env python3
"""File-level backup of the state of the Docker host (VM 100, ubuntuvm1) to own-pbs, run from inside the guest.

Why this exists: the VM-level backup of VM 100 (vzdump snapshot) has been paused since 2026-10-19 08:25Z: three attempts overloaded the
host (copy-before-write stalls, then a run-queue explosion, then the fleecing image filled the hypervisor's root filesystem). This job reads
the guest's own files at idle priority instead, so nothing runs on the hypervisor and there is no copy-before-write.

What one run does (see README.md next to this file for the full picture, the restore recipes and the exclusions):
  1. preflight: client present, token file private, load low enough to start, PBS reachable with the token;
  2. stages what a plain file copy would get wrong: a pg_dumpall of every running Postgres container, an online copy (sqlite3 backup API) of every
     SQLite database that is open right now, and a small inventory of the host (docker ps, volumes, packages, enabled units). The SQLite copies are
     made one at a time, largest first; a big one is compressed with zstd right after its copy (and proven to decompress to the same bytes), then the raw
     copy is deleted and the blocks it held are trimmed, so the staging directory never holds more than one raw copy (see "Staging peak" in the README);
  3. runs `proxmox-backup-client backup` once, so one snapshot holds the archives etc / opt / home / srv / root / volumes / staging, with the data
     directories of the dumped Postgres containers, the live SQLite files (their staged copies are in `staging`), rebuildable indexes and caches left out;
  4. removes the staging directory, writes a textfile metric for node_exporter and exits non-zero when anything went wrong.

The token secret is read from a root-only file and handed to the client in the environment (PBS_PASSWORD), never on a command line and never logged.
Python 3.9+ standard library only. Installed as /usr/local/sbin/dockerhost-state-backup.
"""
from __future__ import annotations

import argparse
import fcntl
import fnmatch
import gzip
import hashlib
import json
import os
import queue
import re
import shutil
import sqlite3
import struct
import subprocess
import sys
import threading
import time

CONFIG_PATH = "/etc/dockerhost-state-backup/config.json"
CHECK_MAX_BYTES_DEFAULT = 512 << 20  # larger staged SQLite copies are not quick_checked (see stage())
COMPRESS_MIN_BYTES_DEFAULT = 64 << 20  # staged SQLite copies of this size or more are compressed (0 turns it off)
COMPRESS_TIMEOUT_DEFAULT = 3600
TRIM_WAIT_DEFAULT = 300
STAGED_SUFFIX = ".zst"
ZSTD_LEVEL = 1  # measured on samples of the real databases: level 3 is 7 % smaller for twice the CPU, gzip -1 is 10 % bigger and no faster
IO_BLOCK = 4 << 20
FS_IOC_FIEMAP, FITRIM, FIEMAP_EXTENT_LAST = 0xC020660B, 0xC0185879, 0x1  # linux/fiemap.h, linux/fs.h
LOCK_PATH = "/run/dockerhost-state-backup.lock"
SQLITE_MAGIC = b"SQLite format 3\x00"
POSTGRES_DATA_DEST = "/var/lib/postgresql/data"
REBUILDABLE_DEST = ("/usr/share/elasticsearch/data",)  # search indexes: rebuilt from their source database, a live file copy of them is not usable
SQLITE_SUFFIXES = (".db", ".sqlite", ".sqlite3")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+@[a-z]+![A-Za-z0-9_.-]+@[A-Za-z0-9_.:-]+:[A-Za-z0-9_.-]+$")  # user@realm!token@host:datastore
EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_BUSY, EXIT_SKIPPED = 0, 1, 2, 3, 4


class BackupError(Exception):
    pass


def log(msg: str) -> None:
    print(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + " " + msg, flush=True)


# ----------------------------------------------------------------------------- configuration


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    problems = config_problems(cfg)
    if problems:
        raise BackupError("config " + path + ": " + "; ".join(problems))
    return cfg


def config_problems(cfg: dict) -> list:
    out = []
    for key in ("repository", "fingerprint", "namespace", "backup_type", "backup_id", "secret_file", "staging_dir", "archives", "limits"):
        if key not in cfg:
            out.append("missing " + key)
    if out:
        return out
    if not REPO_RE.match(cfg["repository"]) or "@pbs!" not in cfg["repository"]:
        out.append("repository must be user@pbs!token@host:datastore (an API token, not a user password)")
    if not re.match(r"^([0-9A-Fa-f]{2}:){31}[0-9A-Fa-f]{2}$", cfg["fingerprint"]):
        out.append("fingerprint must be the 32 colon-separated bytes of the server certificate (public)")
    if cfg["backup_type"] != "host":
        out.append("backup_type must be host")
    if not re.match(r"^[A-Za-z0-9_.-]+$", cfg["backup_id"]) or not re.match(r"^[A-Za-z0-9_.-]+$", cfg["namespace"]):
        out.append("namespace and backup_id may only contain letters, digits, _ . -")
    staging = cfg["staging_dir"]
    if not (os.path.isabs(staging) and staging.startswith(("/var/backups/", "/var/tmp/")) and "dockerhost-state" in os.path.basename(staging.rstrip("/"))):
        out.append("staging_dir must be below /var/backups/ or /var/tmp/ and its name must contain dockerhost-state (it is deleted after each run)")
    arch = cfg["archives"]
    if not arch or not all(re.match(r"^[a-z][a-z0-9_-]*$", k) and isinstance(v, str) and os.path.isabs(v) for k, v in arch.items()):
        out.append("archives must map a short lower-case name to an absolute path")
    if "staging" in arch:
        out.append("the archive name staging is reserved")
    for name, pats in (cfg.get("exclude") or {}).items():
        if name not in arch:
            out.append("exclude names the unknown archive " + name)
        elif not all(isinstance(p, str) and p.startswith("/") for p in pats):
            out.append("exclude patterns of " + name + " must start with / (anchored at the archive root)")
    if not isinstance(cfg.get("raw_sqlite", []), list) or not all(isinstance(g, str) and g.startswith("/") for g in cfg.get("raw_sqlite", [])):
        out.append("raw_sqlite must be a list of absolute path patterns (fnmatch)")
    lim = cfg["limits"]
    for opt in ("check_timeout_s", "check_max_bytes", "compress_timeout_s", "trim_wait_s"):
        if opt in lim and (not isinstance(lim[opt], (int, float)) or lim[opt] <= 0):
            out.append("limits." + opt + " must be a positive number")
    if "compress_min_bytes" in lim and (not isinstance(lim["compress_min_bytes"], (int, float)) or lim["compress_min_bytes"] < 0):
        out.append("limits.compress_min_bytes must be a number of bytes, 0 or more (0 turns the compression off)")
    if not isinstance(cfg.get("trim_staging", True), bool):
        out.append("trim_staging must be true or false")
    elif not cfg.get("trim_staging", True) and lim.get("compress_min_bytes", COMPRESS_MIN_BYTES_DEFAULT) > 0:
        out.append("trim_staging false needs limits.compress_min_bytes 0: one copy at a time without the trim puts more on the hypervisor than staging them all at once (21.9 against 18.2 GiB on the bench)")
    for key in ("start_load5", "abort_load1", "start_wait_s", "deadline_s", "dump_timeout_s", "sqlite_timeout_s"):
        if not isinstance(lim.get(key), (int, float)) or lim[key] <= 0:
            out.append("limits." + key + " must be a positive number")
    return out


def read_secret(path: str) -> str:
    st = os.stat(path)
    if st.st_mode & 0o077:
        raise BackupError("token file " + path + " must not be readable by group or others (chmod 600)")
    if hasattr(os, "geteuid") and st.st_uid != os.geteuid():
        raise BackupError("token file " + path + " must be owned by the user running the backup")
    with open(path, encoding="utf-8") as fh:
        secret = fh.read().strip()
    if not secret:
        raise BackupError("token file " + path + " is empty")
    return secret


# ----------------------------------------------------------------------------- patterns


def escape_pattern(path: str) -> str:
    """A literal path as a pxar match pattern: backslash-escape the glob characters (patterns here always start with /, so no leading ! or #)."""
    return re.sub(r"([\\*?\[\]])", r"\\\1", path)


def relative_pattern(root: str, path: str):
    """Pattern (anchored at the archive root) for a path below root, or None when it is not below it."""
    root = root.rstrip("/") or "/"
    if root == "/":
        return escape_pattern(path) if path.startswith("/") and path != "/" else None
    if path == root or not path.startswith(root + "/"):
        return None
    return escape_pattern(path[len(root):])


def owning_archive(archives: dict, path: str):
    """The archive whose root is the longest prefix of path, with the pattern for it, or (None, None)."""
    best = None
    for name, root in archives.items():
        pat = relative_pattern(root, path)
        if pat is not None and (best is None or len(root) > len(archives[best])):
            best = name
    if best is None:
        return None, None
    return best, relative_pattern(archives[best], path)


def collisions(archives: dict, excludes: dict) -> list:
    """Every --exclude goes to every archive of the one client call. A pattern meant for one archive must not name an existing path in another one."""
    out = []
    for name, pats in excludes.items():
        for pat in pats:
            if re.search(r"(?<!\\)[*?\[]", pat):
                continue  # a glob: cannot be checked by name
            literal = re.sub(r"\\(.)", r"\1", pat)
            for other, root in archives.items():
                if other != name and os.path.lexists(os.path.join(root, literal.lstrip("/"))):
                    out.append("exclude " + pat + " of " + name + " also matches " + os.path.join(root, literal.lstrip("/")) + " in archive " + other)
    return out


# ----------------------------------------------------------------------------- docker


def run(cmd, **kw):
    kw.setdefault("capture_output", True)
    kw.setdefault("text", True)
    kw.setdefault("check", False)
    return subprocess.run(cmd, **kw)


def containers() -> list:
    """Running containers with their image and mounts (no environment: it holds secrets)."""
    ids = run(["docker", "ps", "-q"])
    if ids.returncode != 0:
        raise BackupError("docker ps failed: " + ids.stderr.strip()[:200])
    names = ids.stdout.split()
    if not names:
        return []
    fmt = '{"name":{{json .Name}},"image":{{json .Config.Image}},"mounts":{{json .Mounts}}}'
    res = run(["docker", "inspect", "--format", fmt] + names)
    if res.returncode != 0:
        raise BackupError("docker inspect failed: " + res.stderr.strip()[:200])
    out = []
    for line in res.stdout.splitlines():
        if line.strip():
            c = json.loads(line)
            c["name"] = c["name"].lstrip("/")
            out.append(c)
    return out


def classify(cs: list) -> dict:
    """Postgres containers (dumped, data dir left out), rebuildable index containers (data dir left out) and the raw-copied engines (named, so the plan shows them)."""
    pg, skipped, raw = [], [], []
    for c in cs:
        mounts = c.get("mounts") or []
        if any(m.get("Destination") == POSTGRES_DATA_DEST for m in mounts):
            pg.append(c)
        elif any(m.get("Destination") in REBUILDABLE_DEST for m in mounts):
            skipped.append(c)
        elif re.search(r"(^|/)(redis|clickhouse[^:]*|mysql|mariadb|mongo)(:|$|@)", c.get("image", "")):
            raw.append(c)
    return {"postgres": pg, "rebuildable": skipped, "raw_engines": raw}


def data_sources(c: dict, dests) -> list:
    return [m["Source"] for m in c.get("mounts") or [] if m.get("Destination") in dests and m.get("Source")]


def postgres_user(c: dict) -> str:
    res = run(["docker", "exec", c["name"], "printenv", "POSTGRES_USER"])
    user = res.stdout.strip() if res.returncode == 0 else ""
    return user or "postgres"


def dump_postgres(c: dict, dest_dir: str, timeout: float) -> str:
    """pg_dumpall of one container into dest_dir/<name>.sql.gz; returns the path or raises."""
    user = postgres_user(c)
    path = os.path.join(dest_dir, c["name"] + ".sql.gz")
    cmd = ["docker", "exec", c["name"], "pg_dumpall", "-U", user, "--clean", "--if-exists"]
    deadline = time.time() + timeout
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        with gzip.open(path, "wb", compresslevel=6) as gz:
            while True:
                if time.time() > deadline:
                    proc.kill()
                    raise BackupError("pg_dumpall of " + c["name"] + " took longer than " + str(int(timeout)) + " s")
                chunk = proc.stdout.read(1 << 20)
                if not chunk:
                    break
                gz.write(chunk)
        err = proc.stderr.read().decode("utf-8", "replace").strip()
        if proc.wait() != 0:
            raise BackupError("pg_dumpall of " + c["name"] + " failed: " + err[:200])
    finally:
        if proc.poll() is None:
            proc.kill()
    if os.path.getsize(path) < 100:
        raise BackupError("pg_dumpall of " + c["name"] + " produced only " + str(os.path.getsize(path)) + " bytes")
    return path


# ----------------------------------------------------------------------------- sqlite


def sqlite_candidates(roots, skip_prefixes) -> list:
    """(path, size, mtime) of every SQLite database file below roots, without following symlinks or leaving the starting filesystem."""
    found = []
    for root in roots:
        try:
            dev = os.stat(root).st_dev
        except OSError:
            continue
        stack = [root]
        while stack:
            d = stack.pop()
            if any(d == p or d.startswith(p.rstrip("/") + "/") for p in skip_prefixes):
                continue
            try:
                it = list(os.scandir(d))
            except OSError:
                continue
            for e in it:
                try:
                    if e.is_symlink():
                        continue
                    if e.is_dir(follow_symlinks=False):
                        if e.stat(follow_symlinks=False).st_dev == dev:
                            stack.append(e.path)
                    elif e.is_file(follow_symlinks=False) and e.name.endswith(SQLITE_SUFFIXES):
                        st = e.stat(follow_symlinks=False)
                        if st.st_size >= 4096 and read_magic(e.path) == SQLITE_MAGIC:
                            found.append((e.path, st.st_size, st.st_mtime))
                except OSError:
                    continue
    return sorted(found)


def read_magic(path: str) -> bytes:
    try:
        with open(path, "rb") as fh:
            return fh.read(16)
    except OSError:
        return b""


def journal_mode_wal(path: str) -> bool:
    try:
        with open(path, "rb") as fh:
            h = fh.read(20)
        return len(h) >= 20 and h[18] == 2 and h[19] == 2
    except OSError:
        return False


def is_live(path: str, mtime: float, now: float, quiet_s: float = 900.0) -> bool:
    """Open right now (a WAL database keeps its -shm while any connection is open), has a hot journal, or was written a moment ago."""
    if journal_mode_wal(path):
        return os.path.exists(path + "-shm") or (os.path.exists(path + "-wal") and os.path.getsize(path + "-wal") > 0) or now - mtime < quiet_s
    return os.path.exists(path + "-journal") or now - mtime < quiet_s


def sqlite_backup(src: str, dst: str, wal: bool) -> None:
    """Consistent online copy through the sqlite3 backup API. The source is opened read-only, so root never creates a -wal or -shm
    owned by root next to a database an unprivileged service writes."""
    uri = "file:" + src.replace("%", "%25").replace("?", "%3f").replace("#", "%23") + "?mode=ro"
    s = sqlite3.connect(uri, uri=True, timeout=30)
    d = sqlite3.connect(dst)
    try:
        if wal:
            s.backup(d)  # one step: a single read snapshot, writers carry on in the WAL
        else:
            s.backup(d, pages=512, sleep=0.05)  # rollback-journal database: short read locks, restarts when written meanwhile
        d.execute("PRAGMA journal_mode=DELETE")  # the staged copy stands alone: no -wal/-shm next to it, none to restore by mistake
    finally:
        d.close()
        s.close()
        for suffix in ("-wal", "-shm", "-journal"):  # sidecars of the COPY (never of the source) that SQLite leaves behind after the switch
            try:
                os.remove(dst + suffix)
            except OSError:
                pass


def check_copy(d, src: str) -> None:
    """quick_check of the staged copy. A database with a virtual table whose module this Python does not have (hermes' messages_fts_trigram on 2026-10-21)
    cannot be checked as a whole: the backup API copied its pages, so the copy is complete, and the check is skipped for it."""
    try:
        row = d.execute("PRAGMA quick_check(1)").fetchone()
    except sqlite3.DatabaseError as exc:
        if "vtable constructor failed" in str(exc):
            log("note: " + src + " has a virtual table this sqlite cannot open (" + str(exc)[:80] + "): copied, not checked")
            return
        raise
    if not row or row[0] != "ok":
        raise BackupError("quick_check of the copy of " + src + " says " + str(row))


def stage_sqlite_child(argv) -> int:
    """`dockerhost-state-backup _sqlite SRC DST WAL`: runs in a child process so a stuck lock can be killed by the parent's timeout."""
    src, dst, wal = argv[0], argv[1], argv[2] == "1"
    try:
        sqlite_backup(src, dst, wal)
        return 0
    except Exception as exc:  # noqa: BLE001 - reported to the parent
        print(str(exc)[:300], file=sys.stderr)
        return 1


def check_child(argv) -> int:
    """`dockerhost-state-backup _check DST SRC`: quick_check of a staged copy, in its own process with its own (advisory) timeout. 0 = ok or not checkable, 1 = the copy is damaged."""
    dst, src = argv[0], argv[1]
    try:
        if not os.path.isfile(dst):  # sqlite3.connect would silently create an empty database
            raise BackupError("no staged copy at " + dst)
        d = sqlite3.connect(dst)
        try:
            check_copy(d, src)
        finally:
            d.close()
            for suffix in ("-wal", "-shm", "-journal"):
                try:
                    os.remove(dst + suffix)
                except OSError:
                    pass
        return 0
    except Exception as exc:  # noqa: BLE001 - reported to the parent
        print(str(exc)[:300], file=sys.stderr)
        return 1


# ----------------------------------------------------------------------------- compression and trim


def zstd_binary():
    return shutil.which("zstd")


def compress_file(raw: str, out: str, level: int = ZSTD_LEVEL) -> dict:
    """raw -> out with zstd: one pass over the raw file that also hashes it, then a second pass that decompresses the result and compares the hash.
    The raw copy is only deleted by the caller once this returns, so a compressed copy that does not hold the same bytes is never the only one."""
    zstd = zstd_binary()
    if not zstd:
        raise BackupError("zstd is not installed")
    part = out + ".part"
    try:
        digest, total, broken = hashlib.sha256(), 0, False
        with open(raw, "rb") as src, open(part, "wb") as dst:
            os.fchmod(dst.fileno(), 0o600)
            proc = subprocess.Popen([zstd, "-%d" % level, "-T1", "-q", "-c"], stdin=subprocess.PIPE, stdout=dst)
            try:
                for block in iter(lambda: src.read(IO_BLOCK), b""):
                    digest.update(block)
                    total += len(block)
                    proc.stdin.write(block)
            except BrokenPipeError:  # zstd stopped early: its exit status says why
                broken = True
            finally:
                try:
                    proc.stdin.close()
                except OSError:
                    pass
                rc = proc.wait()
        if broken or rc != 0:
            raise BackupError("zstd exited with " + str(rc) + " while compressing")
        check, seen = hashlib.sha256(), 0
        proc = subprocess.Popen([zstd, "-d", "-q", "-c", part], stdout=subprocess.PIPE)
        try:
            for block in iter(lambda: proc.stdout.read(IO_BLOCK), b""):
                check.update(block)
                seen += len(block)
        finally:
            proc.stdout.close()
            rc = proc.wait()
        if rc != 0 or seen != total or check.digest() != digest.digest():
            raise BackupError("the compressed copy does not decompress to the same bytes (zstd exit " + str(rc) + ", " + str(seen) + " of " + str(total) + " bytes)")
        os.replace(part, out)
        return {"bytes": total, "sha256": digest.hexdigest(), "compressed": os.path.getsize(out)}
    except BaseException:
        try:
            os.remove(part)
        except OSError:
            pass
        raise


def compress_child(argv) -> int:
    """`dockerhost-state-backup _compress RAW OUT`: runs in a child process so the parent's timeout can kill it. Prints one JSON line when it worked."""
    try:
        print(json.dumps(compress_file(argv[0], argv[1])))
        return 0
    except Exception as exc:  # noqa: BLE001 - reported to the parent
        print(str(exc)[:300], file=sys.stderr)
        return 1


def file_extents(path: str) -> list:
    """(physical byte offset, length) of every allocated extent of a file, from FIEMAP; [] when the filesystem cannot say (nothing is trimmed then).
    Not asking for a sync: data that was never written back holds no blocks yet, and deleting it frees nothing on the disk."""
    out, start = [], 0
    try:
        with open(path, "rb") as fh:
            while True:
                count = 64
                buf = bytearray(32 + 56 * count)
                struct.pack_into("=QQLLLL", buf, 0, start, 0xFFFFFFFFFFFFFFFF, 0, 0, count, 0)
                fcntl.ioctl(fh.fileno(), FS_IOC_FIEMAP, buf, True)
                mapped = struct.unpack_from("=L", buf, 20)[0]
                if mapped == 0:
                    return out
                before, last = start, False
                for i in range(mapped):
                    logical, physical, length, _r1, _r2, flags = struct.unpack_from("=QQQQQL", buf, 32 + 56 * i)
                    if physical and not flags & 0x206:  # not UNKNOWN (0x2), DELALLOC (0x4) or INLINE (0x200): those hold no blocks of their own
                        out.append((physical, length))
                    start = logical + length
                    last = bool(flags & FIEMAP_EXTENT_LAST)
                if last or start <= before:  # the last extent, or an answer that does not move on: never loop
                    return out
    except (OSError, ValueError, struct.error):
        return []


def merge_ranges(extents: list, gap: int = 256 << 20) -> list:
    """Sorted (start, length) ranges, extents closer than gap bytes joined: one FITRIM call per cluster of blocks instead of one per extent."""
    out = []
    for start, length in sorted(extents):
        if out and start - (out[-1][0] + out[-1][1]) <= gap:
            out[-1] = (out[-1][0], max(out[-1][1], start + length - out[-1][0]))
        else:
            out.append((start, length))
    return out


def trim_ranges(directory: str, ranges: list) -> int:
    """FITRIM over each (start, length) of the filesystem that holds directory; returns the bytes the filesystem says it discarded. Only free blocks
    are ever discarded, so a range that also holds live data is safe."""
    done = 0
    fd = os.open(directory, os.O_RDONLY)
    try:
        for start, length in ranges:
            buf = bytearray(struct.pack("=QQQ", start, length, 0))
            fcntl.ioctl(fd, FITRIM, buf, True)
            done += struct.unpack("=QQQ", bytes(buf))[1]
    finally:
        os.close(fd)
    return done


def trim_selftest(directory: str, size: int = 32 << 20) -> str:
    """'' when giving the blocks of a deleted file back to the disk works on the filesystem of directory, else the reason.
    Writes and syncs size bytes, reads their extents, deletes the file, fsyncs the directory and trims the extents, the way a staged copy is released.
    Staging copies one at a time only helps the hypervisor when this works: measured on the bench, one at a time WITHOUT the trim put 21.9 GiB on the
    disk file against 18.2 GiB for the old script, because ext4 does not reuse the blocks of a file it has just freed."""
    path = os.path.join(directory, ".trim-selftest")
    try:
        block = os.urandom(1 << 20)
        with open(path, "wb") as fh:
            for _ in range(size >> 20):
                fh.write(block)
            fh.flush()
            os.fsync(fh.fileno())
        extents = file_extents(path)
        os.remove(path)
        if not extents:
            return "the filesystem reports no extents for a file it has just written (FIEMAP)"
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        done = trim_ranges(directory, merge_ranges(extents))
        if done < size // 2:
            return "trimming the %d MiB it had just freed discarded only %d MiB" % (size >> 20, done >> 20)
        return ""
    except OSError as exc:
        return type(exc).__name__ + ": " + str(exc)[:120]
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


class TrimWorker(threading.Thread):
    """Gives the blocks of deleted staging files back to the disk (FITRIM of exactly the ranges they held) while the next copy is being made.
    The guest disk is a qcow2 on the hypervisor's only filesystem: a block the guest freed stays allocated there until the guest trims it, and the
    guest's own fstrim.timer runs once an hour, so without this the freed copies would count at full size until then.
    ext4 only offers a freed block to FITRIM once the journal transaction of the delete has committed (a trim straight after the unlink returns
    almost nothing: 0 MiB of 183 MiB on the bench), so each job first fsyncs the directory the delete changed, which forces that commit."""

    def __init__(self, directory: str, enabled: bool = True):
        super().__init__(daemon=True)
        self.directory, self.enabled, self.trimmed = directory, enabled, 0
        self.jobs = queue.Queue()
        if enabled:
            self.start()

    def submit(self, extents: list, changed_dir: str = "") -> None:
        """extents: what the deleted file held (file_extents, taken before the delete); changed_dir: the directory the delete changed (call this after it)."""
        if self.enabled and extents:
            self.jobs.put((merge_ranges(extents), changed_dir))

    def run(self) -> None:
        while True:
            job = self.jobs.get()
            if job is None:
                return
            ranges, changed_dir = job
            began = time.time()
            try:
                if changed_dir:
                    fd = os.open(changed_dir, os.O_RDONLY)
                    try:
                        os.fsync(fd)
                    finally:
                        os.close(fd)
                done = trim_ranges(self.directory, ranges)
                self.trimmed += done
                log("trimmed %d MiB of freed staging blocks in %.0f s" % (done >> 20, time.time() - began))
            except Exception as exc:  # noqa: BLE001 - a trim is an optimisation: a failure is a note, and the worker carries on
                log("note: trimming freed staging blocks failed (%s): the guest's hourly fstrim returns them instead" % type(exc).__name__)

    def close(self, wait_s: float) -> None:
        if not self.enabled:
            return
        self.jobs.put(None)
        self.join(wait_s)
        if self.is_alive():
            log("note: the trim of freed staging blocks is still running after %d s: leaving it to finish" % wait_s)


def tree_extents(directory: str) -> list:
    out = []
    for base, _dirs, files in os.walk(directory):
        for f in files:
            out.extend(file_extents(os.path.join(base, f)))
    return out


def release(path: str, trimmer) -> None:
    """Delete a staged file and hand the blocks it held to the trim worker."""
    extents = file_extents(path) if trimmer is not None and trimmer.enabled else []
    os.remove(path)
    if trimmer is not None:
        trimmer.submit(extents, os.path.dirname(path))


# ----------------------------------------------------------------------------- inventory


INVENTORY = (
    ("docker-ps-a.txt", ["docker", "ps", "-a", "--format", "{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"]),
    ("docker-images.txt", ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}\t{{.ID}}\t{{.Size}}"]),
    ("docker-volumes.json", ["sh", "-c", "docker volume ls -q | xargs -r docker volume inspect"]),
    ("docker-networks.txt", ["docker", "network", "ls", "--format", "{{.Name}}\t{{.Driver}}\t{{.Scope}}"]),
    ("dpkg-selections.txt", ["dpkg", "--get-selections"]),
    ("systemd-enabled-units.txt", ["systemctl", "list-unit-files", "--state=enabled", "--no-pager", "--no-legend"]),
    ("crontab-root.txt", ["crontab", "-l"]),
    ("df.txt", ["df", "-hT"]),
    ("lsblk.json", ["lsblk", "-J", "-o", "NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT"]),
    ("ip-addr.txt", ["ip", "-br", "addr"]),
    ("uname.txt", ["uname", "-a"]),
    # what a rebuild needs and a file copy does not carry (added 2026-10-29)
    ("os-release.txt", ["cat", "/etc/os-release"]),
    ("docker-version.txt", ["sh", "-c", "docker version; docker compose version"]),
    ("docker-images-digests.txt", ["docker", "images", "--digests", "--format", "{{.Repository}}:{{.Tag}}\t{{.Digest}}\t{{.ID}}"]),
    ("docker-networks-inspect.json", ["sh", "-c", "docker network ls -q | xargs -r docker network inspect"]),
    ("docker-compose-ls.txt", ["docker", "compose", "ls", "-a"]),
    ("docker-noncompose-containers.json", ["sh", "-c", "docker ps -aq | xargs -r docker inspect --format '{{.Id}} {{index .Config.Labels \"com.docker.compose.project\"}}' | awk 'NF==1{print $1}' | xargs -r docker inspect"]),
    ("nft-ruleset.txt", ["nft", "list", "ruleset"]),
    ("iptables-save.txt", ["iptables-save"]),
    ("ip-route.txt", ["ip", "route"]),
    ("hostnamectl.txt", ["hostnamectl"]),
    ("tailscale-status.txt", ["tailscale", "status"]),
    ("systemd-timers.txt", ["systemctl", "list-timers", "--all", "--no-pager"]),
)


def stage_inventory(dest: str) -> None:
    os.makedirs(dest, exist_ok=True)
    for name, cmd in INVENTORY:
        try:
            res = run(cmd, timeout=120)
            text = res.stdout if res.returncode == 0 else "# command failed (" + str(res.returncode) + "): " + res.stderr.strip()[:200] + "\n"
        except (OSError, subprocess.SubprocessError) as exc:
            text = "# " + type(exc).__name__ + ": " + str(exc)[:200] + "\n"
        with open(os.path.join(dest, name), "w", encoding="utf-8") as fh:
            fh.write(text)


# ----------------------------------------------------------------------------- the plan


def build_plan(cfg: dict, cs: list, now: float, discover: bool = True) -> dict:
    """What a run would do, without reading any data: archives, excludes per archive, the containers to dump, the SQLite files to copy online."""
    archives = dict(cfg["archives"])
    excludes = {name: list(pats) for name, pats in (cfg.get("exclude") or {}).items()}
    for name in archives:
        excludes.setdefault(name, [])
    cls = classify(cs)
    notes = []
    skip_sources = []
    pg_patterns = {}
    for c in cls["postgres"]:
        for src in data_sources(c, (POSTGRES_DATA_DEST,)):
            skip_sources.append(src)
            notes.append("postgres " + c["name"] + ": dumped, data dir " + src + " left out")
            name, pat = owning_archive(archives, src)
            if name is not None:
                pg_patterns.setdefault(c["name"], []).append((name, pat))
    for c in cls["rebuildable"]:
        for src in data_sources(c, REBUILDABLE_DEST):
            skip_sources.append(src)
            notes.append("index " + c["name"] + ": data dir " + src + " left out (rebuildable)")
    for src in skip_sources:
        name, pat = owning_archive(archives, src)
        if name is None:
            notes.append("WARNING " + src + " is outside every archive")
        elif pat not in excludes[name]:
            excludes[name].append(pat)
    for c in cls["raw_engines"]:
        notes.append("engine " + c["name"] + " (" + c["image"] + "): files copied as they are (crash-consistent, like the old VM backup)")
    live, sqlite_patterns = [], {}
    if discover:
        prefixes = [cfg["staging_dir"]] + [archives[n] + p for n, pats in excludes.items() for p in pats if "\\" not in p and not re.search(r"[*?\[]", p)]
        roots = [r for n, r in archives.items()]
        raw = cfg.get("raw_sqlite") or []
        for path, size, mtime in sqlite_candidates(roots, prefixes):
            if any(fnmatch.fnmatchcase(path, g) for g in raw):
                notes.append("sqlite " + path + ": listed in raw_sqlite, copied as it is")
                continue
            if is_live(path, mtime, now):
                live.append({"path": path, "size": size, "wal": journal_mode_wal(path)})
                name, pat = owning_archive(archives, path)
                if name is None:
                    continue
                for suffix in ("", "-wal", "-shm", "-journal"):
                    p = pat + suffix
                    if p not in excludes[name]:
                        excludes[name].append(p)
                    sqlite_patterns.setdefault(path, []).append((name, p))
    problems = collisions(archives, excludes)
    return {"archives": archives, "excludes": excludes, "postgres": cls["postgres"], "pg_patterns": pg_patterns, "sqlite_patterns": sqlite_patterns, "live_sqlite": live, "notes": notes, "problems": problems}


def client_command(cfg: dict, plan: dict, staging: str) -> list:
    cmd = ["proxmox-backup-client", "backup"]
    for name, root in plan["archives"].items():
        cmd.append(name + ".pxar:" + root)
    cmd.append("staging.pxar:" + staging)
    cmd += ["--repository", cfg["repository"], "--ns", cfg["namespace"], "--backup-type", cfg["backup_type"], "--backup-id", cfg["backup_id"],
            "--crypt-mode", "none", "--change-detection-mode", "metadata", "--skip-lost-and-found", "true", "--entries-max", str(cfg.get("entries_max", 4194304))]
    for name in plan["archives"]:
        for pat in plan["excludes"].get(name, []):
            cmd += ["--exclude", pat]
    return cmd


def client_env(cfg: dict, secret: str) -> dict:
    env = dict(os.environ)
    env.update({"PBS_PASSWORD": secret, "PBS_FINGERPRINT": cfg["fingerprint"], "HOME": env.get("HOME", "/root")})
    return env


# ----------------------------------------------------------------------------- load guard


def loadavg() -> tuple:
    with open("/proc/loadavg", encoding="utf-8") as fh:
        a = fh.read().split()
    return float(a[0]), float(a[1]), float(a[2])


def wait_for_calm(limits: dict, loadavg_fn=None, sleep_fn=None) -> bool:
    """True when the 5-minute load average is at or under start_load5 within start_wait_s."""
    loadavg_fn, sleep_fn = loadavg_fn or loadavg, sleep_fn or time.sleep
    deadline = time.time() + limits["start_wait_s"]
    while True:
        if loadavg_fn()[1] <= limits["start_load5"]:
            return True
        if time.time() >= deadline:
            return False
        sleep_fn(30)


class Watchdog(threading.Thread):
    """Stops the client when the load climbs past abort_load1 twice in a row or the deadline passes."""

    def __init__(self, proc, limits, loadavg_fn=None, period=15.0):
        super().__init__(daemon=True)
        self.proc, self.limits, self.loadavg_fn, self.period = proc, limits, loadavg_fn or loadavg, period
        self.reason = ""
        self._halt = threading.Event()
        self.started_at = time.time()

    def run(self):
        high = 0
        while not self._halt.wait(self.period):
            if self.proc.poll() is not None:
                return
            if time.time() - self.started_at > self.limits["deadline_s"]:
                self.reason = "deadline of " + str(int(self.limits["deadline_s"])) + " s passed"
            else:
                high = high + 1 if self.loadavg_fn()[0] > self.limits["abort_load1"] else 0
                if high >= 2:
                    self.reason = "load1 stayed above " + str(self.limits["abort_load1"])
            if self.reason:
                self.proc.terminate()
                try:
                    self.proc.wait(60)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                return

    def stop(self):
        self._halt.set()


# ----------------------------------------------------------------------------- metrics


def write_metrics(path: str, ok: bool, started: float, finished: float, warnings: int, staged_bytes: int, prev_success, staging_peak: int = 0) -> None:
    if not path or not os.path.isdir(os.path.dirname(path)):
        return
    success = finished if ok else (prev_success or 0)
    lines = [
        "# HELP dockerhost_state_backup_last_run_timestamp_seconds When the last run of dockerhost-state-backup ended.",
        "# TYPE dockerhost_state_backup_last_run_timestamp_seconds gauge",
        "dockerhost_state_backup_last_run_timestamp_seconds %d" % finished,
        "# HELP dockerhost_state_backup_last_success_timestamp_seconds When the last run that ended well ended.",
        "# TYPE dockerhost_state_backup_last_success_timestamp_seconds gauge",
        "dockerhost_state_backup_last_success_timestamp_seconds %d" % success,
        "# HELP dockerhost_state_backup_last_status 1 when the last run ended well, 0 when it failed or was skipped.",
        "# TYPE dockerhost_state_backup_last_status gauge",
        "dockerhost_state_backup_last_status %d" % (1 if ok else 0),
        "# HELP dockerhost_state_backup_duration_seconds Length of the last run.",
        "# TYPE dockerhost_state_backup_duration_seconds gauge",
        "dockerhost_state_backup_duration_seconds %d" % (finished - started),
        "# HELP dockerhost_state_backup_warnings Warnings of the last run (a database that could not be dumped or copied, ...).",
        "# TYPE dockerhost_state_backup_warnings gauge",
        "dockerhost_state_backup_warnings %d" % warnings,
        "# HELP dockerhost_state_backup_staged_bytes Bytes of database dumps and copies staged for the last run.",
        "# TYPE dockerhost_state_backup_staged_bytes gauge",
        "dockerhost_state_backup_staged_bytes %d" % staged_bytes,
        "# HELP dockerhost_state_backup_staging_peak_bytes The most the staging directory held at any moment of the last run (the burst on the guest disk).",
        "# TYPE dockerhost_state_backup_staging_peak_bytes gauge",
        "dockerhost_state_backup_staging_peak_bytes %d" % staging_peak,
    ]
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def previous_success(path: str):
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("dockerhost_state_backup_last_success_timestamp_seconds "):
                    return int(float(line.split()[1]))
    except (OSError, ValueError):
        pass
    return None


# ----------------------------------------------------------------------------- run


def dir_bytes(path: str) -> int:
    total = 0
    for base, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(base, f))
            except OSError:
                pass
    return total


def remove_staging(staging: str) -> None:
    if os.path.isdir(staging) and "dockerhost-state" in os.path.basename(staging.rstrip("/")) and staging.startswith(("/var/backups/", "/var/tmp/")):
        shutil.rmtree(staging, ignore_errors=True)


def note_peak(plan: dict, staging: str) -> None:
    plan["staging_peak"] = max(plan.get("staging_peak", 0), dir_bytes(staging))


def check_staged(db: dict, dst: str, lim: dict, warnings: list) -> None:
    """quick_check of the staged copy, in its own child with its own (advisory) timeout; it never discards the copy."""
    cap = lim.get("check_max_bytes", CHECK_MAX_BYTES_DEFAULT)
    if db["size"] > cap:  # the check reads the whole copy again: on the CPU-starved host that was 51 min for kuma.db (2.5 GB) and over an hour for graph.db and chaos.db
        log("note: " + db["path"] + " is " + str(db["size"] >> 20) + " MiB, above check_max_bytes (" + str(cap >> 20) + " MiB): copied, not checked")
        return
    # The copy is complete and consistent (one read snapshot); the check only tells whether the SOURCE was already damaged. It reads the whole copy again,
    # which on a starved host can take far longer than the copy (2026-10-21: chaos.db, 8.7 GB, over an hour), so it has its own limit and never discards the copy.
    try:
        chk = run([sys.executable, os.path.abspath(__file__), "_check", dst, db["path"]], timeout=lim.get("check_timeout_s", 3600))
        if chk.returncode != 0:
            warnings.append("quick_check of the copy of " + db["path"] + " failed (the source database is damaged; the copy is kept): " + chk.stderr.strip()[:160])
            log("WARNING " + warnings[-1])
        elif chk.stdout.strip():
            log(chk.stdout.strip().splitlines()[-1])
    except subprocess.TimeoutExpired:
        log("note: quick_check of the copy of " + db["path"] + " did not finish within " + str(int(lim.get("check_timeout_s", 3600))) + " s: copy kept, not checked")
    except OSError as exc:
        log("note: quick_check of " + db["path"] + " could not run: " + type(exc).__name__)


def compress_staged(db: dict, dst: str, lim: dict, warnings: list, trimmer, on_peak=None) -> dict:
    """zstd the staged copy at dst (own child, own timeout) and delete the raw file once the compressed one is proven to hold the same bytes.
    on_peak is called when both files exist, which is the moment the directory is fullest. Returns what the manifest records ({} when it did
    not work: the raw copy stays and a warning says so, the backup is complete either way)."""
    out = dst + STAGED_SUFFIX
    began = time.time()
    try:
        res = run([sys.executable, os.path.abspath(__file__), "_compress", dst, out], timeout=lim.get("compress_timeout_s", COMPRESS_TIMEOUT_DEFAULT))
        if res.returncode != 0:
            raise BackupError("compressing the copy of " + db["path"] + " failed (the raw copy is staged instead): " + res.stderr.strip()[:300])
        info = json.loads(res.stdout.strip().splitlines()[-1])
    except (BackupError, subprocess.TimeoutExpired, OSError, ValueError, IndexError) as exc:
        for stale in (out, out + ".part"):
            try:
                os.remove(stale)
            except OSError:
                pass
        warnings.append(str(exc) if isinstance(exc, BackupError) else "compressing the copy of " + db["path"] + ": " + type(exc).__name__ + " (the raw copy is staged instead)")
        log("WARNING " + warnings[-1])
        return {}
    if on_peak:
        on_peak()
    try:
        release(dst, trimmer)
    except OSError as exc:  # both files are staged then: more bytes on the disk, nothing lost
        warnings.append("the raw copy of " + db["path"] + " could not be deleted after it was compressed: " + type(exc).__name__)
        log("WARNING " + warnings[-1])
    log("compressed %s: %d -> %d bytes (zstd -%d, %.0f s)" % (db["path"], info["bytes"], info["compressed"], ZSTD_LEVEL, time.time() - began))
    return {"codec": "zstd", "level": ZSTD_LEVEL, "copy_bytes": info["bytes"], "staged_bytes": info["compressed"], "sha256": info["sha256"]}


def stage(cfg: dict, plan: dict, staging: str, trimmer=None) -> list:
    """Fill the staging directory. Returns the warnings; plan["pg_failed"] names the Postgres containers whose dump failed.
    The SQLite copies are made one at a time, largest first. A copy of compress_min_bytes or more is compressed with zstd right away and its raw file is
    deleted (its blocks trimmed) before the next copy starts, so the directory never holds more than one raw copy; plan["staging_peak"] is the most it held."""
    lim = cfg["limits"]
    warnings = []
    plan["pg_failed"], plan["sqlite_failed"], plan["staging_peak"], plan["staged_info"] = [], [], 0, {}
    os.makedirs(staging, mode=0o700)
    os.makedirs(os.path.join(staging, "pg"))
    for c in plan["postgres"]:
        try:
            path = dump_postgres(c, os.path.join(staging, "pg"), lim["dump_timeout_s"])
            log("dumped " + c["name"] + " -> " + str(os.path.getsize(path)) + " bytes")
        except (BackupError, OSError) as exc:
            warnings.append(str(exc))
            plan["pg_failed"].append(c["name"])
            log("WARNING " + str(exc))
    compress_min = lim.get("compress_min_bytes", COMPRESS_MIN_BYTES_DEFAULT)
    compress = compress_min > 0 and any(x["size"] >= compress_min for x in plan["live_sqlite"])  # nothing big enough: nothing to compress, nothing to check for
    if compress and not zstd_binary():
        warnings.append("zstd is not installed: the SQLite copies are staged uncompressed, all at once (the staging peak is their full size)")
        log("WARNING " + warnings[-1])
        compress = False
    if compress and trimmer is not None and trimmer.enabled:
        problem = trim_selftest(staging)
        if problem:
            warnings.append("giving freed staging blocks back to the disk does not work here (" + problem + "): the SQLite copies are staged as before, all at once, because one at a time would put more on the hypervisor")
            log("WARNING " + warnings[-1])
            compress = False
    sizes = sorted((x["size"] for x in plan["live_sqlite"]), reverse=True)
    # compressed: one raw copy at a time plus what the compressed ones leave behind (a generous half); otherwise all of them at once
    need = int(sizes[0] * 1.05 + 0.5 * sum(sizes[1:])) if compress else int(sum(sizes) * 1.1)
    free = shutil.disk_usage(os.path.dirname(staging.rstrip("/"))).free
    if need + (2 << 30) > free:
        raise BackupError("not enough free space for the SQLite copies: need about %d MiB, %d MiB free" % (need >> 20, free >> 20))
    note_peak(plan, staging)
    for db in sorted(plan["live_sqlite"], key=lambda x: (-x["size"], x["path"])):
        dst = os.path.join(staging, "sqlite", db["path"].lstrip("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            res = run([sys.executable, os.path.abspath(__file__), "_sqlite", db["path"], dst, "1" if db["wal"] else "0"], timeout=lim["sqlite_timeout_s"])
            if res.returncode != 0:
                raise BackupError("online copy of " + db["path"] + " failed: " + res.stderr.strip()[:200])
            log("copied " + db["path"] + " -> " + str(os.path.getsize(dst)) + " bytes")
        except (BackupError, subprocess.TimeoutExpired, OSError) as exc:
            warnings.append(str(exc) if isinstance(exc, BackupError) else "online copy of " + db["path"] + ": " + type(exc).__name__)
            plan["sqlite_failed"].append(db["path"])
            log("WARNING " + warnings[-1])
            if os.path.exists(dst):
                os.remove(dst)
            continue
        note_peak(plan, staging)
        check_staged(db, dst, lim, warnings)
        info = {"staged": os.path.relpath(dst, staging), "copy_bytes": os.path.getsize(dst)}
        if compress and info["copy_bytes"] >= compress_min:
            packed = compress_staged(db, dst, lim, warnings, trimmer, lambda: note_peak(plan, staging))
            if packed:
                info.update(packed, staged=os.path.relpath(dst + STAGED_SUFFIX, staging))
        plan["staged_info"][db["path"]] = info
        note_peak(plan, staging)
    stage_inventory(os.path.join(staging, "inventory"))
    manifest = {"created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "postgres": [c["name"] for c in plan["postgres"]],
                "sqlite": [dict({"path": x["path"], "size": x["size"]}, **plan["staged_info"].get(x["path"], {})) for x in plan["live_sqlite"]],
                "staging_peak_bytes": plan["staging_peak"], "notes": plan["notes"], "warnings": warnings}
    with open(os.path.join(staging, "MANIFEST.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1)
    return warnings


def do_run(cfg: dict, args) -> int:
    lim = cfg["limits"]
    started = time.time()
    metrics = cfg.get("textfile")
    prev = previous_success(metrics) if metrics else None
    lock = open(LOCK_PATH, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log("another run holds " + LOCK_PATH)
        return EXIT_BUSY
    staging = cfg["staging_dir"]
    ok, warnings, staged, peak = False, [], 0, 0
    trimmer = TrimWorker(os.path.dirname(staging.rstrip("/")) or "/", enabled=cfg.get("trim_staging", True))
    try:
        secret = read_secret(cfg["secret_file"])
        if not shutil.which("proxmox-backup-client"):
            raise BackupError("proxmox-backup-client is not installed")
        if not args.skip_load_check and not wait_for_calm(lim):
            log("host busy: load5 stayed above %s for %s s, skipping this run" % (lim["start_load5"], lim["start_wait_s"]))
            write_metrics(metrics, False, started, time.time(), 0, 0, prev)
            return EXIT_SKIPPED
        remove_staging(staging)
        cs = containers()
        plan = build_plan(cfg, cs, time.time())
        for n in plan["notes"]:
            log(n)
        if plan["problems"]:
            raise BackupError("; ".join(plan["problems"]))
        log("%d postgres dumps, %d live SQLite copies, archives: %s" % (len(plan["postgres"]), len(plan["live_sqlite"]), ", ".join(plan["archives"])))
        warnings = stage(cfg, plan, staging, trimmer)
        peak = plan["staging_peak"]
        for name in plan["pg_failed"]:  # no dump: a raw copy of the data dir (may need crash recovery) is better than nothing
            for archive, pat in plan["pg_patterns"].get(name, []):
                if pat in plan["excludes"][archive]:
                    plan["excludes"][archive].remove(pat)
            log("WARNING " + name + ": its data dir is copied as it is instead (no usable dump)")
        for path in plan["sqlite_failed"]:  # no online copy: the file itself (with its WAL, copied at two moments) is better than nothing
            for archive, pat in plan["sqlite_patterns"].get(path, []):
                if pat in plan["excludes"][archive]:
                    plan["excludes"][archive].remove(pat)
            log("WARNING " + path + ": copied as it is instead (no usable online copy)")
        staged = dir_bytes(staging)
        cmd = client_command(cfg, plan, staging)
        log("starting the client (%d archives, %d excludes)" % (len(plan["archives"]) + 1, sum(len(v) for v in plan["excludes"].values())))
        proc = subprocess.Popen(cmd, env=client_env(cfg, secret), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        dog = Watchdog(proc, lim)
        dog.start()
        for line in proc.stdout:
            sys.stdout.write(line)
        rc = proc.wait()
        dog.stop()
        if dog.reason:
            raise BackupError("client stopped: " + dog.reason)
        if rc != 0:
            raise BackupError("proxmox-backup-client exited with " + str(rc))
        ok = True
    except BackupError as exc:
        log("FAILED: " + str(exc))
    finally:
        extents = tree_extents(staging) if trimmer.enabled else []  # what is left of the staging goes back to the disk right away too (the guest's fstrim.timer runs once an hour)
        remove_staging(staging)
        trimmer.submit(extents, os.path.dirname(staging.rstrip("/")) or "/")
        trimmer.close(lim.get("trim_wait_s", TRIM_WAIT_DEFAULT))
        write_metrics(metrics, ok and not warnings, started, time.time(), len(warnings), staged, prev, peak)
    if ok and warnings:
        log("backup written, but %d warning(s): %s" % (len(warnings), "; ".join(warnings)))
    return EXIT_OK if ok and not warnings else EXIT_FAILED


def do_plan(cfg: dict) -> int:
    plan = build_plan(cfg, containers(), time.time())
    print("repository: " + cfg["repository"] + "  ns: " + cfg["namespace"] + "  group: " + cfg["backup_type"] + "/" + cfg["backup_id"])
    for name, root in plan["archives"].items():
        print("archive %-8s %s  (%d excludes)" % (name, root, len(plan["excludes"].get(name, []))))
    print("postgres dumps: " + ", ".join(c["name"] for c in plan["postgres"]))
    for x in plan["live_sqlite"]:
        print("live sqlite: %s (%d MiB, %s)" % (x["path"], x["size"] >> 20, "wal" if x["wal"] else "journal"))
    compress_min = cfg["limits"].get("compress_min_bytes", COMPRESS_MIN_BYTES_DEFAULT)
    if compress_min > 0:
        print("staging: SQLite copies one at a time, largest first; those of %d MiB and more are compressed with zstd -%d (%s) and their raw copy is deleted; trim of freed blocks %s"
              % (compress_min >> 20, ZSTD_LEVEL, "zstd found" if zstd_binary() else "ZSTD MISSING: they would be staged uncompressed", "on" if cfg.get("trim_staging", True) else "off"))
    else:
        print("staging: SQLite copies are staged uncompressed, all at once (limits.compress_min_bytes is 0)")
    for n in plan["notes"]:
        print("note: " + n)
    for p in plan["problems"]:
        print("PROBLEM: " + p)
    return EXIT_FAILED if plan["problems"] else EXIT_OK


def do_check(cfg: dict) -> int:
    secret = read_secret(cfg["secret_file"])
    if not shutil.which("proxmox-backup-client"):
        raise BackupError("proxmox-backup-client is not installed")
    res = run(["proxmox-backup-client", "snapshot", "list", "host/" + cfg["backup_id"], "--repository", cfg["repository"], "--ns", cfg["namespace"], "--output-format", "json"],
              env=client_env(cfg, secret), timeout=120)
    if res.returncode != 0:
        raise BackupError("cannot list " + cfg["backup_id"] + ": " + res.stderr.strip()[:300])
    print("ok: the token can reach " + cfg["repository"].split("@")[-1] + " namespace " + cfg["namespace"] + "; " + str(len(json.loads(res.stdout or "[]"))) + " snapshot(s) of the group")
    return EXIT_OK


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "_sqlite":
        return stage_sqlite_child(argv[1:])
    if argv and argv[0] == "_check":
        return check_child(argv[1:])
    if argv and argv[0] == "_compress":
        return compress_child(argv[1:])
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("command", choices=("run", "plan", "check"))
    ap.add_argument("--config", default=CONFIG_PATH)
    ap.add_argument("--skip-load-check", action="store_true", help="start even when the load is high (a supervised first run)")
    args = ap.parse_args(argv)
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        print("must run as root", file=sys.stderr)
        return EXIT_USAGE
    try:
        cfg = load_config(args.config)
        return {"run": lambda: do_run(cfg, args), "plan": lambda: do_plan(cfg), "check": lambda: do_check(cfg)}[args.command]()
    except BackupError as exc:
        print("error: " + str(exc), file=sys.stderr)
        return EXIT_FAILED
    except (OSError, ValueError) as exc:
        print("error: " + type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
