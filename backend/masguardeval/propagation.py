from __future__ import annotations

from dataclasses import dataclass, field

from .models import Trace


@dataclass(frozen=True)
class PropagationAnalysis:
    trace_id: str
    root_span_ids: list[str]
    propagated_span_ids: list[str]
    edges: list[tuple[str, str]]
    paths: list[list[str]] = field(default_factory=list)
    longest_path_length: int = 0
    impact_score: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "trace_id": self.trace_id,
            "root_span_ids": self.root_span_ids,
            "propagated_span_ids": self.propagated_span_ids,
            "edges": [{"source": source, "target": target} for source, target in self.edges],
            "paths": self.paths,
            "longest_path_length": self.longest_path_length,
            "impact_score": round(self.impact_score, 4),
        }


class PropagationAnalyzer:
    """Builds a rooted failure-propagation graph from parent spans and propagation metadata."""

    def analyze(self, trace: Trace) -> PropagationAnalysis:
        spans_by_id = {span.span_id: span for span in trace.spans}
        children: dict[str, list[str]] = {span.span_id: [] for span in trace.spans}
        edges: list[tuple[str, str]] = []
        previous_failure_id: str | None = None
        root_ids: list[str] = []
        propagated_ids: list[str] = []

        for span in trace.spans:
            if span.parent_span_id and span.parent_span_id in spans_by_id:
                children.setdefault(span.parent_span_id, []).append(span.span_id)
                edges.append((span.parent_span_id, span.span_id))

            if span.failure_label and not span.metadata.get("propagated_from") and span.failure_label != "cascading_failure":
                root_ids.append(span.span_id)
                previous_failure_id = span.span_id
                continue

            is_propagated = bool(span.metadata.get("propagated_from")) or span.failure_label == "cascading_failure"
            if is_propagated:
                propagated_ids.append(span.span_id)
                if previous_failure_id and (previous_failure_id, span.span_id) not in edges:
                    edges.append((previous_failure_id, span.span_id))
                    children.setdefault(previous_failure_id, []).append(span.span_id)
                previous_failure_id = span.span_id

        paths: list[list[str]] = []
        for root_id in root_ids:
            self._collect_paths(root_id, children, [root_id], paths)

        longest = max((len(path) for path in paths), default=0)
        impact = len(propagated_ids) / len(trace.spans) if trace.spans else 0.0
        return PropagationAnalysis(
            trace_id=trace.trace_id,
            root_span_ids=root_ids,
            propagated_span_ids=propagated_ids,
            edges=edges,
            paths=paths,
            longest_path_length=longest,
            impact_score=impact,
        )

    def _collect_paths(
        self,
        current_id: str,
        children: dict[str, list[str]],
        path: list[str],
        paths: list[list[str]],
    ) -> None:
        next_ids = children.get(current_id, [])
        if not next_ids:
            paths.append(path)
            return
        for child_id in next_ids:
            if child_id in path:
                paths.append(path + [child_id])
                continue
            self._collect_paths(child_id, children, path + [child_id], paths)

