import pytest

from apps.accounts.phone import InvalidMobile, normalize_mobile


@pytest.mark.parametrize(
    "raw",
    ["09123456789", "۰۹۱۲۳۴۵۶۷۸۹", "+989123456789", "00989123456789", "989123456789", "9123456789", "0912 345 6789", "0912-345-6789"],
)
def test_normalize_accepts_common_formats(raw):
    assert normalize_mobile(raw) == "09123456789"


@pytest.mark.parametrize("raw", ["", None, "0912345678", "091234567890", "08123456789", "abc", "+19123456789"])
def test_normalize_rejects_invalid(raw):
    with pytest.raises(InvalidMobile):
        normalize_mobile(raw)
