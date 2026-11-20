# Purpose: Prevent automatic loading of the SCTP kernel module while its privilege-escalation issue is unpatched.
# Use case: Temporary containment on servers where no SCTP sockets are active or required.
# Inputs: A reachable Linux host, `ss`, `modprobe`, and the active kernel config.
# Outputs: Persistent SCTP module install block, unloaded module, and verified empty SCTP socket table.
# Idempotency: Yes; reruns preserve the same module policy and verify the runtime state.
# Dependencies: ADR 0498; kernel must expose SCTP as a loadable module rather than built-in support.

The role fails closed when SCTP sockets are present, the active kernel config is
unknown, or SCTP is built into the kernel. It is a temporary kernel mitigation,
not a substitute for installing the vendor's fixed kernel when available.
