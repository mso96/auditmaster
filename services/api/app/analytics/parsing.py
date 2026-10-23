"""Rule-specific invoice and identity normalization (locale parsing is shared)."""

import re


def invoice(value):
    if not value:
        return None
    parts = re.findall(r"[^\W\d_]+|\d+", value)
    return "|".join((p.lstrip("0") or "0") if p.isdigit() else p.upper() for p in parts) or None


def identity(value):
    return (value or "").strip().translate(str.maketrans({"İ": "i", "I": "ı"})).casefold()


def same_identity(left, right):
    if not left or not right:
        return False
    # ASCII-only ERP account codes often use ALI for ali. Once either side
    # contains Turkish characters, preserve the dotted/dotless distinction.
    if left.isascii() and right.isascii():
        return left.strip().casefold() == right.strip().casefold()
    return identity(left) == identity(right)
