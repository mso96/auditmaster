import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pandas as pd
import psycopg
import pytest
from app.config import get_settings
from app.datasets.profiling import preview, profile, read_table
from app.datasets.router import get_store
from app.datasets.store import DatasetStore
from app.main import create_app
from fastapi.testclient import TestClient

FIXTURES = Path(__file__).parent / "fixtures"


class MemoryStore:
    def __init__(self):
        self.rows = {}

    def insert(self, id, name, sheet, row_count):
        row = dict(id=id, name=name, sheet=sheet, row_count=row_count, created_at=datetime.now(UTC))
        self.rows[id] = row
        return row

    def list(self):
        return list(self.rows.values())

    def get(self, id):
        return self.rows.get(id)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    app = create_app()
    store = MemoryStore()
    app.dependency_overrides[get_store] = lambda: store
    with TestClient(app) as result:
        yield result
    get_settings.cache_clear()


@pytest.mark.parametrize(
    "values,kind,minimum,maximum,distinct,nulls",
    [
        (["1.234,56", "-2.345,67", "2.000", None], "number", -2345.67, 2000, 3, 1),
        (["12.50", 20.25, "12.50"], "number", 12.5, 20.25, 2, 0),
        (["31.12.2025", "01.01.2026", ""], "date", "2025-12-31", "2026-01-01", 2, 1),
        (["2026-04-23", "2026-04-24"], "date", "2026-04-23", "2026-04-24", 2, 0),
        (["Evet", "Hayır", "EVET", None], "boolean", None, None, 2, 1),
        ([True, False], "boolean", None, None, 2, 0),
        ([None, "", "  "], "text", None, None, 0, 3),
        (["1", "not-number"], "text", None, None, 2, 0),
        (["31.02.2026", "12.02.2026"], "text", None, None, 2, 0),
        (["NaN", "Infinity"], "text", None, None, 2, 0),
    ],
)
def test_inference(values, kind, minimum, maximum, distinct, nulls):
    column = profile(pd.DataFrame({"Sütun": values}))["columns"][0]
    assert {k: column[k] for k in ("type", "min", "max", "distinct_count", "null_count")} == {
        "type": kind,
        "min": minimum,
        "max": maximum,
        "distinct_count": distinct,
        "null_count": nulls,
    }


def test_text_top_five_and_preview_limit():
    frame = pd.DataFrame(
        {"Şehir": ["İzmir"] * 101 + ["Ankara", "Bursa", "Çorum", "Düzce", "Edirne"]}
    )
    assert profile(frame)["columns"][0]["top_values"] == [
        {"value": "İzmir", "count": 101},
        {"value": "Ankara", "count": 1},
        {"value": "Bursa", "count": 1},
        {"value": "Çorum", "count": 1},
        {"value": "Düzce", "count": 1},
    ]
    assert len(preview(frame)["rows"]) == 100


