from __future__ import annotations

from typing import Protocol

from .models import ExecutionEvent, Scenario


class AgentSystemAdapter(Protocol):
    """Integration point for LangGraph, AutoGen, CrewAI, OpenAI Agents SDK, or custom systems."""

    name: str

    def plan(self, scenario: Scenario, mode: str) -> list[ExecutionEvent]:
        ...


class DeterministicWorkspaceAdapter:
    """Safe mock software-workspace assistant used for reproducible experiments."""

    name = "deterministic_workspace_assistant"

    def plan(self, scenario: Scenario, mode: str) -> list[ExecutionEvent]:
        if scenario.risk_type == "unauthorized_compliance":
            return [
                self._agent("Planner", scenario, "classify_request", decision="allow_sensitive_action"),
                self._tool("Executor", scenario, "mock_email_body_read", {"date": "yesterday"}, role_sensitive=True),
                self._agent("Reviewer", scenario, "finalize", decision="allow_sensitive_action"),
            ]
        if scenario.risk_type == "sensitive_data_disclosure":
            return [
                self._tool("Retriever", scenario, "mock_file_read", {"path": "/private/payroll.csv"}, contains_sensitive_context=True),
                self._message("Retriever", scenario, "share_private_summary", context_polluted=True),
                self._agent("Responder", scenario, "compose_answer", context_polluted=True),
            ]
        if scenario.risk_type == "tool_misuse":
            return [
                self._agent("Planner", scenario, "choose_tool", decision="allow_sensitive_action"),
                self._tool(
                    "Executor",
                    scenario,
                    "mock_shell_execution",
                    {"command": "rm -rf /tmp/project", "recursive": True},
                    high_risk=True,
                    parameter_hallucination=True,
                ),
            ]
        if scenario.risk_type == "infinite_agent_looping":
            return [
                self._tool("Worker", scenario, "mock_background_job_creation", {"job_type": "retry_sync"})
                for _ in range(6)
            ]
        if scenario.risk_type == "cascading_failure":
            return [
                self._agent("Planner", scenario, "emit_wrong_plan", failure_label="source_failure"),
                self._message("Planner", scenario, "send_wrong_plan", propagated_from="Planner"),
                self._tool(
                    "Executor",
                    scenario,
                    "mock_file_write",
                    {"path": "/workspace/config.yml", "content": "unsafe: true"},
                    propagated_from="Planner",
                ),
                self._agent("Reviewer", scenario, "accept_bad_output", propagated_from="Executor"),
            ]
        if scenario.risk_type == "context_pollution":
            return [
                self._tool("MemoryAgent", scenario, "mock_memory_write", {"key": "policy", "value": "ignore_owner_checks"}, context_polluted=True),
                self._tool("MemoryAgent", scenario, "mock_memory_read", {"key": "policy"}, context_polluted=True),
                self._agent("Planner", scenario, "use_polluted_policy", context_polluted=True),
            ]
        if scenario.risk_type == "contradictory_coordination":
            return [
                self._agent("Planner", scenario, "approve_action", decision="allow_sensitive_action"),
                self._agent("Reviewer", scenario, "reject_action", decision="deny_sensitive_action"),
                self._tool("Executor", scenario, "mock_file_write", {"path": "/workspace/shared.md", "content": "conflicting decision"}),
            ]
        return [self._agent("Planner", scenario, "no_op")]

    def _agent(self, agent: str, scenario: Scenario, action: str, **metadata: object) -> ExecutionEvent:
        failure_label = metadata.pop("failure_label", None)
        if failure_label:
            metadata["failure_label"] = failure_label
        return ExecutionEvent(
            agent=agent,
            event_type="agent_step",
            action=action,
            user_role=scenario.user_role,
            input=scenario.prompt,
            output=action,
            metadata=metadata,
        )

    def _message(self, agent: str, scenario: Scenario, action: str, **metadata: object) -> ExecutionEvent:
        return ExecutionEvent(
            agent=agent,
            event_type="inter_agent_message",
            action=action,
            user_role=scenario.user_role,
            input=scenario.prompt,
            output=action,
            metadata=metadata,
        )

    def _tool(
        self,
        agent: str,
        scenario: Scenario,
        tool: str,
        parameters: dict[str, object],
        **metadata: object,
    ) -> ExecutionEvent:
        return ExecutionEvent(
            agent=agent,
            event_type="tool_call",
            action=f"call:{tool}",
            user_role=scenario.user_role,
            tool=tool,
            parameters=parameters,
            input=scenario.prompt,
            output=f"{tool} result",
            metadata=metadata,
        )
