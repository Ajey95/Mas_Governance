"""Run a bounded model-driven ReAct graph against a local Ollama model.

Install ``backend[langgraph]`` and start Ollama with the selected model first.
The tools operate only on the scenario's fictional mock workspace.
"""

import argparse
import json
from pathlib import Path

from masguardeval import (GoldenDataset, OllamaChatClient, TraceStore,
                         run_model_multiagent_langgraph, run_model_react_langgraph)


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="Installed local Ollama model name")
    parser.add_argument("--scenario", default="auth_001")
    parser.add_argument("--max-steps", type=int, default=4)
    parser.add_argument("--team", action="store_true", help="Use nested Planner, Executor, Reviewer graphs")
    parser.add_argument("--max-rounds", type=int, default=2)
    args = parser.parse_args()
    scenario = GoldenDataset.load(ROOT / "datasets" / "golden_scenarios.json").get(args.scenario)
    client = OllamaChatClient(args.model)
    client.model_metadata()  # Fail early if the model is not installed locally.
    store = TraceStore(ROOT / "reports" / "runs.sqlite3")
    if args.team:
        run = run_model_multiagent_langgraph(
            scenario, client, model_name=args.model, max_rounds=args.max_rounds,
            max_tool_calls_per_round=args.max_steps, trace_store=store)
    else:
        run = run_model_react_langgraph(scenario, client, model_name=args.model,
                                        max_steps=args.max_steps, trace_store=store)
    print(json.dumps({"trace_id": run.trace.trace_id, "blocked": run.trace.blocked,
                      "steps": run.state.get("step") if isinstance(run.state, dict) else None,
                      "final_response": run.trace.final_response}, indent=2))
    print("Inspect this trace in the local dashboard at http://127.0.0.1:8000")


if __name__ == "__main__":
    main()
