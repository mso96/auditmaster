import math

import duckdb
import pandas as pd
import pytest
from app.analytics import run_rules
from app.main import create_app
from fastapi.testclient import TestClient


def run(rows, **config):
    frame = pd.DataFrame(rows)
    return run_rules(frame, {c: c for c in frame.columns}, config)


def matches(result, rule):
    return [f.row_indices for f in result.findings if f.rule_id == rule]


@pytest.fixture
def payments():
    # Each cluster has both a positive and a close negative.
    return pd.DataFrame(
        [
            ["A", "INV-001", 123, "TRY", "2026-06-01", "TR 01", "x", "y"],
            ["A", "INV-001", 123, "TRY", "2026-06-02", "TR01", "x", "y"],
            ["A", "INV 1", 123, "TRY", "2026-07-01", "TR02", "x", "y"],
            ["A", "other", 123, "USD", "2026-06-02", "TR03", "x", "y"],
            ["B", "b1", 217, "TRY", "2026-06-01", "TR01", "x", "x"],
            ["B", "b2", 217, "TRY", "2026-06-04", "TR04", None, None],
            ["B", "b3", 217, "TRY", "2026-07-01", "TR05", "x", "y"],
            ["C", "c1", 1000, "TRY", "2026-06-06", "TR06", "x", "y"],
            ["C", "c2", 9950, "TRY", "2026-03-20", "TR07", "x", "y"],
            ["C", "c3", 9899, "TRY", "2026-06-01", "TR08", "x", "y"],
        ],
        columns=[
            "vendor_id",
            "invoice_no",
            "amount",
            "currency",
            "payment_date",
            "iban",
            "created_by",
            "approver",
        ],
    )


def test_planted_matches_and_determinism(payments):
    mapping = {c: "customer_" + c for c in payments.columns}
    frame = payments.rename(columns=mapping)
    frame.index = [f"id-{i}" for i in range(len(frame))]
    result = run_rules(frame, mapping)
    expected = {
        "exact_duplicate": [[0, 1]],
        "fuzzy_duplicate": [[0, 1, 2], [4, 5]],
        "shared_iban": [[0, 1, 4]],
        "amount_pattern": [[7], [8]],
        "non_working_day": [[7], [8]],
        "segregation_of_duties": [[4]],
        "vendor_outlier": [],
        "benford": [],
    }
    assert {rule: matches(result, rule) for rule in expected} == expected
    assert result.summary.by_rule == {k: len(v) for k, v in expected.items()}
    assert result.summary.total_findings == 9
    assert result.summary.affected_rows == 7
    assert result.findings[0].row_ids == ["id-0", "id-1"]
    assert result == run_rules(frame, mapping)
    assert all(f.title and f.explanation and f.severity for f in result.findings)


@pytest.mark.parametrize(
    "amounts,expected,method",
    [
        ([100, 101, 102, 103, 104, 900], [[5]], "robust_z"),
        ([100, 100, 100, 100, 100, 900], [[5]], "iqr"),
        ([100, 101, 102, 103, 104], [], None),
        ([100, 100, 100, 100, 100], [], None),
    ],
)
def test_outlier(amounts, expected, method):
    result = run([dict(vendor_id="A", amount=a) for a in amounts])
    assert matches(result, "vendor_outlier") == expected
    if expected:
        assert (
            next(f for f in result.findings if f.rule_id == "vendor_outlier").evidence["method"]
            == method
        )


def test_outlier_small_groups_and_currency():
    result = run(
        [
            dict(vendor_id="A", currency="TRY" if i < 4 else "USD", amount=a)
            for i, a in enumerate([100, 100, 100, 100, 900])
        ]
    )
    assert matches(result, "vendor_outlier") == []


def test_benford_positive_negative_zero_and_fraction():
    assert matches(run([{"amount": 0.009} for _ in range(100)]), "benford") == [[]]
    natural = [
        {"amount": d} for d in range(1, 10) for _ in range(round(1000 * math.log10(1 + 1 / d)))
    ]
    assert matches(run(natural), "benford") == []
    assert matches(run([{"amount": a} for a in [0, -9, None] * 100]), "benford") == []
    assert matches(run([{"amount": 9}] * 99), "benford") == []
    assert (
        matches(run([{"amount": 9, "currency": str(i % 2)} for i in range(100)]), "benford") == []
    )


