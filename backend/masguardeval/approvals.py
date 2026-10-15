from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Event, Lock
from uuid import uuid4

from .models import ExecutionEvent, Trace


@dataclass(frozen=True)
class ApprovalOutcome:
    approved: bool
    request_id: str
    status: str
    reason: str


@dataclass
class ApprovalRequest:
    request_id: str
    trace_id: str
    scenario_id: str
    agent: str
    tool: str | None
    parameters: dict[str, object]
    created_at: str
    status: str = "pending"
    reason: str | None = None
    resolved_at: str | None = None
    signal: Event = field(default_factory=Event, repr=False)

    def to_dict(self) -> dict[str, object]:
        return {
            "request_id": self.request_id, "trace_id": self.trace_id, "scenario_id": self.scenario_id,
            "agent": self.agent, "tool": self.tool, "parameters": self.parameters,
            "created_at": self.created_at, "status": self.status, "reason": self.reason,
            "resolved_at": self.resolved_at,
        }


class ApprovalBroker:
    """Keeps a running guarded session paused until an authenticated decision arrives."""

    def __init__(self, timeout_seconds: float = 60.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("approval timeout must be positive")
        self.timeout_seconds = timeout_seconds
        self._requests: dict[str, ApprovalRequest] = {}
        self._lock = Lock()

    def request(self, trace: Trace, event: ExecutionEvent) -> ApprovalOutcome:
        request = ApprovalRequest(
            request_id=str(uuid4()), trace_id=trace.trace_id, scenario_id=trace.scenario_id,
            agent=event.agent, tool=event.tool, parameters=dict(event.parameters),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._requests[request.request_id] = request
        if not request.signal.wait(self.timeout_seconds):
            with self._lock:
                if request.status == "pending":
                    request.status = "expired"
                    request.reason = "Approval request expired"
                    request.resolved_at = datetime.now(timezone.utc).isoformat()
        return ApprovalOutcome(request.status == "approved", request.request_id, request.status, request.reason or "No reason provided")

    def list(self, status: str | None = None) -> list[dict[str, object]]:
        with self._lock:
            requests = list(self._requests.values())
            return [request.to_dict() for request in requests if status is None or request.status == status]

    def decide(self, request_id: str, approve: bool, reason: str) -> dict[str, object]:
        with self._lock:
            request = self._requests.get(request_id)
            if request is None:
                raise KeyError(request_id)
            if request.status != "pending":
                raise ValueError(f"Approval is already {request.status}")
            request.status = "approved" if approve else "denied"
            request.reason = reason
            request.resolved_at = datetime.now(timezone.utc).isoformat()
            request.signal.set()
            return request.to_dict()
