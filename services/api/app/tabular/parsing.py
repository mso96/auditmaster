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


def parse_amount(value, decimal_separator):
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
            pattern = (
                rf"[+-]?(?:(?:\d+|\d{{1,3}}(?:{t}\d{{3}})+)(?:{d}\d*)?"
                rf"|{d}\d+)(?:[eE][+-]?\d+)?"
            )
            if not re.fullmatch(pattern, value):
                return None
            result = Decimal(value.replace(thousands, "").replace(decimal_separator, "."))
        # Bound adversarial exponents before exact Fraction arithmetic allocates integers.
        return result if result.is_finite() and abs(result.adjusted()) <= 308 else None
    except (InvalidOperation, ValueError, OverflowError):
        return None


def parse_dates(series, *, date_format=None, dayfirst=True, field="date", warnings=None):
    if warnings is None:
        warnings = []
    source = series.reset_index(drop=True)
    if pd.api.types.is_datetime64_any_dtype(source.dtype):
        parsed = source
    else:
        # Native dates remain native. Numeric cells are not implicitly Unix nanoseconds.
        safe = source.map(lambda v: v if isinstance(v, (str, date, datetime)) else None)
        # Audit dates are local wall dates, not UTC instants. Strip timezone metadata
        # before bulk parsing so mixed offsets don't fail or change the posting day.
        safe = safe.map(lambda v: v.replace(tzinfo=None) if isinstance(v, datetime) else v)
        safe = safe.map(
            lambda v: (
                re.sub(r"(?:Z|[+-]\d{2}:?\d{2})$", "", v)
                if isinstance(v, str) and re.search(r"[T ]\d{2}:", v)
                else v
            )
        )
        if date_format is None:
            ambiguous = []
            for i, v in enumerate(source):
                if isinstance(v, str):
                    match = re.fullmatch(r"\s*(\d{1,2})[./-](\d{1,2})[./-]\d{4}\s*", v)
                    if match and 1 <= int(match[1]) <= 12 and 1 <= int(match[2]) <= 12:
                        if int(match[1]) != int(match[2]):
                            ambiguous.append(i)
            if ambiguous:
                warnings.append(f"Tarih sırası belirsiz satırlar {ambiguous}; dayfirst={dayfirst}.")
        parsed = pd.Series(pd.NaT, index=source.index, dtype=object)
        native = safe.map(lambda v: isinstance(v, (date, datetime)))
        iso = safe.map(lambda v: isinstance(v, str) and bool(re.match(r"^\d{4}-\d{2}-\d{2}", v)))
        if date_format is not None:
            iso[:] = False
        for mask, fmt, dayfirst in (
            (native, "mixed", False),
            (iso & ~native, "ISO8601", False),
            (~native & ~iso, date_format or "mixed", dayfirst),
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
        warnings.append(f"{field}: geçersiz değer içeren satırlar {bad}.")
    return [None if pd.isna(v) else v.date() for v in parsed]


def parse_amounts(series, *, decimal_separator=".", field="amount", warnings=None):
    """Return exact Decimals; auto is a column-level ingestion policy, not row guessing."""
    if warnings is None:
        warnings = []
    raw = list(series)
    auto = decimal_separator == "auto"
    if auto:
        strings = [re.sub(r"\s+", "", v) for v in raw if isinstance(v, str)]
        mixed = [v for v in strings if "," in v and "." in v]
        if mixed:
            decimal_separator = "," if mixed[0].rfind(",") > mixed[0].rfind(".") else "."
        elif any("," in v for v in strings):
            decimal_separator = ","
        elif any(re.fullmatch(r"[+-]?\d{1,3}(?:\.\d{3})+", v) for v in strings):
            decimal_separator = ","
        else:
            decimal_separator = "."
    if decimal_separator not in (".", ","):
        raise ValueError("decimal_separator must be '.', ',' or 'auto'")
    parsed = [parse_amount(v, decimal_separator) for v in raw]
    invalid = [
        i
        for i, (v, p) in enumerate(zip(raw, parsed, strict=True))
        if text(v) is not None and p is None
    ]
    ambiguous = [
        i
        for i, v in enumerate(raw)
        if isinstance(v, str)
        and re.fullmatch(r"[+-]?\d{1,3}(?:[.,]\d{3})+", v.strip())
        and (auto or decimal_separator in v)
    ]
    if invalid:
        warnings.append(f"{field}: geçersiz değer içeren satırlar {invalid}.")
    if ambiguous:
        warnings.append(
            f"Belirsiz binlik ayırıcı içeren satırlar {ambiguous}; "
            f"decimal_separator={decimal_separator} uygulandı."
        )
    return parsed
