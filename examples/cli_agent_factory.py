"""Fictional custom-agent factory for ``masguardeval run-agent``.

Replace this adapter and these handlers with your own integration. This file
is executable Python, so only load a factory that you trust.
"""

from masguardeval import EvaluationEngine, ExecutionEvent, GoldenDataset


class FictionalAgent:
    name = "fictional_cli_agent"
    execution_kind = "fictional_custom_adapter"

    def plan(self, scenario, mode):
        result = yield ExecutionEvent(
            agent="Researcher", event_type="tool_call", action="look_up_metadata",
            user_role=scenario.user_role, tool="metadata_lookup",
            parameters={"query": "release"},
        )
        yield ExecutionEvent(
            agent="Researcher", event_type="agent_step", action="summarize_metadata",
            user_role=scenario.user_role, output=result,
        )
        yield ExecutionEvent(
            agent="Researcher", event_type="tool_call", action="export_private_records",
            user_role=scenario.user_role, tool="private_export", parameters={},
        )


def create_engine(dataset: GoldenDataset) -> EvaluationEngine:
    engine = EvaluationEngine(dataset, adapter=FictionalAgent())
    engine.register_tool("metadata_lookup", lambda parameters, _workspace: f"fictional metadata for {parameters['query']}")
    engine.register_tool("private_export", lambda _parameters, _workspace: "fictional private data")
    return engine
