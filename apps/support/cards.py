"""Bank card numbers: validation, masking, and scrubbing them out of free text."""

import re

_FA = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
# 16 digits, optionally split by spaces or dashes in groups of four.
_CARD_IN_TEXT = re.compile(r"(?<!\d)(?:\d[ \-]?){15}\d(?!\d)")


class InvalidCard(ValueError):
    pass


def _luhn_ok(digits):
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def normalize_card(raw):
    digits = re.sub(r"[\s\-]", "", str(raw or "").translate(_FA))
    if not re.fullmatch(r"\d{16}", digits) or not _luhn_ok(digits):
        raise InvalidCard("شماره کارت ۱۶ رقمی معتبر نیست.")
    return digits


def mask(digits):
    return f"{digits[:6]}******{digits[-4:]}"


def scrub(text):
    """Mask anything that looks like a card number typed into a message."""
    text = str(text or "")
    translated = text.translate(_FA)

    def repl(m):
        digits = re.sub(r"\D", "", m.group(0))
        return mask(digits) if _luhn_ok(digits) else m.group(0)

    return _CARD_IN_TEXT.sub(repl, translated) if _CARD_IN_TEXT.search(translated) else text
