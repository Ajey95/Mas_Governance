from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .models import ExecutionEvent, PolicyDecision, Scenario


@dataclass(frozen=True)
class GuardDecision:
    decision: PolicyDecision
    guard_name: str
    reason: str
    modified_event: ExecutionEvent | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class Guard(Protocol):
    name: str

    def evaluate(self, scenario: Scenario, event: ExecutionEvent, recent_events: list[ExecutionEvent]) -> GuardDecision:
        ...


class ToolAllowlistGuard:
    name = "ToolAllowlistGuard"

    def evaluate(self, scenario: Scenario, event: ExecutionEvent, recent_events: list[ExecutionEvent]) -> GuardDecision:
        if event.tool and event.tool in scenario.blocked_tools:
            return GuardDecision(PolicyDecision.BLOCK, self.name, f"{event.tool} is explicitly blocked")
        if event.tool and scenario.allowed_tools and event.tool not in scenario.allowed_tools:
            return GuardDecision(PolicyDecision.BLOCK, self.name, f"{event.tool} is outside the allowlist")
        return GuardDecision(PolicyDecision.ALLOW, self.name, "tool is permitted")


class RBACGuard:
    name = "RBACGuard"

    def evaluate(self, scenario: Scenario, event: ExecutionEvent, recent_events: list[ExecutionEvent]) -> GuardDecision:
        if event.tool in scenario.blocked_tools and scenario.user_role not in scenario.authorized_roles:
            return GuardDecision(
                PolicyDecision.BLOCK,
                self.name,
                f"{scenario.user_role} is not authorized for {event.tool}",
                metadata={"authorized_roles": scenario.authorized_roles},
            )
        return GuardDecision(PolicyDecision.ALLOW, self.name, "role is in scope for requested event")


class ParameterValidator:
    name = "ParameterValidator"

    def evaluate(self, scenario: Scenario, event: ExecutionEvent, recent_events: list[ExecutionEvent]) -> GuardDecision:
        if not event.tool:
            return GuardDecision(PolicyDecision.ALLOW, self.name, "no tool parameters to validate")
        schema = scenario.parameter_schema.get(event.tool, {})
        allowed_keys = set(schema.get("allowed_keys", []))
        required_keys = set(schema.get("required_keys", []))
        if not schema:
            return GuardDecision(PolicyDecision.ALLOW, self.name, "no parameter schema registered")
        actual_keys = set(event.parameters)
        extra_keys = actual_keys - allowed_keys
        missing_keys = required_keys - actual_keys
        if extra_keys or missing_keys:
            return GuardDecision(
                PolicyDecision.BLOCK,
                self.name,
                "invalid parameters",
                metadata={"extra_keys": sorted(extra_keys), "missing_keys": sorted(missing_keys)},
            )
        return GuardDecision(PolicyDecision.ALLOW, self.name, "parameters match schema")


class ContextSanitizer:
    name = "ContextSanitizer"

    def evaluate(self, scenario: Scenario, event: ExecutionEvent, recent_events: list[ExecutionEvent]) -> GuardDecision:
        if event.metadata.get("contains_sensitive_context") or event.metadata.get("context_polluted"):
            sanitized = ExecutionEvent(
                agent=event.agent,
                event_type=event.event_type,
                action=event.action,
                user_role=event.user_role,
                tool=event.tool,
                parameters=event.parameters,
                input=event.input,
                output="[sanitized context]",
                metadata={**event.metadata, "sanitized": True},
            )
            return GuardDecision(PolicyDecision.MODIFY, self.name, "unsafe context was sanitized", sanitized)
        return GuardDecision(PolicyDecision.ALLOW, self.name, "context is clean")


class LoopDetector:
    name = "LoopDetector"

    def __init__(self, max_repeated_actions: int = 3) -> None:
        self.max_repeated_actions = max_repeated_actions

    def evaluate(self, scenario: Scenario, event: ExecutionEvent, recent_events: list[ExecutionEvent]) -> GuardDecision:
        repeated = [
            item
            for item in recent_events[-self.max_repeated_actions :]
            if item.agent == event.agent and item.action == event.action and item.tool == event.tool
        ]
        if len(repeated) >= self.max_repeated_actions - 1:
            return GuardDecision(
                PolicyDecision.BLOCK,
                self.name,
                f"repeated action threshold {self.max_repeated_actions} reached",
            )
        return GuardDecision(PolicyDecision.ALLOW, self.name, "loop threshold not reached")


class HumanApprovalGate:
    name = "HumanApprovalGate"

    def evaluate(self, scenario: Scenario, event: ExecutionEvent, recent_events: list[ExecutionEvent]) -> GuardDecision:
        if event.metadata.get("high_risk"):
            return GuardDecision(PolicyDecision.REQUIRE_APPROVAL, self.name, "high-risk action requires approval")
        return GuardDecision(PolicyDecision.ALLOW, self.name, "approval not required")


def default_guards() -> list[Guard]:
    return [
        RBACGuard(),
        ToolAllowlistGuard(),
        ParameterValidator(),
        ContextSanitizer(),
        LoopDetector(),
        HumanApprovalGate(),
    ]
