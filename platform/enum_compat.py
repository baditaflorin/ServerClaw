from __future__ import annotations

import sys
from enum import Enum

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:  # pragma: no cover - Python < 3.11 fallback
    class StrEnum(str, Enum):
        pass


__all__ = ["StrEnum"]
