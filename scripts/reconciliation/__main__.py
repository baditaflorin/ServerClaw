"""Allow ``python -m scripts.reconciliation`` to invoke the CLI."""

from scripts.reconciliation.cli import main

raise SystemExit(main())
