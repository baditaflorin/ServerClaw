import pytest

from validation_toolkit import require_int


def test_require_int_accepts_legacy_positional_bounds() -> None:
    assert require_int(5, "field", 1, 10) == 5


def test_require_int_rejects_out_of_range_legacy_positional_bounds() -> None:
    with pytest.raises(ValueError, match="field must be <= 10"):
        require_int(11, "field", 1, 10)
