"""Native framework tools backed by one MASGuardEval execution session.

Only pass the returned tools to an agent. Passing an original, unwrapped tool as
well would let that agent perform side effects outside the guard boundary.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from queue import Empty, Queue
from threading import Event, Lock, Thread
from typing import Any, Callable
from uuid import uuid4

from .approvals import ApprovalOutcome
from .dataset import GoldenDataset
from .graph import AgentToolGraphBuilder
from .models import ExecutionEvent, Scenario, Span, Trace
from .runner import EvaluationEngine
from .store import RunStore
from .workspace import MockWorkspace, ToolHandler


class FrameworkToolBlocked(RuntimeError):
    """A guard stopped a native framework tool before its handler ran."""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    handler: ToolHandler | None = None


@dataclass
class _Request:
    event: ExecutionEvent
    reply: Queue[tuple[bool, Any]]


class _BridgeAdapter:
    execution_kind = "external_framework"

    def __init__(self, framework_name: str) -> None:
        self.name = framework_name
        self.requests: Queue[_Request | None] = Queue()
        self.active: _Request | None = None
        self.final_answer: str | None = None

    def plan(self, scenario: Scenario, mode: str):
        while True:
            request = self.requests.get()
            if request is None:
                return
            self.active = request
            feedback = yield request.event
            request.reply.put((True, feedback))
            self.active = None

    def respond(self, scenario: Scenario, trace: Trace) -> str:
        if self.final_answer is not None:
            return self.final_answer
        return next((span.output for span in reversed(trace.spans) if span.span_type == "tool_call" and span.output), "No final answer recorded.")

    def fail_pending(self, error: BaseException) -> None:
        if self.active is not None:
            self.active.reply.put((False, error))
            self.active = None
        while True:
            try:
                request = self.requests.get_nowait()
            except Empty:
                break
            if request is not None:
                request.reply.put((False, error))


class FrameworkSession:
    """One baseline or guarded run shared by native tools in an external agent.

    The framework's tool callback blocks until the evaluation runner has applied
    guards and, if allowed, executed the registered handler exactly once.
    """

    def __init__(
        self, scenario: Scenario, *, mode: str = "guarded", framework_name: str = "external_framework",
        trace_store: RunStore | None = None,
        approval_handler: Callable[[Trace, ExecutionEvent], bool | ApprovalOutcome] | None = None,
        on_span: Callable[[Span], None] | None = None,
        max_events: int = 100,
    ) -> None:
        if mode not in {"baseline", "guarded"}:
            raise ValueError("mode must be baseline or guarded")
        if not 1 <= max_events <= 10_000:
            raise ValueError("max_events must be 1..10000")
        self.scenario = scenario
        self.mode = mode
        self.adapter = _BridgeAdapter(framework_name)
        self.engine = EvaluationEngine(GoldenDataset([scenario]), adapter=self.adapter,
                                       trace_store=trace_store, max_events=max_events)
        self.approval_handler = approval_handler
        self.on_span = on_span
        self.trace: Trace | None = None
        self.error: BaseException | None = None
        self._done = Event()
        self._submit_lock = Lock()
        self._started = False
        self._closed = False
        self._worker_thread: Thread | None = None

    def register_tool(self, spec: ToolSpec) -> None:
        if self._started:
            raise RuntimeError("Register tools before the first framework call")
        if spec.name not in set(self.scenario.allowed_tools) | set(self.scenario.blocked_tools):
            raise ValueError(f"Tool {spec.name} is not declared in scenario {self.scenario.scenario_id}")
        self.engine.register_tool(spec.name, spec.handler)

    def _start(self) -> None:
        if self._started:
            return
        self._started = True

        def run() -> None:
            try:
                if self.mode == "guarded":
                    self.trace = self.engine.run_guarded(self.scenario, on_span=self.on_span, approval_handler=self.approval_handler)
                else:
                    self.trace = self.engine.run_baseline(self.scenario, on_span=self.on_span)
            except BaseException as exc:
                self.error = exc
            finally:
                self._done.set()
                reason = FrameworkToolBlocked(self.trace.stop_reason or "Execution stopped") if self.trace and self.trace.blocked else self.error or RuntimeError("Framework session ended")
                self.adapter.fail_pending(reason)

        self._worker_thread = Thread(target=run, name=f"masguardeval-{self.scenario.scenario_id}", daemon=True)
        self._worker_thread.start()

    def _submit(self, event: ExecutionEvent) -> str | None:
        with self._submit_lock:
            if self._closed:
                raise RuntimeError("Framework session is closed")
            if self._done.is_set():
                raise FrameworkToolBlocked(self.trace.stop_reason or "Execution stopped") if self.trace and self.trace.blocked else RuntimeError("Framework session ended")
            self._start()
            request = _Request(event, Queue(maxsize=1))
            self.adapter.requests.put(request)
            ok, value = request.reply.get()
            if not ok:
                raise value
            return value

    def call(
        self, tool: str, parameters: dict[str, Any], *, agent: str = "ExternalAgent",
        caused_by: str | None = None, action_id: str | None = None,
    ) -> str:
        if not isinstance(parameters, dict):
            raise TypeError("tool parameters must be a dictionary")
        if action_id is not None and not action_id:
            raise ValueError("action_id must be nonempty")
        event = ExecutionEvent(
            agent=agent, event_type="tool_call", action=action_id or f"call:{tool}:{uuid4()}",
            user_role=self.scenario.user_role, tool=tool, parameters=parameters,
            input=self.scenario.prompt,
            metadata={
                "framework": self.adapter.name,
                "high_risk": tool in self.scenario.high_risk_tools,
                "role_sensitive": tool in self.scenario.sensitive_tools,
                "resource_attributes": self.scenario.resource_attributes.get(str(parameters.get("path", "")), {}),
                **({"caused_by": caused_by} if caused_by is not None else {}),
            },
        )
        return str(self._submit(event))

    async def acall(
        self, tool: str, parameters: dict[str, Any], *, agent: str = "ExternalAgent",
        caused_by: str | None = None, action_id: str | None = None,
    ) -> str:
        return await asyncio.to_thread(self.call, tool, parameters, agent=agent,
                                       caused_by=caused_by, action_id=action_id)

    def agent_step(
        self, agent: str, action: str, *, output: str = "", metadata: dict[str, Any] | None = None,
        caused_by: str | None = None,
    ) -> str:
        action_id = f"{action}:{uuid4()}"
        self._submit(ExecutionEvent(
            agent=agent, event_type="agent_step", action=action_id,
            user_role=self.scenario.user_role, input=self.scenario.prompt, output=output,
            metadata={"framework": self.adapter.name, **(metadata or {}),
                      **({"caused_by": caused_by} if caused_by is not None else {})},
        ))
        return action_id

    def message(self, sender: str, recipient: str, content: str, *, caused_by: str | None = None,
                metadata: dict[str, Any] | None = None) -> str:
        action_id = f"message:{uuid4()}"
        self._submit(ExecutionEvent(
            agent=sender, event_type="inter_agent_message", action=action_id,
            user_role=self.scenario.user_role, input=content, output=content,
            metadata={**(metadata or {}), "framework": self.adapter.name, "recipient": recipient,
                      **({"caused_by": caused_by} if caused_by is not None else {})},
        ))
        return action_id

    def observe_graph(self, event_type: str, name: str, *, metadata: dict[str, Any] | None = None) -> str:
        """Record runtime topology without evaluating it as another agent action."""
        from .models import GRAPH_OBSERVATION_TYPES

        if event_type not in GRAPH_OBSERVATION_TYPES:
            raise ValueError("Unsupported graph observation type")
        action = f"graph:{name}:{uuid4()}"
        self._submit(ExecutionEvent(
            agent=name, event_type=event_type, action=action,
            user_role=self.scenario.user_role,
            metadata={"framework": self.adapter.name, **(metadata or {})},
        ))
        return action

    def finish(self, final_answer: str | None = None) -> Trace:
        with self._submit_lock:
            if self._closed:
                if self.trace is None:
                    raise RuntimeError("Framework session closed without a trace")
                return self.trace
            self._closed = True
            self.adapter.final_answer = final_answer
            self._start()
            if not self._done.is_set():
                self.adapter.requests.put(None)
        self._done.wait()
        if self.error:
            raise self.error
        if self.trace is None:
            raise RuntimeError("Framework session ended without a trace")
        return self.trace

    def metrics(self) -> dict[str, object]:
        trace = self.finish()
        return {key: value.to_dict() for key, value in self.engine.compute_metrics(self.scenario, trace).items()}

    def graph(self) -> dict[str, Any]:
        return AgentToolGraphBuilder().build(self.scenario, self.finish())

    def __enter__(self) -> "FrameworkSession":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.finish()


def make_langchain_tool(session: FrameworkSession, spec: ToolSpec, *, agent: str = "LangChainAgent") -> Any:
    """Return a LangChain StructuredTool; use it with create_agent(..., tools=[...])."""
    try:
        from langchain_core.tools import StructuredTool
    except ImportError as exc:
        raise RuntimeError("Install backend[langchain] to use LangChain tools") from exc
    session.register_tool(spec)

    def invoke(parameters: dict[str, Any]) -> str:
        return session.call(spec.name, parameters, agent=agent)

    async def ainvoke(parameters: dict[str, Any]) -> str:
        return await session.acall(spec.name, parameters, agent=agent)

    return StructuredTool.from_function(func=invoke, coroutine=ainvoke, name=spec.name, description=spec.description)


def make_langgraph_tool_node(session: FrameworkSession, specs: list[ToolSpec], *, agent: str = "LangGraphAgent") -> Any:
    """Return a LangGraph ToolNode containing guarded LangChain tools."""
    try:
        from langgraph.prebuilt import ToolNode
    except ImportError as exc:
        raise RuntimeError("Install backend[langgraph] to use LangGraph ToolNode") from exc
    return ToolNode([make_langchain_tool(session, spec, agent=agent) for spec in specs])


def make_autogen_tool(session: FrameworkSession, spec: ToolSpec, *, agent: str = "AutoGenAgent") -> Any:
    """Return an AutoGen FunctionTool for AssistantAgent(tools=[...])."""
    try:
        from autogen_core.tools import FunctionTool
    except ImportError as exc:
        raise RuntimeError("Install backend[autogen] to use AutoGen tools") from exc
    session.register_tool(spec)

    async def invoke(parameters: dict[str, Any]) -> str:
        return await session.acall(spec.name, parameters, agent=agent)

    return FunctionTool(invoke, description=spec.description, name=spec.name)


def make_crewai_tool(session: FrameworkSession, spec: ToolSpec, *, agent: str = "CrewAIAgent") -> Any:
    """Return a CrewAI BaseTool for Agent(tools=[...])."""
    try:
        from crewai.tools import BaseTool
        from pydantic import BaseModel, PrivateAttr
    except ImportError as exc:
        raise RuntimeError("Install backend[crewai] to use CrewAI tools") from exc
    session.register_tool(spec)

    class GatewayInput(BaseModel):
        parameters: dict[str, Any]

    class GuardedCrewTool(BaseTool):
        name: str = spec.name
        description: str = spec.description
        args_schema: type[BaseModel] = GatewayInput
        _gateway_session: Any = PrivateAttr()

        def _run(self, parameters: dict[str, Any]) -> str:
            return self._gateway_session.call(spec.name, parameters, agent=agent)

        async def _arun(self, parameters: dict[str, Any]) -> str:
            return await self._gateway_session.acall(spec.name, parameters, agent=agent)

    tool = GuardedCrewTool()
    tool._gateway_session = session
    return tool
