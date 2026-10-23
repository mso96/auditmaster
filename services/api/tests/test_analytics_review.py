import asyncio
import json
import math
import random
from datetime import date, timedelta
from decimal import Decimal
from importlib.resources import files
from time import perf_counter

import pandas as pd
import pytest
from app.analytics import RulesConfig, run_rules
from app.analytics.fuzzy import clusters
from app.analytics.limits import MAX_BODY_BYTES, AnalysisBodyLimit
from app.analytics.parsing import invoice
from app.main import create_app
from fastapi.testclient import TestClient


def run(rows, **config):
    frame = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    return run_rules(frame, {c: c for c in frame.columns}, config)


def matches(result, rule):
    return [f.row_indices for f in result.findings if f.rule_id == rule]


def test_turkish_dates_iso_and_invalid_are_consistent():
    result = run(
        [
            {"payment_date": d}
            for d in ["07.06.2026", "13.06.2026", "2026-06-07", "31.02.2026", "bad"]
        ]
    )
    assert matches(result, "non_working_day") == [[0], [1], [2]]
    assert any("belirsiz" in w and "[0]" in w for w in result.summary.warnings)
    assert any("geçersiz" in w and "[3, 4]" in w for w in result.summary.warnings)
    assert run([{"payment_date": "07.06.2026"}], dayfirst=False).findings == []
    explicit = run([{"payment_date": "07.06.2026"}], date_format="%d.%m.%Y")
    assert matches(explicit, "non_working_day") == [[0]]
    assert not any("belirsiz" in w for w in explicit.summary.warnings)


def test_typed_dates_and_money_ignore_text_locale():
    frame = pd.DataFrame(
        {
            "vendor_id": ["A", "A"],
            "invoice_no": ["X", "X"],
            "amount": [Decimal("12.500"), Decimal("12.5")],
            "payment_date": pd.to_datetime(["2026-06-07", "2026-06-08"]),
        }
    )
    result = run(frame, decimal_separator=",", date_format="%d.%m.%Y", dayfirst=False)
    assert matches(result, "exact_duplicate") == [[0, 1]]
    assert result.findings[0].evidence["amount"] == "12.500"
    assert matches(result, "non_working_day") == [[0]]
    assert not any("belirsiz" in w or "geçersiz" in w for w in result.summary.warnings)
    frame["amount"] = [12.5, 12.5]
    assert run(frame, decimal_separator=",").findings[0].evidence["amount"] == "12.5"


def test_turkish_amounts_and_ambiguous_separator():
    result = run(
        [
            {"vendor_id": "A", "invoice_no": "X", "amount": a}
            for a in ["1.234,56", "1234,56", "12.500", 12500]
        ],
        decimal_separator=",",
    )
    assert matches(result, "exact_duplicate") == [[0, 1], [2, 3]]
    assert not any("geçersiz" in w for w in result.summary.warnings)
    ambiguous = run([{"amount": "12.500"}])
    assert any("Belirsiz binlik" in w and "[0]" in w for w in ambiguous.summary.warnings)
    invalid = run([{"amount": "1.23,45"}], decimal_separator=",")
    assert any("geçersiz" in w for w in invalid.summary.warnings)
    assert any("geçersiz" in w for w in run([{"amount": "1e999999"}]).summary.warnings)


def test_invoice_segments_preserved_before_punctuation_removed():
    assert invoice("INV-001-05") == invoice("inv-1-5") == "INV|1|5"
    assert invoice("1-02") != invoice("10-2")
    assert invoice("INV 001 / 05") == invoice("INV-1-5")
    result = run(
        [
            {"vendor_id": "A", "amount": 217, "invoice_no": v}
            for v in ["INV-001-05", "inv-1-5", "1-02", "10-2"]
        ]
    )
    assert matches(result, "fuzzy_duplicate") == [[0, 1]]


def test_clusters_transitive_and_exact_only_exclusion():
    rows = [
        {"vendor_id": "A", "amount": 217, "invoice_no": inv, "payment_date": d}
        for inv, d in [
            ("A", "2026-06-01"),
            ("A", "2026-06-02"),
            ("B", "2026-06-04"),
            ("C", "2026-06-07"),
            ("D", "2026-06-11"),
        ]
    ]
    assert matches(run(rows), "fuzzy_duplicate") == [[0, 1, 2, 3]]
    assert matches(run(rows[:2]), "fuzzy_duplicate") == []
    assert matches(run(rows[:2]), "exact_duplicate") == [[0, 1]]


