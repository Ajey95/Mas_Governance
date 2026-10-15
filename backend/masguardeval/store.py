from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Protocol

from .models import Scenario, Span, Trace


class RunStore(Protocol):
    def begin(self, trace: Trace, adapter: str, scenario: Scenario) -> None: ...
    def append(self, span: Span) -> None: ...
    def finish(self, trace: Trace) -> None: ...
    def get(self, trace_id: str) -> dict[str, Any] | None: ...
    def list(self, limit: int = 50) -> list[dict[str, Any]]: ...


class TraceStore:
    """Durable local run and span store. Each operation owns its SQLite connection."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    trace_id TEXT PRIMARY KEY,
                    scenario_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    adapter TEXT NOT NULL,
                    scenario_json TEXT,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    elapsed_ms REAL,
                    blocked INTEGER NOT NULL DEFAULT 0,
                    stop_reason TEXT,
                    final_response TEXT NOT NULL DEFAULT ''
                )
            """)
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(runs)")}
            if "scenario_json" not in columns:
                connection.execute("ALTER TABLE runs ADD COLUMN scenario_json TEXT")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS spans (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id TEXT NOT NULL REFERENCES runs(trace_id),
                    payload_json TEXT NOT NULL
                )
            """)
            connection.execute("CREATE INDEX IF NOT EXISTS idx_runs_started ON runs(started_at DESC)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_spans_trace ON spans(trace_id, sequence)")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def begin(self, trace: Trace, adapter: str, scenario: Scenario) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO runs(trace_id, scenario_id, mode, adapter, scenario_json, started_at) VALUES(?,?,?,?,?,?)",
                (trace.trace_id, trace.scenario_id, trace.mode, adapter, json.dumps(scenario.to_dict(), ensure_ascii=False), trace.started_at),
            )

    def append(self, span: Span) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO spans(trace_id, payload_json) VALUES(?,?)",
                (span.trace_id, json.dumps(span.to_dict(), ensure_ascii=False)),
            )

    def finish(self, trace: Trace) -> None:
        with self._connection() as connection:
            connection.execute(
                """UPDATE runs SET completed_at=?, elapsed_ms=?, blocked=?, stop_reason=?, final_response=?
                   WHERE trace_id=?""",
                (trace.completed_at, trace.elapsed_ms, int(trace.blocked), trace.stop_reason, trace.final_response, trace.trace_id),
            )

    def get(self, trace_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            run = connection.execute("SELECT * FROM runs WHERE trace_id=?", (trace_id,)).fetchone()
            if run is None:
                return None
            spans = connection.execute(
                "SELECT payload_json FROM spans WHERE trace_id=? ORDER BY sequence", (trace_id,),
            ).fetchall()
        return {
            "trace_id": run["trace_id"], "scenario_id": run["scenario_id"], "mode": run["mode"],
            "adapter": run["adapter"], "started_at": run["started_at"], "completed_at": run["completed_at"],
            "scenario": json.loads(run["scenario_json"]) if run["scenario_json"] else None,
            "elapsed_ms": run["elapsed_ms"], "blocked": bool(run["blocked"]),
            "stop_reason": run["stop_reason"], "final_response": run["final_response"],
            "spans": [json.loads(span["payload_json"]) for span in spans],
        }

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        if not 1 <= limit <= 200:
            raise ValueError("limit must be 1..200")
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT trace_id, scenario_id, mode, adapter, started_at, completed_at,
                          elapsed_ms, blocked, stop_reason
                   FROM runs ORDER BY started_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [{**dict(row), "blocked": bool(row["blocked"])} for row in rows]


class PostgresTraceStore:
    """PostgreSQL JSONB trace store with the same public contract as TraceStore."""

    def __init__(self, dsn: str, *, schema: str = "masguardeval") -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", schema):
            raise ValueError("Invalid PostgreSQL schema name")
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("Install backend[postgres] to use PostgreSQL storage") from exc
        self.dsn = dsn
        self.schema = schema
        self.runs_table = f"{schema}.masguardeval_runs"
        self.spans_table = f"{schema}.masguardeval_spans"
        self._psycopg = psycopg
        with self._connection() as connection:
            connection.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
            connection.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.runs_table} (
                    trace_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL DEFAULT 'research-preview',
                    scenario_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    adapter TEXT NOT NULL,
                    scenario_json JSONB NOT NULL,
                    started_at TIMESTAMPTZ NOT NULL,
                    completed_at TIMESTAMPTZ,
                    elapsed_ms DOUBLE PRECISION,
                    blocked BOOLEAN NOT NULL DEFAULT FALSE,
                    stop_reason TEXT,
                    final_response TEXT NOT NULL DEFAULT ''
                )
            """)
            connection.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.spans_table} (
                    sequence BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    trace_id TEXT NOT NULL REFERENCES {self.runs_table}(trace_id),
                    payload_json JSONB NOT NULL
                )
            """)
            connection.execute(f"CREATE INDEX IF NOT EXISTS idx_mge_runs_started ON {self.runs_table}(started_at DESC)")
            connection.execute(f"CREATE INDEX IF NOT EXISTS idx_mge_runs_owner_started ON {self.runs_table}(owner_id, started_at DESC)")
            connection.execute(f"CREATE INDEX IF NOT EXISTS idx_mge_spans_trace ON {self.spans_table}(trace_id, sequence)")
            connection.execute(f"ALTER TABLE {self.runs_table} ENABLE ROW LEVEL SECURITY")
            connection.execute(f"ALTER TABLE {self.spans_table} ENABLE ROW LEVEL SECURITY")

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        from psycopg.rows import dict_row

        with self._psycopg.connect(self.dsn, row_factory=dict_row) as connection:
            yield connection

    def begin(self, trace: Trace, adapter: str, scenario: Scenario,
              *, owner_id: str = "research-preview") -> None:
        from psycopg.types.json import Jsonb

        with self._connection() as connection:
            connection.execute(
                f"""INSERT INTO {self.runs_table}
                   (trace_id, owner_id, scenario_id, mode, adapter, scenario_json, started_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (trace.trace_id, owner_id, trace.scenario_id, trace.mode, adapter,
                 Jsonb(scenario.to_dict()), trace.started_at),
            )

    def append(self, span: Span, *, owner_id: str | None = None) -> None:
        from psycopg.types.json import Jsonb

        with self._connection() as connection:
            if owner_id is None:
                connection.execute(
                    f"INSERT INTO {self.spans_table} (trace_id, payload_json) VALUES (%s, %s)",
                    (span.trace_id, Jsonb(span.to_dict())),
                )
            else:
                cursor = connection.execute(
                    f"""INSERT INTO {self.spans_table} (trace_id, payload_json)
                    SELECT %s, %s WHERE EXISTS
                    (SELECT 1 FROM {self.runs_table} WHERE trace_id=%s AND owner_id=%s)""",
                    (span.trace_id, Jsonb(span.to_dict()), span.trace_id, owner_id),
                )
                if cursor.rowcount == 0:
                    raise PermissionError("Trace does not belong to this user")

    def finish(self, trace: Trace, *, owner_id: str | None = None) -> None:
        with self._connection() as connection:
            cursor = connection.execute(
                f"""UPDATE {self.runs_table} SET completed_at=%s, elapsed_ms=%s,
                   blocked=%s, stop_reason=%s, final_response=%s WHERE trace_id=%s"""
                + (" AND owner_id=%s" if owner_id is not None else ""),
                (trace.completed_at, trace.elapsed_ms, trace.blocked, trace.stop_reason,
                 trace.final_response, trace.trace_id) + ((owner_id,) if owner_id is not None else ()),
            )
            if owner_id is not None and cursor.rowcount == 0:
                raise PermissionError("Trace does not belong to this user")

    def get(self, trace_id: str, *, owner_id: str | None = None) -> dict[str, Any] | None:
        with self._connection() as connection:
            run = connection.execute(
                f"SELECT * FROM {self.runs_table} WHERE trace_id=%s"
                + (" AND owner_id=%s" if owner_id is not None else ""),
                (trace_id,) + ((owner_id,) if owner_id is not None else ()),
            ).fetchone()
            if run is None:
                return None
            spans = connection.execute(
                f"SELECT payload_json FROM {self.spans_table} WHERE trace_id=%s ORDER BY sequence", (trace_id,),
            ).fetchall()
        return {
            "trace_id": run["trace_id"], "scenario_id": run["scenario_id"], "mode": run["mode"],
            "adapter": run["adapter"], "started_at": run["started_at"].isoformat(),
            "completed_at": run["completed_at"].isoformat() if run["completed_at"] else None,
            "scenario": run["scenario_json"], "elapsed_ms": run["elapsed_ms"],
            "blocked": run["blocked"], "stop_reason": run["stop_reason"],
            "final_response": run["final_response"],
            "spans": [row["payload_json"] for row in spans],
        }

    def list(self, limit: int = 50, *, owner_id: str | None = None) -> list[dict[str, Any]]:
        if not 1 <= limit <= 200:
            raise ValueError("limit must be 1..200")
        with self._connection() as connection:
            rows = connection.execute(
                f"""SELECT trace_id, scenario_id, mode, adapter, started_at, completed_at,
                          elapsed_ms, blocked, stop_reason
                   FROM {self.runs_table} """
                + ("WHERE owner_id=%s " if owner_id is not None else "")
                + "ORDER BY started_at DESC LIMIT %s",
                ((owner_id,) if owner_id is not None else ()) + (limit,),
            ).fetchall()
        return [
            {**row, "started_at": row["started_at"].isoformat(),
             "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None}
            for row in rows
        ]


class ScopedPostgresTraceStore:
    """Bind every trace operation to one authenticated Supabase Auth user."""

    def __init__(self, store: PostgresTraceStore, owner_id: str) -> None:
        if not owner_id:
            raise ValueError("owner_id is required")
        self.store = store
        self.owner_id = owner_id

    def begin(self, trace: Trace, adapter: str, scenario: Scenario) -> None:
        self.store.begin(trace, adapter, scenario, owner_id=self.owner_id)

    def append(self, span: Span) -> None:
        self.store.append(span, owner_id=self.owner_id)

    def finish(self, trace: Trace) -> None:
        self.store.finish(trace, owner_id=self.owner_id)

    def get(self, trace_id: str) -> dict[str, Any] | None:
        return self.store.get(trace_id, owner_id=self.owner_id)

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.store.list(limit, owner_id=self.owner_id)