@pytest.mark.parametrize("filename", ["turkish.csv", "turkish_cp1254.csv", "payments.xlsx"])
def test_upload_profile_preview_and_disk(client, tmp_path, filename):
    content = (FIXTURES / filename).read_bytes()
    response = client.post("/datasets", files={"file": (filename, content)})
    assert response.status_code == 201, response.text
    dataset = response.json()
    assert dataset["name"] == filename
    assert dataset["row_count"] == 3
    assert dataset["sheet"] == ("Ödemeler" if filename.endswith("xlsx") else None)
    assert dataset["created_at"]
    assert client.get("/datasets").json() == [dataset]
    data = client.get(f"/datasets/{dataset['id']}/profile").json()
    assert data == {
        "row_count": 3,
        "columns": [
            {
                "name": "Tedarikçi",
                "type": "text",
                "null_count": 0,
                "distinct_count": 2,
                "min": None,
                "max": None,
                "top_values": [{"value": "Çağrı", "count": 2}, {"value": "Özgür", "count": 1}],
            },
            {
                "name": "Tutar",
                "type": "number",
                "null_count": 1,
                "distinct_count": 2,
                "min": 1234.56,
                "max": 2000,
                "top_values": [],
            },
            {
                "name": "Tarih",
                "type": "date",
                "null_count": 0,
                "distinct_count": 3,
                "min": "2026-04-23",
                "max": "2026-04-25",
                "top_values": [],
            },
            {
                "name": "Onay",
                "type": "boolean",
                "null_count": 0,
                "distinct_count": 2,
                "min": None,
                "max": None,
                "top_values": [],
            },
        ],
    }
    view = client.get(f"/datasets/{dataset['id']}/preview").json()
    assert view["columns"] == ["Tedarikçi", "Tutar", "Tarih", "Onay"]
    assert len(view["rows"]) == 3
    assert view["rows"][2]["Tutar"] is None
    assert view["rows"][0]["Tedarikçi"] == "Çağrı"
    assert (tmp_path / dataset["id"] / ("original" + Path(filename).suffix)).read_bytes() == content


def test_sheet_selection(client):
    response = client.post(
        "/datasets",
        files={"file": ("book.xlsx", (FIXTURES / "payments.xlsx").read_bytes())},
        data={"sheet": "İkinci"},
    )
    assert response.status_code == 201
    dataset = response.json()
    assert dataset["sheet"] == "İkinci"
    assert dataset["row_count"] == 1
    assert client.get(f"/datasets/{dataset['id']}/preview").json()["rows"] == [
        {"Kod": "001", "Tutar": "1.234,56"}
    ]


@pytest.mark.parametrize(
    "filename,content,sheet,status",
    [
        ("file.txt", b"a\n1", None, 415),
        ("file.csv", b"", None, 422),
        ("file.csv", b"a,a\n1,2", None, 422),
        ("file.csv", b"a;b\n1;2;3", None, 422),
        ("file.xlsx", b"not-excel", None, 422),
        ("file.csv", b"a\n1", "Sheet", 422),
        ("payments.xlsx", None, "Missing", 422),
    ],
)
def test_bad_upload_cleanup(client, tmp_path, filename, content, sheet, status):
    if content is None:
        content = (FIXTURES / filename).read_bytes()
    response = client.post(
        "/datasets", files={"file": (filename, content)}, data={"sheet": sheet} if sheet else {}
    )
    assert response.status_code == status
    assert client.get("/datasets").json() == []
    assert list(tmp_path.iterdir()) == []