def test_sliding_clusters_match_small_brute_force_graph():
    rng = random.Random(713)
    for _ in range(150):
        rows = []
        for i in range(25):
            inv = rng.choice(["A", "B", "C", "INV-001", "INV 1", None])
            d = date(2026, 6, 1) + timedelta(days=rng.randrange(15))
            rows.append(
                {
                    "invoice_no": inv,
                    "normalized_invoice": invoice(inv),
                    "date": None if rng.random() < 0.2 else d,
                }
            )
        adjacency = {i: set() for i in range(len(rows))}
        for i, a in enumerate(rows):
            for j in range(i + 1, len(rows)):
                b = rows[j]
                if a["invoice_no"] and a["invoice_no"] == b["invoice_no"]:
                    continue
                normalized = a["normalized_invoice"] and (
                    a["normalized_invoice"] == b["normalized_invoice"]
                )
                nearby = a["date"] and b["date"] and abs((a["date"] - b["date"]).days) <= 3
                if normalized or nearby:
                    adjacency[i].add(j)
                    adjacency[j].add(i)
        seen, expected = set(), []
        for i in range(len(rows)):
            if i in seen:
                continue
            component, stack = set(), [i]
            while stack:
                v = stack.pop()
                if v not in component:
                    component.add(v)
                    stack.extend(adjacency[v] - component)
            seen.update(component)
            if len(component) > 1:
                expected.append(sorted(component))
        assert clusters(rows, list(range(len(rows))), 3) == expected


def test_dense_group_is_one_cluster_and_completes_without_pair_explosion():
    n = 10000
    frame = pd.DataFrame(
        {
            "vendor_id": ["A"] * n,
            "amount": [217] * n,
            "payment_date": pd.to_datetime(["2026-06-01"] * n),
            "invoice_no": [f"INV-{i}" for i in range(n)],
        }
    )
    start = perf_counter()
    result = run(frame)
    elapsed = perf_counter() - start
    assert matches(result, "fuzzy_duplicate") == [list(range(n))]
    assert result.summary.total_findings == 2  # cluster + Benford summary
    assert elapsed < 10  # generous CI guard; old all-pairs version takes >10s


def test_findings_cap_reports_exact_omissions_and_is_deterministic():
    rows = [{"created_by": "a", "approver": "A", "amount": 1000} for _ in range(10)]
    result = run(rows, max_findings=3)
    assert len(result.findings) == 3
    assert result.summary.truncated
    assert result.summary.omitted_by_rule == {"amount_pattern": 7, "segregation_of_duties": 10}
    assert any("17 bulgu" in w for w in result.summary.warnings)
    assert result == run(rows, max_findings=3)


def test_blank_currency_warns_and_uses_explicit_fallback():
    rows = [
        {"vendor_id": "A", "invoice_no": "X", "amount": 19, "currency": c}
        for c in ["", None, "TRY", "USD"]
    ]
    result = run(rows)
    assert matches(result, "exact_duplicate") == [[0, 1, 2]]
    assert any("Boş para birimi" in w and "[0, 1]" in w for w in result.summary.warnings)
    excluded = run(rows, default_currency=None)
    assert matches(excluded, "exact_duplicate") == []
    assert any("çıkarıldı" in w for w in excluded.summary.warnings)


def test_per_currency_threshold_and_unit():
    result = run(
        [{"amount": 9950, "currency": c} for c in ["TRY", "USD", "EUR"]],
        approval_threshold={"TRY": 10000, "USD": 20000},
        round_unit={"TRY": 1000, "USD": 3000},
    )
    assert matches(result, "amount_pattern") == [[0]]
    assert any("EUR" in w and "tanımsız" in w for w in result.summary.warnings)
    assert result.findings[0].evidence["approval_threshold"] == "10000"
    with pytest.raises(ValueError):
        RulesConfig(approval_threshold={"TRY": -1})
    with pytest.raises(ValueError):
        RulesConfig(round_unit={"TRY": 0})


def test_log_scale_avoids_skew_and_ignores_refunds():
    # Symmetric, broad log distribution: endpoints are not outliers on log scale.
    values = [10 ** (2 + z / 10) for z in range(-20, 21)]
    result = run([{"vendor_id": "A", "amount": a} for a in values + [-100000, 0]])
    assert matches(result, "vendor_outlier") == []
    planted = run([{"vendor_id": "A", "amount": a} for a in values + [1e12, -1e12]])
    assert matches(planted, "vendor_outlier") == [[len(values)]]
    outlier = next(f for f in planted.findings if f.rule_id == "vendor_outlier")
    assert outlier.evidence["scale"] == "log10"
    assert math.isfinite(outlier.evidence["robust_z"])


def test_zero_dispersion_relative_tolerance():
    rows = [{"vendor_id": "A", "amount": a} for a in [100] * 9 + [101, 120]]
    assert matches(run(rows), "vendor_outlier") == [[10]]
    assert matches(run(rows, outlier_relative_tolerance=0), "vendor_outlier") == [[9], [10]]


