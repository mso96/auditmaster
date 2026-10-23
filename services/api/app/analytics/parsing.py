"""Typed upload columns are authoritative; locale parsing is a text fallback."""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from numbers import Integral, Real

import pandas as pd


def text(value):
    if value is None or pd.isna(value):
        return None
    return str(value).strip() or None


def amount(value, decimal_separator):
    if value is None or isinstance(value, bool):
        return None
    try:
        if isinstance(value, Decimal):
            result = value
        elif isinstance(value, Integral):
            result = Decimal(int(value))
        elif isinstance(value, Real):
            result = Decimal(repr(float(value)))
        else:
            value = re.sub(r"\s+", "", str(value))
            thousands = "." if decimal_separator == "," else ","
            # Validate grouping instead of silently deleting misplaced separators.
            d, t = re.escape(decimal_separator), re.escape(thousands)
            pattern = rf"[+-]?(?:\d+|\d{{1,3}}(?:{t}\d{{3}})+)(?:{d}\d+)?(?:[eE][+-]?\d+)?"
            if not re.fullmatch(pattern, value):
                return None
            result = Decimal(value.replace(thousands, "").replace(decimal_separator, "."))
        # Bound adversarial exponents before exact Fraction arithmetic allocates integers.
        return result if result.is_finite() and abs(result.adjusted()) <= 308 else None
    except (InvalidOperation, ValueError, OverflowError):
        return None


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


def dates(series, cfg, warnings):
    source = series.reset_index(drop=True)
    if pd.api.types.is_datetime64_any_dtype(source.dtype):
        parsed = source
    else:
        # Native dates remain native. Numeric cells are not implicitly Unix nanoseconds.
        safe = source.map(lambda v: v if isinstance(v, (str, date, datetime)) else None)
        if cfg.date_format is None:
            ambiguous = []
            for i, v in enumerate(source):
                if isinstance(v, str):
                    match = re.fullmatch(r"\s*(\d{1,2})[./-](\d{1,2})[./-]\d{4}\s*", v)
                    if match and 1 <= int(match[1]) <= 12 and 1 <= int(match[2]) <= 12:
                        if int(match[1]) != int(match[2]):
                            ambiguous.append(i)
            if ambiguous:
                warnings.append(
                    f"Tarih sırası belirsiz satırlar {ambiguous}; dayfirst={cfg.dayfirst}."
                )
        parsed = pd.Series(pd.NaT, index=source.index, dtype=object)
        native = safe.map(lambda v: isinstance(v, (date, datetime)))
        iso = safe.map(lambda v: isinstance(v, str) and bool(re.match(r"^\d{4}-\d{2}-\d{2}", v)))
        if cfg.date_format is not None:
            iso[:] = False
        for mask, fmt, dayfirst in (
            (native, "mixed", False),
            (iso & ~native, "ISO8601", False),
            (~native & ~iso, cfg.date_format or "mixed", cfg.dayfirst),
        ):
            if mask.any():
                parsed.loc[mask] = pd.to_datetime(
                    safe[mask], format=fmt, dayfirst=dayfirst, errors="coerce"
                ).astype(object)
    bad = [
        i
        for i, (raw, v) in enumerate(zip(source, parsed, strict=True))
        if text(raw) is not None and pd.isna(v)
    ]
    if bad:
        warnings.append(f"{cfg.posting_date_field}: geçersiz değer içeren satırlar {bad}.")
    return [None if pd.isna(v) else v.date() for v in parsed]
