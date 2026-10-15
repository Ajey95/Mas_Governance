# Runnable SDK integrations

These examples use fictional data and local handlers. No LLM key, database,
email account, host shell command, or network service is used. Copy this folder
outside the repository after installing the wheel to verify that the public
package can be used from another codebase.

Install the package from the repository root:

```powershell
python -m pip install ./backend
python examples/custom_agent.py
masguardeval run-agent --dataset examples/fictional_scenarios.json --scenario fictional_tool_boundary --factory examples/cli_agent_factory.py:create_engine --out reports/my-agent.json
python -m pip install './backend[langchain,langgraph,autogen,crewai]'
python examples/langchain_agent.py
python examples/langgraph_agent.py
python examples/autogen_agent.py
python examples/crewai_agent.py
```

The custom example passes `ExecutionEvent` intents into `EvaluationEngine`.
Each framework example constructs that framework's native tool type from a
`FrameworkSession`. The LangGraph example compiles and runs a graph with a
guarded tool node. The other examples invoke native tools directly to check
their integration boundary; they do not run an LLM agent loop. Each prints a
trace ID after confirming an approved lookup reached its handler and a private
export did not. The example scenario is a synthetic teaching fixture, not a
validated study case.

In an application, give the agent only wrapped side-effecting tools. A direct
tool reference outside MASGuardEval bypasses the guard. Create a new session
for each run, and call `finish()` even when a guard blocks a call. See
[`docs/INTEGRATIONS.md`](../docs/INTEGRATIONS.md) for setup details and the
LangGraph runtime tracing/checkpoint path.