def test_size_limit_and_boundary(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.datasets.router.MAX_BYTES", 5)
    assert client.post("/datasets", files={"file": ("a.csv", b"a\n1234")}).status_code == 413
    assert list(tmp_path.iterdir()) == []
    assert client.post("/datasets", files={"file": ("a.csv", b"a\n123")}).status_code == 201


def test_csv_delimiters_and_headers_only(client, tmp_path):
    frame, _ = read_table(FIXTURES / "comma.csv", ".csv")
    assert profile(frame)["columns"][1]["min"] == 12.5
    for separator in ["\t", "|"]:
        content = f"Ad{separator}Tutar\nŞule{separator}12,50".encode()
        assert client.post("/datasets", files={"file": ("a.csv", content)}).status_code == 201
    response = client.post("/datasets", files={"file": ("../header.csv", b"a;b\n")})
    assert response.status_code == 201
    assert response.json()["name"] == "header.csv"
    assert response.json()["row_count"] == 0
    assert client.get(f"/datasets/{response.json()['id']}/preview").json()["rows"] == []
    assert not (tmp_path.parent / "header.csv").exists()


def test_missing_dataset(client):
    assert client.get(f"/datasets/{uuid4()}/profile").status_code == 404
    assert client.get(f"/datasets/{uuid4()}/preview").status_code == 404
    assert client.get("/datasets/not-a-uuid/profile").status_code == 422


def test_postgres_persistence(tmp_path, monkeypatch):
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to run real Postgres integration (required in CI).")
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    ids = []
    try:
        with TestClient(create_app()) as client:
            for filename in ["turkish.csv", "payments.xlsx"]:
                response = client.post(
                    "/datasets", files={"file": (filename, (FIXTURES / filename).read_bytes())}
                )
                assert response.status_code == 201, response.text
                ids.append(response.json()["id"])
        # Fresh app and fresh DB connections, same persisted disk and metadata.
        with TestClient(create_app()) as client:
            assert set(ids) <= {item["id"] for item in client.get("/datasets").json()}
            for id in ids:
                assert client.get(f"/datasets/{id}/profile").json()["row_count"] == 3
                assert len(client.get(f"/datasets/{id}/preview").json()["rows"]) == 3
        store = DatasetStore(url)
        assert str(store.get(ids[0])["id"]) == ids[0]
    finally:
        if ids:
            with psycopg.connect(url) as conn:
                conn.execute("DELETE FROM datasets WHERE id = ANY(%s::uuid[])", (ids,))
        get_settings.cache_clear()


def test_database_insert_failure_cleans_files(client, tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise psycopg.OperationalError("unavailable")

    monkeypatch.setattr(MemoryStore, "insert", fail)
    # Dependency is mocked here, so the exception propagates to the test client.
    with pytest.raises(psycopg.OperationalError):
        client.post("/datasets", files={"file": ("data.csv", b"a\n1")})
    assert list(tmp_path.iterdir()) == []
    assert client.get("/datasets").json() == []


def test_delimiter_only_rows_are_not_discarded(client):
    response = client.post("/datasets", files={"file": ("nulls.csv", b"a;b\n1;2\n;\n3;4\n")})
    assert response.status_code == 201
    assert response.json()["row_count"] == 3
    result = client.get(f"/datasets/{response.json()['id']}/profile").json()
    assert [c["null_count"] for c in result["columns"]] == [1, 1]


def test_exact_numeric_distinct_and_typed_handoff():
    from decimal import Decimal

    from app.datasets.profiling import prepare_table

    frame = pd.DataFrame(
        {"amount": ["9007199254740992", "9007199254740993"], "date": ["07.06.2026", "13.06.2026"]}
    )
    typed, result = prepare_table(frame)
    assert result["columns"][0]["distinct_count"] == 2
    assert typed["amount"].tolist() == [Decimal("9007199254740992"), Decimal("9007199254740993")]
    assert typed["date"].iloc[0].isoformat() == "2026-06-07"
    assert any("belirsiz" in warning for warning in result["warnings"])


def test_shared_parsing_turkish_amounts_and_mixed_timezones():
    from app.datasets.profiling import prepare_table

    frame = pd.DataFrame(
        {
            "amount": ["1.234,56", "12.500"],
            "date": ["2026-06-07T00:30:00+03:00", "2026-06-07T23:30:00-04:00"],
        }
    )
    typed, result = prepare_table(frame)
    assert result["columns"][0]["min"] == 1234.56
    assert result["columns"][0]["max"] == 12500
    assert [v.isoformat() for v in typed["date"]] == ["2026-06-07", "2026-06-07"]


def test_cell_budget_rejects_and_cleans(client, monkeypatch, tmp_path):
    monkeypatch.setattr("app.datasets.profiling.MAX_CELLS", 3)
    response = client.post("/datasets", files={"file": ("wide.csv", b"a;b\n1;2\n")})
    assert response.status_code == 422
    assert list(tmp_path.iterdir()) == []


def test_nonfinite_json_bounds_are_safe(client):
    response = client.post("/datasets", files={"file": ("huge.csv", b"amount\n9e308\n")})
    assert response.status_code == 201
    result = client.get(f"/datasets/{response.json()['id']}/profile").json()
    assert result["columns"][0]["max"] == "9E+308"
