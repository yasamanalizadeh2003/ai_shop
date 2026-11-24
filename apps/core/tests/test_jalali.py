from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from apps.core.jalali import gregorian_to_jalali, jalali_to_gregorian
from apps.core.templatetags.persian import jdate


@pytest.mark.parametrize(
    "g, j",
    [
        ((2026, 11, 24), (1405, 9, 3)),
        ((2025, 3, 21), (1404, 1, 1)),
        ((2024, 3, 20), (1403, 1, 1)),
        ((2000, 1, 1), (1378, 10, 11)),
        ((2025, 3, 20), (1403, 12, 30)),  # leap Esfand
    ],
)
def test_known_dates(g, j):
    assert gregorian_to_jalali(*g) == j
    assert jalali_to_gregorian(*j) == g


def test_roundtrip_over_many_days():
    d = date(1990, 1, 1)
    for _ in range(0, 15000, 7):
        jy, jm, jd = gregorian_to_jalali(d.year, d.month, d.day)
        assert jalali_to_gregorian(jy, jm, jd) == (d.year, d.month, d.day)
        d = date.fromordinal(d.toordinal() + 7)


def test_jdate_filter_formats_in_tehran_time():
    # 22:00 UTC on Nov 23 is already Nov 24 (01:30) in Tehran.
    value = datetime(2026, 11, 23, 22, 0, tzinfo=ZoneInfo("UTC"))
    assert jdate(value) == "۱۴۰۵/۰۹/۰۳"
    assert jdate(value, "datetime") == "۱۴۰۵/۰۹/۰۳ ۰۱:۳۰"
    assert jdate(value, "long") == "۳ آذر ۱۴۰۵"
    assert jdate(None) == ""
