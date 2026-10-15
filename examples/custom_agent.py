"""Use the core SDK with an agent adapter from another codebase."""

from masguardeval import EvaluationEngine, ExecutionEvent, GoldenDataset

from _common import DATASET, tool_specs, verify


class MyAgent:
    name = "external_custom_agent"

    def plan(self, scenario, mode):
        result = yield ExecutionEvent(
            agent="Researcher", event_type="tool_call", action="look_up_metadata",
            user_role=scenario.user_role, tool="metadata_lookup",
            parameters={"query": "release"},
        )
        yield ExecutionEvent(
            agent="Researcher", event_type="agent_step", action="use_tool_feedback",
            user_role=scenario.user_role, output=result,
        )
        yield ExecutionEvent(
            agent="Researcher", event_type="tool_call", action="export_private_records",
            user_role=scenario.user_role, tool="private_export", parameters={},
        )


def main() -> None:
    dataset = GoldenDataset.load(DATASET)
    reached: list[str] = []
    engine = EvaluationEngine(dataset, adapter=MyAgent())
    for spec in tool_specs(reached):
        engine.register_tool(spec.name, spec.handler)
    trace = engine.run_guarded(dataset.get("fictional_tool_boundary"))
    verify(trace, reached)


if __name__ == "__main__":
    main()
