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
        if event.tool and event.tool not in scenario.allowed_tools:
            return GuardDecision(PolicyDecision.BLOCK, self.name, f"{event.tool} is outside the allowlist")
        return GuardDecision(PolicyDecision.ALLOW, self.name, "tool is permitted")


class RBACGuard:
    name = "RBACGuard"

    def evaluate(self, scenario: Scenario, event: ExecutionEvent, recent_events: list[ExecutionEvent]) -> GuardDecision:
        sensitive = (
            event.tool in scenario.blocked_tools
            or event.tool in scenario.sensitive_tools
            or event.metadata.get("role_sensitive")
            or event.metadata.get("contains_sensitive_context")
        )
        if sensitive and scenario.user_role not in scenario.authorized_roles:
            return GuardDecision(
                PolicyDecision.BLOCK,
                self.name,
                f"{scenario.user_role} is not authorized for {event.tool}",
                metadata={"authorized_roles": scenario.authorized_roles},
            )
        return GuardDecision(PolicyDecision.ALLOW, self.name, "role is in scope for requested event")


class ABACGuard:
    name = "ABACGuard"

    def evaluate(self, scenario: Scenario, event: ExecutionEvent, recent_events: list[ExecutionEvent]) -> GuardDecision:
        rule = scenario.attribute_policies.get(event.tool or "")
        if not rule:
            return GuardDecision(PolicyDecision.ALLOW, self.name, "no attribute rule applies")
        subject = scenario.subject_attributes
        resource = event.metadata.get("resource_attributes", {})
        if not isinstance(resource, dict):
            return GuardDecision(PolicyDecision.BLOCK, self.name, "resource attributes are invalid")
        for key, expected in rule.get("subject", {}).items():
            if subject.get(key) != expected:
                return GuardDecision(PolicyDecision.BLOCK, self.name, f"subject attribute {key} does not match policy")
        for key, expected in rule.get("resource", {}).items():
            if resource.get(key) != expected:
                return GuardDecision(PolicyDecision.BLOCK, self.name, f"resource attribute {key} does not match policy")
        for key in rule.get("match", []):
            if not subject.get(key) or subject.get(key) != resource.get(key):
                return GuardDecision(PolicyDecision.BLOCK, self.name, f"subject and resource {key} do not match")
        return GuardDecision(PolicyDecision.ALLOW, self.name, "attribute policy permits event")


class ParameterValidator:
    name = "ParameterValidator"

    def evaluate(self, scenario: Scenario, event: ExecutionEvent, recent_events: list[ExecutionEvent]) -> GuardDecision:
        if not event.tool:
            return GuardDecision(PolicyDecision.ALLOW, self.name, "no tool parameters to validate")
        schema = scenario.parameter_schema.get(event.tool, {})
        if not schema:
            return GuardDecision(PolicyDecision.ALLOW, self.name, "no parameter schema registered")
        from .parameter_validation import parameter_issues
        issues = parameter_issues(schema, event.parameters)
        max_calls = schema.get("max_calls")
        call_limit_reached = max_calls is not None and sum(
            item.tool == event.tool for item in recent_events
        ) >= max_calls
        if any(issues.values()) or call_limit_reached:
            return GuardDecision(
                PolicyDecision.BLOCK,
                self.name,
                "invalid parameters",
                metadata={**issues, "call_limit_reached": call_limit_reached},
            )
        return GuardDecision(PolicyDecision.ALLOW, self.name, "parameters match schema")


class ContextSanitizer:
    name = "ContextSanitizer"

    def evaluate(self, scenario: Scenario, event: ExecutionEvent, recent_events: list[ExecutionEvent]) -> GuardDecision:
        if event.metadata.get("contains_sensitive_context") or event.metadata.get("context_polluted"):
            if event.event_type in {"tool_call", "memory_operation"}:
                return GuardDecision(PolicyDecision.BLOCK, self.name, "unsafe context cannot enter a tool or memory operation")
            sanitized = ExecutionEvent(
                agent=event.agent,
                event_type=event.event_type,
                action=event.action,
                user_role=event.user_role,
                tool=event.tool,
                parameters=event.parameters,
                input="[sanitized context]",
                output="[sanitized context]",
                metadata={**event.metadata, "sanitized": True},
            )
            return GuardDecision(PolicyDecision.MODIFY, self.name, "unsafe context was sanitized", sanitized)
        return GuardDecision(PolicyDecision.ALLOW, self.name, "context is clean")


class FailureIsolationGuard:
    name = "FailureIsolationGuard"

    def evaluate(self, scenario: Scenario, event: ExecutionEvent, recent_events: list[ExecutionEvent]) -> GuardDecision:
        if event.metadata.get("propagated_from") and any(
            item.metadata.get("failure_label") or item.metadata.get("propagated_from") for item in recent_events
        ):
            return GuardDecision(PolicyDecision.BLOCK, self.name, "upstream failure must be reviewed before propagation")
        return GuardDecision(PolicyDecision.ALLOW, self.name, "no upstream failure propagation detected")


class CoordinationGuard:
    name = "CoordinationGuard"

    def evaluate(self, scenario: Scenario, event: ExecutionEvent, recent_events: list[ExecutionEvent]) -> GuardDecision:
        decisions = {item.metadata.get("decision") for item in recent_events}
        if event.tool and {"allow_sensitive_action", "deny_sensitive_action"} <= decisions:
            return GuardDecision(PolicyDecision.BLOCK, self.name, "conflicting agent decisions require resolution")
        return GuardDecision(PolicyDecision.ALLOW, self.name, "no conflicting decision blocks this event")


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
        if event.metadata.get("high_risk") or event.tool in scenario.high_risk_tools:
            return GuardDecision(PolicyDecision.REQUIRE_APPROVAL, self.name, "high-risk action requires approval")
        return GuardDecision(PolicyDecision.ALLOW, self.name, "approval not required")


def default_guards() -> list[Guard]:
    return [
        FailureIsolationGuard(),
        CoordinationGuard(),
        RBACGuard(),
        ABACGuard(),
        ToolAllowlistGuard(),
        ParameterValidator(),
        ContextSanitizer(),
        LoopDetector(),
        HumanApprovalGate(),
    ]


def guard_profile(name: str) -> list[Guard]:
    """Named, reproducible internal comparators for matched experiments."""
    if name == "full":
        return default_guards()
    if name == "allowlist":
        return [ToolAllowlistGuard()]
    if name == "access_control":
        return [RBACGuard(), ABACGuard(), ToolAllowlistGuard(), ParameterValidator()]
    raise ValueError(f"Unknown guard profile: {name}")
