# Preserve network semantics in sanitized address examples

Public CI exposed five stale-source findings introduced by sanitizing specific Tailnet addresses into the public documentation range. The production policy and its accepted findings remain correct.

Keep specific Tailnet examples inside the generic shared-address range; keep public address examples in their documentation range. Verify actual exported policies and baselines together, retain pure synthetic regressions in public, and repeat the required scripted publication after reviewed exact-head CI.

No live network changes or finding-baseline expansion are part of this workstream.

The preexisting LAN example projection also eliminates sixteen previously accepted foreign-source findings. The publisher validates every exported policy/baseline pair, refuses new non-info findings, and removes only accepted IDs that no longer exist. It validates all pairs before any write and reuses disposable-export identity, ancestor, symlink and hard-link guards. Private policies and baselines remain byte-identical.

The complete exported-workflow rehearsal also checks synthetic foreign/stale sources using a reserved documentation address that cannot collapse into the example LAN. The wrapper test fixture executes its exact Python interpreter rather than symlinking a virtualenv launcher from a different directory; policy assertions remain intact.
