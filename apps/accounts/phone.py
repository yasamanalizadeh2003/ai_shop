import re

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_MOBILE_RE = re.compile(r"^09\d{9}$")


class InvalidMobile(ValueError):
    pass


def normalize_mobile(raw: str) -> str:
    """
    Normalize an Iranian mobile number to 09XXXXXXXXX.
    Accepts Persian/Arabic digits, spaces, dashes and +98 / 0098 / 98 prefixes.
    """
    if raw is None:
        raise InvalidMobile("empty")
    value = re.sub(r"[\s\-()]", "", str(raw).translate(_DIGITS))
    if value.startswith("+98"):
        value = "0" + value[3:]
    elif value.startswith("0098"):
        value = "0" + value[4:]
    elif value.startswith("98") and len(value) == 12:
        value = "0" + value[2:]
    elif value.startswith("9") and len(value) == 10:
        value = "0" + value
    if not _MOBILE_RE.match(value):
        raise InvalidMobile(raw)
    return value
