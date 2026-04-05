"""ADR 0347: File-domain lock helpers for atomic infrastructure mutations.
ADR 0355: Apply-phase serialization via VM-level apply locks.

These are thin wrappers over ResourceLockRegistry that enforce the canonical
lock-key naming convention:

  File-domain locks (ADR 0347):
    vm:{vmid}:config:{role}:{filename}
    Example: vm:101:config:keycloak_runtime:docker-compose.yml

  Apply-phase locks (ADR 0355):
    vm:{vmid}:apply
    Example: vm:101:apply

Both use EXCLUSIVE lock type — only one writer at a time per resource.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

from .registry import ResourceLockRegistry, ResourceLocked
from .schema import LockEntry, LockType


# Lock TTL defaults
FILE_DOMAIN_LOCK_TTL = 300   # 5 min — typical Ansible task duration
APPLY_LOCK_TTL = 1800         # 30 min — full playbook apply can take longer


def file_domain_resource(vmid: str | int, role: str, filename: str) -> str:
    """Return canonical lock resource path for a managed config file.

    Example:
        file_domain_resource("101", "keycloak_runtime", "docker-compose.yml")
        → "vm:101:config:keycloak_runtime:docker-compose.yml"
    """
    return f"vm:{vmid}:config:{role}:{filename}"


def apply_resource(vmid: str | int) -> str:
    """Return canonical lock resource path for a VM-level apply operation.

    Example:
        apply_resource("101") → "vm:101:apply"
    """
    return f"vm:{vmid}:apply"


def acquire_file_domain_lock(
    registry: ResourceLockRegistry,
    *,
    vmid: str | int,
    role: str,
    filename: str,
    holder: str,
    context_id: str | None = None,
    ttl_seconds: int = FILE_DOMAIN_LOCK_TTL,
    wait_seconds: int = 0,
    metadata: dict[str, Any] | None = None,
) -> LockEntry:
    """Acquire an EXCLUSIVE lock on a specific managed config file.

    ADR 0347: Prevents two agents from concurrently writing the same
    docker-compose.yml, nginx fragment, or systemd unit.

    Args:
        registry: ResourceLockRegistry instance.
        vmid: VM ID (e.g. "101").
        role: Ansible role name managing the file (e.g. "keycloak_runtime").
        filename: Config file basename (e.g. "docker-compose.yml").
        holder: Agent/session identifier acquiring the lock.
        context_id: Optional workstream or job ID for audit trail.
        ttl_seconds: Lock TTL; defaults to FILE_DOMAIN_LOCK_TTL (300s).
        wait_seconds: Seconds to wait if resource is already locked.
        metadata: Optional additional context dict.

    Returns:
        LockEntry for the acquired lock.

    Raises:
        ResourceLocked: If the resource is locked and wait_seconds is exhausted.
    """
    resource = file_domain_resource(vmid, role, filename)
    return registry.acquire(
        resource,
        LockType.EXCLUSIVE,
        holder,
        context_id=context_id,
        ttl_seconds=ttl_seconds,
        wait_seconds=wait_seconds,
        metadata=metadata or {},
    )


def acquire_apply_lock(
    registry: ResourceLockRegistry,
    *,
    vmid: str | int,
    holder: str,
    context_id: str | None = None,
    ttl_seconds: int = APPLY_LOCK_TTL,
    wait_seconds: int = 0,
    metadata: dict[str, Any] | None = None,
) -> LockEntry:
    """Acquire an EXCLUSIVE apply-phase lock for a VM.

    ADR 0355: Serializes full playbook applies per VM/resource-group.
    Prevents two agents from running overlapping applies against the same
    VM, eliminating double-restart races and interleaved secret rotations.

    Args:
        registry: ResourceLockRegistry instance.
        vmid: VM ID (e.g. "101").
        holder: Agent/session identifier acquiring the lock.
        context_id: Optional workstream or job ID for audit trail.
        ttl_seconds: Lock TTL; defaults to APPLY_LOCK_TTL (1800s).
        wait_seconds: Seconds to wait if resource is already locked.
        metadata: Optional additional context dict.

    Returns:
        LockEntry for the acquired lock.

    Raises:
        ResourceLocked: If the VM is already being applied and wait exhausted.
    """
    resource = apply_resource(vmid)
    return registry.acquire(
        resource,
        LockType.EXCLUSIVE,
        holder,
        context_id=context_id,
        ttl_seconds=ttl_seconds,
        wait_seconds=wait_seconds,
        metadata=metadata or {},
    )


@contextmanager
def file_domain_lock(
    registry: ResourceLockRegistry,
    *,
    vmid: str | int,
    role: str,
    filename: str,
    holder: str,
    context_id: str | None = None,
    ttl_seconds: int = FILE_DOMAIN_LOCK_TTL,
    wait_seconds: int = 0,
    metadata: dict[str, Any] | None = None,
) -> Generator[LockEntry, None, None]:
    """Context manager: acquire file-domain lock, yield, then release.

    Usage:
        with file_domain_lock(registry, vmid="101", role="keycloak_runtime",
                              filename="docker-compose.yml", holder="ws-0347"):
            # safe to write docker-compose.yml
            ...
    """
    entry = acquire_file_domain_lock(
        registry,
        vmid=vmid,
        role=role,
        filename=filename,
        holder=holder,
        context_id=context_id,
        ttl_seconds=ttl_seconds,
        wait_seconds=wait_seconds,
        metadata=metadata,
    )
    try:
        yield entry
    finally:
        registry.release(lock_id=entry.lock_id)


@contextmanager
def apply_lock(
    registry: ResourceLockRegistry,
    *,
    vmid: str | int,
    holder: str,
    context_id: str | None = None,
    ttl_seconds: int = APPLY_LOCK_TTL,
    wait_seconds: int = 0,
    metadata: dict[str, Any] | None = None,
) -> Generator[LockEntry, None, None]:
    """Context manager: acquire VM apply-phase lock, yield, then release.

    Usage:
        with apply_lock(registry, vmid="101", holder="ws-0355"):
            # safe to run full playbook apply against vm:101
            ...
    """
    entry = acquire_apply_lock(
        registry,
        vmid=vmid,
        holder=holder,
        context_id=context_id,
        ttl_seconds=ttl_seconds,
        wait_seconds=wait_seconds,
        metadata=metadata,
    )
    try:
        yield entry
    finally:
        registry.release(lock_id=entry.lock_id)
