from uuid import UUID

import psycopg
from psycopg.rows import dict_row


class DatasetStore:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row, connect_timeout=5)

    def initialize(self):
        # Lazy, idempotent initialization also upgrades existing Compose volumes.
        with self.connect() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(64219028)")
            conn.execute("""CREATE TABLE IF NOT EXISTS datasets (
                id UUID PRIMARY KEY,
                name TEXT NOT NULL,
                sheet TEXT,
                row_count BIGINT NOT NULL CHECK (row_count >= 0),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )""")

    def insert(self, id: UUID, name: str, sheet: str | None, row_count: int):
        with self.connect() as conn:
            return conn.execute(
                "INSERT INTO datasets (id, name, sheet, row_count) VALUES (%s, %s, %s, %s) "
                "RETURNING *",
                (id, name, sheet, row_count),
            ).fetchone()

    def list(self):
        with self.connect() as conn:
            return conn.execute("SELECT * FROM datasets ORDER BY created_at DESC, id").fetchall()

    def get(self, id: UUID):
        with self.connect() as conn:
            return conn.execute("SELECT * FROM datasets WHERE id = %s", (id,)).fetchone()