@pytest.mark.parametrize("creator,approver", [(" ali ", "ALI"), ("İpek", "ipek"), ("IŞIK", "ışık")])
def test_turkish_sod_keeps_original_evidence(creator, approver):
    result = run([{"created_by": creator, "approver": approver}])
    assert matches(result, "segregation_of_duties") == [[0]]
    assert result.findings[0].evidence == {"created_by": creator, "approver": approver}
    assert run([{"created_by": creator, "approver": "başkası"}]).findings == []


@pytest.mark.parametrize(
    "year,ramadan,sacrifice",
    [
        (2023, "04-21", "06-28"),
        (2024, "04-10", "06-16"),
        (2025, "03-30", "06-06"),
        (2026, "03-20", "05-27"),
        (2027, "03-09", "05-16"),
    ],
)
def test_religious_holidays_full_and_half_days(year, ramadan, sacrifice):
    calendar = json.loads(files("app.analytics").joinpath("holidays_tr.json").read_text())
    for start, duration in [(ramadan, 3), (sacrifice, 4)]:
        first = date.fromisoformat(f"{year}-{start}")
        for offset in range(duration):
            d = (first + timedelta(days=offset)).isoformat()
            assert d in calendar["full_days"]
            finding = run([{"payment_date": d}]).findings[0]
            assert finding.evidence["public_holiday"]
        eve = (first - timedelta(days=1)).isoformat()
        assert eve in calendar["half_days"]
        assert run([{"payment_date": eve}]).findings[0].evidence["half_day"]


def test_external_holiday_config(tmp_path):
    data = {
        "religious_years": [2030],
        "annual_full_days": [],
        "annual_half_days": [],
        "full_days": ["2030-06-03"],
        "half_days": [],
    }
    path = tmp_path / "calendar.json"
    path.write_text(json.dumps(data))
    assert matches(
        run([{"payment_date": "2030-06-03"}], holidays_path=str(path)), "non_working_day"
    ) == [[0]]
    assert not any(
        "kapsamıyor" in w
        for w in run([{"payment_date": "2030-06-03"}], holidays_path=str(path)).summary.warnings
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"rows": [{"a": 1}], "mapping": {"amonut": "a"}},
        {"rows": [{str(i): 1 for i in range(201)}], "mapping": {}},
        {"rows": [{str(i): 1} for i in range(201)], "mapping": {}},
        {"rows": [{"a": "x" * 1001}], "mapping": {}},
        {"rows": [{"a": "9" * 1001}], "mapping": {}},
        {"rows": [{"a" * 1001: 1}], "mapping": {}},
        {"rows": [], "mapping": {}, "config": {"holidays_path": "/etc/passwd"}},
    ],
)
def test_api_validation(payload):
    assert TestClient(create_app()).post("/analysis/run", json=payload).status_code == 422


def test_unknown_mapping_library_error():
    with pytest.raises(ValueError, match="Bilinmeyen"):
        run_rules(pd.DataFrame({"a": [1]}), {"amonut": "a"})


def test_body_size_rejected_before_json_parsing():
    client = TestClient(create_app())
    response = client.post(
        "/analysis/run",
        content=b"x" * (MAX_BODY_BYTES + 1),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413


def test_chunked_body_limit_without_content_length():
    async def scenario():
        called, messages = [], []

        async def app(scope, receive, send):
            called.append(True)

        chunks = iter(
            [
                {"type": "http.request", "body": b"1234", "more_body": True},
                {"type": "http.request", "body": b"5678", "more_body": False},
            ]
        )

        async def receive():
            return next(chunks)

        async def send(message):
            messages.append(message)

        await AnalysisBodyLimit(app, max_bytes=7)(
            {"type": "http", "method": "POST", "path": "/analysis/run", "headers": []},
            receive,
            send,
        )
        assert not called
        assert messages[0]["status"] == 413

    asyncio.run(scenario())


def test_sod_preserves_turkish_dotted_dotless_distinction():
    assert run([{"created_by": "İlker", "approver": "ılker"}]).findings == []


def test_api_accepts_limits_and_preserves_numeric_types():
    body = {
        "rows": [{"amount": 12.5, "created_by": "x" * 1000, "approver": "x" * 1000}],
        "mapping": {"amount": "amount", "created_by": "created_by", "approver": "approver"},
        "config": {"decimal_separator": ","},
    }
    response = TestClient(create_app()).post("/analysis/run", json=body)
    assert response.status_code == 200
    assert response.json()["summary"]["by_rule"]["segregation_of_duties"] == 1
    assert not any("geçersiz" in w for w in response.json()["summary"]["warnings"])


def test_zero_dispersion_tolerance_boundary_is_exact():
    rows = [{"vendor_id": "A", "amount": a} for a in [100] * 20 + [90, 110, 110.01]]
    assert matches(run(rows), "vendor_outlier") == [[22]]