def test_threshold_boundaries():
    result = run(
        [{"amount": a} for a in [9900, 9999.99, 10000, 9899.99, 0, -1000]], round_unit=3000
    )
    assert matches(result, "amount_pattern") == [[0], [1]]


def test_holidays_and_half_days():
    rows = [
        {"payment_date": d}
        for d in [
            "2026-01-01",
            "2026-10-28",
            "2026-05-26",
            "2026-05-27",
            "2026-06-01",
            "2026-06-07",
        ]
    ]
    assert matches(run(rows), "non_working_day") == [[0], [1], [2], [3], [5]]
    assert matches(run(rows, flag_half_days=False), "non_working_day") == [[0], [3], [5]]
    assert matches(run(rows, extra_holidays=["2026-06-01"]), "non_working_day") == [
        [0],
        [1],
        [2],
        [3],
        [4],
        [5],
    ]
    assert any("2028" in w for w in run([{"payment_date": "2028-06-01"}]).summary.warnings)


def test_nulls_invalid_and_missing_mapping():
    result = run(
        [
            dict(
                vendor_id=None,
                invoice_no=None,
                amount="bad",
                payment_date="invalid",
                created_by=None,
                approver=None,
            )
        ]
        * 2
    )
    assert result.findings == []
    assert len(result.summary.warnings) == 3
    assert "shared_iban" in result.summary.skipped_rules
    with pytest.raises(ValueError, match="bulunamadı"):
        run_rules(pd.DataFrame({"a": [1]}), {"amount": "missing"})
    assert run_rules(pd.DataFrame(), {}).summary.total_rows == 0


def test_fuzzy_window_and_normalization():
    rows = [
        dict(vendor_name="A", amount=19, invoice_no=inv, payment_date=d)
        for inv, d in [
            ("0001", "2026-06-01"),
            ("001", "2026-08-01"),
            ("X", "2026-06-04"),
            ("Y", "2026-06-08"),
        ]
    ]
    assert matches(run(rows), "fuzzy_duplicate") == [[0, 1, 2]]
    assert matches(run(rows, fuzzy_days=0), "fuzzy_duplicate") == [[0, 1]]


def test_duckdb_parity(payments):
    mapping = {c: c for c in payments.columns}
    with duckdb.connect() as connection:
        relation = connection.from_df(payments)
        assert run_rules(relation, mapping) == run_rules(payments, mapping)


def test_endpoint_offline_and_validation(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Network/database access is forbidden")

    monkeypatch.setattr("socket.socket.connect", forbidden)
    monkeypatch.setattr("app.main.check_database", forbidden)
    client = TestClient(create_app())
    body = {
        "rows": [{"user": "Ali", "boss": "Ali", "id": "R1"}],
        "mapping": {"created_by": "user", "approver": "boss", "row_id": "id"},
    }
    response = client.post("/analysis/run", json=body)
    assert response.status_code == 200
    assert response.json()["findings"][0]["row_ids"] == ["R1"]
    assert response.json()["summary"]["total_findings"] == 1
    body["config"] = {"fuzzy_days": -1}
    assert client.post("/analysis/run", json=body).status_code == 422
    assert (
        client.post("/analysis/run", json={"rows": [], "mapping": {"amount": "a"}}).json()[
            "summary"
        ]["total_rows"]
        == 0
    )
    assert (
        client.post(
            "/analysis/run", json={"rows": [{"a": 1}], "mapping": {"amount": "b"}}
        ).status_code
        == 422
    )


def test_nonfinite_dates_and_amounts():
    result = run(
        [{"amount": "NaN", "payment_date": "NaT"}, {"amount": "Infinity", "payment_date": ""}]
    )
    assert result.findings == []
    assert any("payment_date" in w for w in result.summary.warnings)
    assert matches(run([{"amount": "1e30"}]), "amount_pattern") == [[0]]
