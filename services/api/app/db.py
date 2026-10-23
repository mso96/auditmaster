import psycopg


def check_database(database_url: str) -> None:
    """Confirm Postgres is reachable and the pgvector extension is installed."""
    with psycopg.connect(database_url, connect_timeout=3) as conn:
        probe = conn.execute("SELECT 1").fetchone()
        if probe is None:
            raise RuntimeError("database probe failed")
        extension = conn.execute(
            "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()
        if extension is None:
            raise RuntimeError("pgvector extension is not installed")
