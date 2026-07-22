from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4


RiskType = Literal[
    "unauthorized_compliance",
    "sensitive_data_disclosure",
    "tool_misuse",
    "infinite_agent_looping",
    "cascading_failure",
    "context_pollution",
    "contradictory_coordination",
]

SpanType = Literal[
    "agent_step",
    "tool_call",
    "inter_agent_message",
    "memory_operation",
    "guard_decision",
    "final_response",
]


class PolicyDecision(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    MODIFY = "MODIFY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    LOG_ONLY = "LOG_ONLY"


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    source_case_study: str
    risk_type: RiskType
    user_role: str
    prompt: str
    expected_safe_behavior: str
    allowed_tools: list[str]
    blocked_tools: list[str]
    metrics: list[str]
    required_tools: list[str] = field(default_factory=list)
    authorized_roles: list[str] = field(default_factory=lambda: ["owner"])
    parameter_schema: dict[str, dict[str, Any]] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Scenario":
        return cls(
            scenario_id=str(payload["scenario_id"]),
            source_case_study=str(payload["source_case_study"]),
            risk_type=payload["risk_type"],
            user_role=str(payload["user_role"]),
            prompt=str(payload["prompt"]),
            expected_safe_behavior=str(payload["expected_safe_behavior"]),
            allowed_tools=list(payload.get("allowed_tools", [])),
            blocked_tools=list(payload.get("blocked_tools", [])),
            metrics=list(payload.get("metrics", [])),
            required_tools=list(payload.get("required_tools", payload.get("allowed_tools", []))),
            authorized_roles=list(payload.get("authorized_roles", ["owner"])),
            parameter_schema=dict(payload.get("parameter_schema", {})),
            tags=list(payload.get("tags", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "source_case_study": self.source_case_study,
            "risk_type": self.risk_type,
            "user_role": self.user_role,
            "prompt": self.prompt,
            "expected_safe_behavior": self.expected_safe_behavior,
            "allowed_tools": self.allowed_tools,
            "blocked_tools": self.blocked_tools,
            "required_tools": self.required_tools,
            "authorized_roles": self.authorized_roles,
            "parameter_schema": self.parameter_schema,
            "metrics": self.metrics,
            "tags": self.tags,
        }


@dataclass
class ExecutionEvent:
    agent: str
    event_type: SpanType
    action: str
    user_role: str
    tool: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    input: str | None = None
    output: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Span:
    span_id: str
    trace_id: str
    parent_span_id: str | None
    timestamp: str
    span_type: SpanType
    agent: str
    role: str
    input: str | None = None
    output: str | None = None
    tool: str | None = None
    tool_parameters: dict[str, Any] = field(default_factory=dict)
    policy_decision: str | None = None
    latency_ms: int = 0
    token_usage: int = 0
    failure_label: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        trace_id: str,
        span_type: SpanType,
        agent: str,
        role: str,
        *,
        parent_span_id: str | None = None,
        input: str | None = None,
        output: str | None = None,
        tool: str | None = None,
        tool_parameters: dict[str, Any] | None = None,
        policy_decision: str | None = None,
        latency_ms: int = 0,
        token_usage: int = 0,
        failure_label: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "Span":
        return cls(
            span_id=str(uuid4()),
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            span_type=span_type,
            agent=agent,
            role=role,
            input=input,
            output=output,
            tool=tool,
            tool_parameters=tool_parameters or {},
            policy_decision=policy_decision,
            latency_ms=latency_ms,
            token_usage=token_usage,
            failure_label=failure_label,
            metadata=metadata or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id,
            "timestamp": self.timestamp,
            "span_type": self.span_type,
            "agent": self.agent,
            "role": self.role,
            "input": self.input,
            "output": self.output,
            "tool": self.tool,
            "tool_parameters": self.tool_parameters,
            "policy_decision": self.policy_decision,
            "latency_ms": self.latency_ms,
            "token_usage": self.token_usage,
            "failure_label": self.failure_label,
            "metadata": self.metadata,
        }


@dataclass
class Trace:
    trace_id: str
    scenario_id: str
    mode: Literal["baseline", "guarded"]
    started_at: str
    spans: list[Span] = field(default_factory=list)
    final_response: str = ""
    blocked: bool = False

    @classmethod
    def start(cls, scenario_id: str, mode: Literal["baseline", "guarded"]) -> "Trace":
        return cls(
            trace_id=str(uuid4()),
            scenario_id=scenario_id,
            mode=mode,
            started_at=datetime.now(timezone.utc).isoformat(),
        )

    def add_span(self, span: Span) -> Span:
        self.spans.append(span)
        return span

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "scenario_id": self.scenario_id,
            "mode": self.mode,
            "started_at": self.started_at,
            "final_response": self.final_response,
            "blocked": self.blocked,
            "spans": [span.to_dict() for span in self.spans],
        }


@dataclass(frozen=True)
class MetricResult:
    key: str
    name: str
    score: float
    passed: bool
    threshold: float
    interpretation: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "score": round(self.score, 4),
            "passed": self.passed,
            "threshold": self.threshold,
            "interpretation": self.interpretation,
            "details": self.details,
        }


@dataclass
class EvaluationResult:
    scenario: Scenario
    baseline_trace: Trace
    guarded_trace: Trace
    baseline_metrics: dict[str, MetricResult]
    guarded_metrics: dict[str, MetricResult]
    recommendations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario.to_dict(),
            "baseline_trace": self.baseline_trace.to_dict(),
            "guarded_trace": self.guarded_trace.to_dict(),
            "baseline_metrics": {k: v.to_dict() for k, v in self.baseline_metrics.items()},
            "guarded_metrics": {k: v.to_dict() for k, v in self.guarded_metrics.items()},
            "risk_reduction": self.risk_reduction(),
            "recommendations": self.recommendations,
        }

    def risk_reduction(self) -> dict[str, float]:
        reduction: dict[str, float] = {}
        for key, baseline in self.baseline_metrics.items():
            guarded = self.guarded_metrics.get(key)
            if not guarded:
                continue
            if key in {"PHR", "CPI", "CFP", "CCR", "DT"}:
                reduction[key] = round(baseline.score - guarded.score, 4)
            else:
                reduction[key] = round(guarded.score - baseline.score, 4)
        return reduction
