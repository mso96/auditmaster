"""Local parsing and deterministic profiling; no remote readers or services."""

import csv
import io
import math
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from zipfile import BadZipFile, ZipFile

import pandas as pd
from openpyxl import load_workbook

from app.tabular.parsing import parse_amounts, parse_dates

MAX_BYTES = 50 * 1024 * 1024
MAX_CELLS = 2_000_000


def scalar(value):
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, str):
        return value.strip() or None
    return value


def read_table(path: Path, suffix: str, sheet: str | None = None):
    selected = None
    if suffix == ".csv":
        if sheet:
            raise ValueError("CSV dosyasında çalışma sayfası seçilemez.")
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp1254")
        if "\x00" in text:
            raise ValueError("Dosya geçerli bir CSV değil.")
        try:
            dialect = csv.Sniffer().sniff(text[:65536], delimiters=";,\t|")
            delimiter = dialect.delimiter
        except csv.Error:
            # One-column CSVs are valid; prefer the most common header separator.
            header = text.splitlines()[0] if text else ""
            delimiter = max(";\t,|", key=header.count)
        records = bounded_rows(csv.reader(io.StringIO(text), delimiter=delimiter, strict=True))
    else:
        try:
            with ZipFile(path) as archive:
                if sum(item.file_size for item in archive.infolist()) > 256 * 1024 * 1024:
                    raise ValueError("Excel içeriği açıldığında 256 MB sınırını aşıyor.")
        except BadZipFile as exc:
            raise ValueError("Geçerli bir XLSX dosyası seçin.") from exc
        workbook = load_workbook(path, read_only=True, data_only=True, keep_links=False)
        try:
            selected = sheet or workbook.sheetnames[0]
            if selected not in workbook.sheetnames:
                raise ValueError("Çalışma sayfası bulunamadı.")
            worksheet = workbook[selected]
            if (worksheet.max_row or 0) * (worksheet.max_column or 0) > MAX_CELLS:
                raise ValueError("Çalışma sayfası 2.000.000 hücre sınırını aşıyor.")
            records = bounded_rows(worksheet.iter_rows(values_only=True))
            while records and all(scalar(v) is None for v in records[-1]):
                records.pop()
        finally:
            workbook.close()
    # Empty physical CSV lines have no fields. Delimiter-only rows are real null records.
    records = [list(row) for row in records if len(row)]
    if not records:
        raise ValueError("Dosya boş; sütun başlıkları bulunamadı.")
    headers = [str(v).strip() if v is not None else "" for v in records[0]]
    if not all(headers) or len(headers) != len(set(headers)):
        raise ValueError("Sütun başlıkları dolu ve benzersiz olmalıdır.")
    if any(len(row) != len(headers) for row in records[1:]):
        raise ValueError("Satırlardaki sütun sayıları başlıklarla eşleşmiyor.")
    frame = pd.DataFrame(records[1:], columns=headers, dtype=object)
    return frame, selected


def bounded_rows(source):
    records, cells = [], 0
    for row in source:
        cells += len(row)
        if cells > MAX_CELLS:
            raise ValueError("Dosya 2.000.000 hücre sınırını aşıyor.")
        records.append(row)
    return records


def boolean(value):
    if isinstance(value, bool):
        return value
    text = str(value).casefold()
    if text in ("true", "false", "evet", "hayır"):
        return text in ("true", "evet")
    raise ValueError


def json_number(value):
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else str(value)


def prepare_table(frame: pd.DataFrame):
    """Return authoritative typed columns and a profile; preview stays source-original."""
    columns, warnings = [], []
    typed = frame.copy()
    for name in frame.columns:
        raw = frame[name].tolist()
        present = [i for i, value in enumerate(raw) if scalar(value) is not None]
        values = [raw[i] for i in present]
        kind, converted = "text", [str(scalar(v)) for v in values]
        if values:
            try:
                converted = [boolean(v) for v in values]
                kind = "boolean"
            except (ValueError, TypeError):
                number_warnings = []
                amounts = parse_amounts(
                    raw, decimal_separator="auto", field=name, warnings=number_warnings
                )
                if all(amounts[i] is not None for i in present):
                    kind, converted = "number", [amounts[i] for i in present]
                    warnings.extend(number_warnings)
                else:
                    date_warnings = []
                    days = parse_dates(frame[name], field=name, warnings=date_warnings)
                    if all(days[i] is not None for i in present):
                        kind, converted = "date", [days[i] for i in present]
                        warnings.extend(date_warnings)
        if kind != "text":
            normalized = [None] * len(raw)
            for i, value in zip(present, converted, strict=True):
                normalized[i] = value
            typed[name] = pd.Series(normalized, index=frame.index, dtype=object)
        counts = Counter(converted)
        minimum = min(converted) if converted and kind in ("number", "date") else None
        maximum = max(converted) if converted and kind in ("number", "date") else None
        columns.append(
            {
                "name": name,
                "type": kind,
                "null_count": len(raw) - len(values),
                "distinct_count": len(counts),
                # JSON clients expect numeric min/max; distinct counts and typed handoff
                # are computed with exact Decimal values, never rounded binary floats.
                "min": json_number(minimum) if kind == "number" else scalar(minimum),
                "max": json_number(maximum) if kind == "number" else scalar(maximum),
                "top_values": [{"value": v, "count": c} for v, c in counts.most_common(5)]
                if kind == "text"
                else [],
            }
        )
    result = {"row_count": len(frame), "columns": columns}
    if warnings:
        result["warnings"] = warnings
    return typed, result


def profile(frame: pd.DataFrame):
    return prepare_table(frame)[1]


def preview(frame: pd.DataFrame):
    return {
        "columns": list(frame.columns),
        "rows": [
            {key: scalar(value) for key, value in row.items()}
            for row in frame.head(100).to_dict(orient="records")
        ],
    }
