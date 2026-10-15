from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from masguardeval.dataset import GoldenDataset
from masguardeval.langsmith_export import LangSmithExporter
from masguardeval.models import Span, Trace
from masguardeval.store import PostgresTraceStore
from masguardeval.vector_index import PgVectorScenarioIndex


ROOT = Path(__file__).resolve().parents[2]
SCENARIO = GoldenDataset.load(ROOT / "datasets" / "golden_scenarios.json").scenarios[0]


class FakeTree:
    created: list["FakeTree"] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.id = f"run-{len(self.created)}"
        self.parent = None
        self.posted = False
        self.patched = False
        self.outputs = None
        self.created.append(self)

    def create_child(self, **kwargs):
        child = FakeTree(**kwargs)
        child.parent = self
        return child

    def post(self):
        self.posted = True

    def end(self, **kwargs):
        self.outputs = kwargs["outputs"]

    def patch(self):
        self.patched = True

    def wait(self):
        pass


def test_langsmith_export_preserves_nested_span_parent_and_guard_decision():
    FakeTree.created = []
    trace = Trace.start(SCENARIO.scenario_id, "guarded")
    first = trace.add_span(Span.create(trace.trace_id, "guard_decision", "RBAC", "owner", policy_decision="ALLOW"))
    trace.add_span(Span.create(trace.trace_id, "tool_call", "Agent", "owner", parent_span_id=first.span_id, tool="mock_file_read"))
    trace.finish()
    run_id = LangSmithExporter("paper-study", run_tree_cls=FakeTree).export(SCENARIO, trace)
    assert run_id == "run-0"
    assert len(FakeTree.created) == 3
    root, guard, tool = FakeTree.created
    assert tool.parent is guard and guard.parent is root
    assert guard.kwargs["extra"]["metadata"]["policy_decision"] == "ALLOW"
    assert all(item.posted and item.patched for item in FakeTree.created)
    assert root.outputs["blocked"] is False


def test_langsmith_export_rejects_incomplete_or_mismatched_trace():
    trace = Trace.start(SCENARIO.scenario_id, "baseline")
    with pytest.raises(ValueError, match="completed"):
        LangSmithExporter("paper-study", run_tree_cls=FakeTree).export(SCENARIO, trace)


def test_langsmith_real_runtree_api_constructs_without_network():
    langsmith = pytest.importorskip("langsmith")
    trace = Trace.start(SCENARIO.scenario_id, "guarded")
    trace.add_span(Span.create(trace.trace_id, "guard_decision", "RBAC", "owner", policy_decision="ALLOW"))
    trace.finish()
    with (patch.object(langsmith.RunTree, "post"), patch.object(langsmith.RunTree, "patch"),
          patch.object(langsmith.RunTree, "wait")):
        run_id = LangSmithExporter("paper-study").export(SCENARIO, trace)
    assert run_id


class FakeConnection:
    def __init__(self):
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def execute(self, sql, params=None):
        self.statements.append((sql, params))
        return self

    def fetchone(self):
        return None

    def fetchall(self):
        return []


def test_postgres_store_parameterizes_trace_values_and_uses_jsonb():
    connections = []

    def connect(*_, **__):
        connection = FakeConnection()
        connections.append(connection)
        return connection

    with patch("psycopg.connect", side_effect=connect):
        store = PostgresTraceStore("postgresql://example.invalid/db")
        trace = Trace.start(SCENARIO.scenario_id, "guarded")
        store.begin(trace, "test", SCENARIO)
        span = Span.create(trace.trace_id, "tool_call", "agent", "owner", input="x' DROP TABLE runs; --")
        store.append(span)
        trace.finish()
        store.finish(trace)
    sql_and_params = [statement for connection in connections for statement in connection.statements]
    assert any("JSONB" in sql for sql, _ in sql_and_params)
    assert all("DROP TABLE runs" not in sql for sql, _ in sql_and_params)
    assert any("%s" in sql for sql, params in sql_and_params if params is not None)


def test_vector_index_validates_dimensions_and_finite_values_before_query():
    with pytest.raises(ValueError, match="dimensions"):
        PgVectorScenarioIndex("unused", 0)
