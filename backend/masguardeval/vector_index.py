"""Optional pgvector index for externally computed scenario embeddings."""

from __future__ import annotations

import re
from math import isfinite
from typing import Any, Sequence


class PgVectorScenarioIndex:
    def __init__(self, dsn: str, dimensions: int, *, schema: str = "masguardeval") -> None:
        if not 1 <= dimensions <= 2000:
            raise ValueError("dimensions must be 1..2000")
        if not re.fullmatch(r"[a-z][a-z0-9_]*", schema):
            raise ValueError("Invalid PostgreSQL schema name")
        try:
            import psycopg
            from pgvector import Vector
            from pgvector.psycopg import register_vector
        except ImportError as exc:
            raise RuntimeError("Install backend[pgvector] to index scenario embeddings") from exc
        self.dsn = dsn
        self.schema = schema
        self.table = f"{schema}.masguardeval_scenario_vectors"
        self.dimensions = dimensions
        self._psycopg = psycopg
        self._vector = Vector
        self._register_vector = register_vector
        with self._psycopg.connect(self.dsn) as connection:
            extension = connection.execute("""SELECT n.nspname FROM pg_extension e
                JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='vector'""").fetchone()
            if extension is None:
                raise RuntimeError("Enable the pgvector extension in this database before creating the index")
            self.extension_schema = extension[0]
            if not re.fullmatch(r"[a-z][a-z0-9_]*", self.extension_schema):
                raise ValueError("Unsupported pgvector extension schema name")
        with self._connect() as connection:
            connection.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
            connection.execute(f"""CREATE TABLE IF NOT EXISTS {self.table} (
                scenario_id TEXT PRIMARY KEY, embedding {self.extension_schema}.vector({dimensions}) NOT NULL,
                embedding_model TEXT NOT NULL, scenario_text TEXT NOT NULL
            )""")
            existing = connection.execute(
                "SELECT atttypmod FROM pg_attribute WHERE attrelid=%s::regclass AND attname='embedding'",
                (self.table,),
            ).fetchone()
            if existing and existing[0] != dimensions:
                raise ValueError(f"Existing scenario vector table uses {existing[0]} dimensions, requested {dimensions}")
            connection.execute(f"ALTER TABLE {self.table} ENABLE ROW LEVEL SECURITY")

    def _connect(self) -> Any:
        connection = self._psycopg.connect(self.dsn)
        connection.execute("SELECT set_config('search_path', %s, false)",
                           (f"{self.schema},{self.extension_schema},public",))
        self._register_vector(connection)
        return connection

    def _embedding(self, values: Sequence[float]) -> list[float]:
        result = [float(value) for value in values]
        if len(result) != self.dimensions or not all(isfinite(value) for value in result):
            raise ValueError(f"embedding must contain {self.dimensions} finite values")
        return result

    def upsert(self, scenario_id: str, embedding: Sequence[float], *, embedding_model: str, scenario_text: str) -> None:
        if not scenario_id or not embedding_model:
            raise ValueError("scenario_id and embedding_model are required")
        vector = self._embedding(embedding)
        with self._connect() as connection:
            connection.execute(
                f"""INSERT INTO {self.table}
                   (scenario_id, embedding, embedding_model, scenario_text) VALUES (%s, %s, %s, %s)
                   ON CONFLICT (scenario_id) DO UPDATE SET embedding=EXCLUDED.embedding,
                   embedding_model=EXCLUDED.embedding_model, scenario_text=EXCLUDED.scenario_text""",
                (scenario_id, self._vector(vector), embedding_model, scenario_text),
            )

    def search(self, embedding: Sequence[float], *, embedding_model: str, limit: int = 10) -> list[dict[str, Any]]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be 1..100")
        vector = self._embedding(embedding)
        with self._connect() as connection:
            rows = connection.execute(
                f"""SELECT scenario_id, scenario_text, embedding_model,
                          embedding <=> %s AS cosine_distance
                   FROM {self.table} WHERE embedding_model=%s
                   ORDER BY embedding <=> %s LIMIT %s""",
                (self._vector(vector), embedding_model, self._vector(vector), limit),
            ).fetchall()
        return [
            {"scenario_id": row[0], "scenario_text": row[1],
             "embedding_model": row[2], "cosine_distance": float(row[3])}
            for row in rows
        ]
