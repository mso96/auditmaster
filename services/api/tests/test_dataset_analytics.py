from datetime import date
from decimal import Decimal

import pytest
from app.analytics import run_rules
from app.datasets.profiling import prepare_table, read_table
from openpyxl import Workbook


@pytest.mark.parametrize("suffix", [".csv", ".xlsx"])
def test_uploaded_turkish_columns_are_authoritative_for_analytics(tmp_path, suffix):
    records = [
        ["Tedarikçi", "Fatura", "Tutar", "Tarih", "Para Birimi"],
        ["Çağrı", "INV-001", "1.234,56", "07.06.2026", "TRY"],
        ["Çağrı", "INV-001", "1234,56", "08.06.2026", "TRY"],
        ["Çağrı", "INV-002", "12.500", "07.06.2026", "TRY"],
        ["Çağrı", "INV-002", "12500", "08.06.2026", "TRY"],
    ]
    path = tmp_path / f"payments{suffix}"
    if suffix == ".csv":
        path.write_text("\n".join(";".join(row) for row in records), encoding="cp1254")
    else:
        book = Workbook()
        for row in records:
            book.active.append(row)
        book.save(path)
        book.close()

    source, _ = read_table(path, suffix)
    typed, profile = prepare_table(source)
    assert typed["Tutar"].tolist() == [
        Decimal("1234.56"), Decimal("1234.56"), Decimal("12500"), Decimal("12500")
    ]
    assert typed["Tarih"].tolist() == [date(2026, 6, 7), date(2026, 6, 8)] * 2
    assert any("Belirsiz binlik" in warning for warning in profile["warnings"])

    # Text fallback settings must never reinterpret authoritative typed columns.
    result = run_rules(
        typed,
        {
            "vendor_name": "Tedarikçi",
            "invoice_no": "Fatura",
            "amount": "Tutar",
            "payment_date": "Tarih",
            "currency": "Para Birimi",
        },
        {"dayfirst": False, "date_format": "%m/%d/%Y", "decimal_separator": "."},
    )
    duplicates = [f for f in result.findings if f.rule_id == "exact_duplicate"]
    assert [f.row_indices for f in duplicates] == [[0, 1], [2, 3]]
    assert [Decimal(f.evidence["amount"]) for f in duplicates] == [
        Decimal("1234.56"), Decimal("12500")
    ]
    assert [f.row_indices for f in result.findings if f.rule_id == "non_working_day"] == [
        [0], [2]
    ]
    assert result.summary.warnings == []
