"""MASGuardEval framework package."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("masguardeval")
except PackageNotFoundError:
    __version__ = "0.1.2"

from .dataset import GoldenDataset
from .guards import (
    Guard,
    GuardDecision,
    ABACGuard,
    CoordinationGuard,
    ContextSanitizer,
    FailureIsolationGuard,
    HumanApprovalGate,
    LoopDetector,
    ParameterValidator,
    RBACGuard,
    ToolAllowlistGuard,
    default_guards,
    guard_profile,
)
from .metrics import MetricEngine
from .graph import AgentToolGraphBuilder
from .store import PostgresTraceStore, TraceStore
from .langsmith_export import LangSmithExporter
from .vector_index import PgVectorScenarioIndex
from .approvals import ApprovalBroker, ApprovalOutcome
from .live import LiveWorkspaceAdapter, ModelClient, ModelOutput, OllamaChatClient, OpenAIResponsesClient, SingleAgentWorkspaceAdapter
from .frameworks import (
    FrameworkSession, FrameworkToolBlocked, ToolSpec,
    make_autogen_tool, make_crewai_tool, make_langchain_tool, make_langgraph_tool_node,
)
from .langgraph_runtime import LangGraphRun, private_postgres_checkpointer, run_langgraph_graph
from .react_langgraph import run_model_react_langgraph
from .multiagent_langgraph import run_model_multiagent_langgraph
from .runner import EvaluationEngine
from .models import EvaluationResult, ExecutionEvent, MetricResult, PolicyDecision, Scenario, Span, Trace
from .evaluator import EvaluatorAgreement
from .experiments import ExperimentSuite
from .propagation import PropagationAnalyzer
from .scaling import BatchEvaluationExecutor

__all__ = [
    "__version__",
    "EvaluationResult",
    "ExecutionEvent",
    "MetricResult",
    "PolicyDecision",
    "Scenario",
    "Span",
    "Trace",
    "EvaluationEngine",
    "BatchEvaluationExecutor",
    "EvaluatorAgreement",
    "ExperimentSuite",
    "GoldenDataset",
    "Guard",
    "GuardDecision",
    "ABACGuard",
    "CoordinationGuard",
    "ContextSanitizer",
    "FailureIsolationGuard",
    "HumanApprovalGate",
    "LoopDetector",
    "MetricEngine",
    "AgentToolGraphBuilder",
    "TraceStore",
    "PostgresTraceStore",
    "LangSmithExporter",
    "PgVectorScenarioIndex",
    "ApprovalBroker",
    "ApprovalOutcome",
    "LiveWorkspaceAdapter",
    "FrameworkSession",
    "FrameworkToolBlocked",
    "ToolSpec",
    "make_autogen_tool",
    "make_crewai_tool",
    "make_langchain_tool",
    "make_langgraph_tool_node",
    "LangGraphRun",
    "run_langgraph_graph",
    "run_model_react_langgraph",
    "run_model_multiagent_langgraph",
    "private_postgres_checkpointer",
    "ModelClient",
    "ModelOutput",
    "OpenAIResponsesClient",
    "OllamaChatClient",
    "SingleAgentWorkspaceAdapter",
    "ParameterValidator",
    "PropagationAnalyzer",
    "RBACGuard",
    "ToolAllowlistGuard",
    "default_guards",
    "guard_profile",
]
