from __future__ import annotations

from dataclasses import dataclass, field

from .models import GRAPH_OBSERVATION_TYPES, Trace


@dataclass(frozen=True)
class PropagationAnalysis:
    trace_id: str
    root_span_ids: list[str]
    propagated_span_ids: list[str]
    edges: list[tuple[str, str]]
    paths: list[list[str]] = field(default_factory=list)
    longest_path_length: int = 0
    impact_score: float = 0.0
    dependency_edges: list[tuple[str, str]] = field(default_factory=list)
    failure_paths: list[list[str]] = field(default_factory=list)
    unlinked_propagation_span_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "trace_id": self.trace_id,
            "root_span_ids": self.root_span_ids,
            "propagated_span_ids": self.propagated_span_ids,
            "edges": [{"source": source, "target": target} for source, target in self.edges],
            "paths": self.paths,
            "longest_path_length": self.longest_path_length,
            "impact_score": round(self.impact_score, 4),
            "dependency_edges": [{"source": source, "target": target} for source, target in self.dependency_edges],
            "failure_paths": self.failure_paths,
            "unlinked_propagation_span_ids": self.unlinked_propagation_span_ids,
        }


class PropagationAnalyzer:
    """Keep structural ancestry separate from declared dependency evidence."""

    def analyze(self, trace: Trace) -> PropagationAnalysis:
        spans_by_id = {span.span_id: span for span in trace.spans}
        children: dict[str, list[str]] = {span.span_id: [] for span in trace.spans}
        edges: list[tuple[str, str]] = []
        dependency_edges: list[tuple[str, str]] = []
        dependency_children: dict[str, list[str]] = {span.span_id: [] for span in trace.spans}
        dependency_parent_by_target: dict[str, str] = {}

        positions = {span.span_id: index for index, span in enumerate(trace.spans)}
        for span in trace.spans:
            if span.parent_span_id and span.parent_span_id in spans_by_id:
                children.setdefault(span.parent_span_id, []).append(span.span_id)
                edges.append((span.parent_span_id, span.span_id))

            dependency_parent = span.metadata.get("causal_parent_span_id")
            if not dependency_parent and span.metadata.get("caused_by"):
                # Saved traces from before explicit span IDs used a declared
                # action reference plus a parent chain through guard spans.
                dependency_parent = span.parent_span_id
                while dependency_parent in spans_by_id and spans_by_id[dependency_parent].span_type == "guard_decision":
                    dependency_parent = spans_by_id[dependency_parent].parent_span_id
            if (span.span_type != "guard_decision" and isinstance(dependency_parent, str) and dependency_parent in positions
                    and positions[dependency_parent] < positions[span.span_id]):
                dependency_edges.append((dependency_parent, span.span_id))
                dependency_children[dependency_parent].append(span.span_id)
                dependency_parent_by_target[span.span_id] = dependency_parent

        failure_ids = {span.span_id for span in trace.spans
                       if span.failure_label and span.span_type not in GRAPH_OBSERVATION_TYPES | {"guard_decision"}}
        root_ids: list[str] = []
        propagated_ids: list[str] = []
        unlinked: list[str] = []
        for span in trace.spans:
            if span.span_id not in failure_ids:
                continue
            ancestor = dependency_parent_by_target.get(span.span_id)
            has_failure_ancestor = False
            while ancestor:
                if ancestor in failure_ids:
                    has_failure_ancestor = True
                    break
                ancestor = dependency_parent_by_target.get(ancestor)
            if has_failure_ancestor:
                propagated_ids.append(span.span_id)
            else:
                root_ids.append(span.span_id)
                if span.metadata.get("propagated_from") or span.failure_label == "cascading_failure":
                    unlinked.append(span.span_id)

        paths: list[list[str]] = []
        for root_id in root_ids:
            self._collect_paths(root_id, children, [root_id], paths)

        failure_paths: list[list[str]] = []
        for root_id in root_ids:
            self._collect_failure_paths(root_id, dependency_children, failure_ids, [root_id], failure_paths)

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
            dependency_edges=dependency_edges,
            failure_paths=failure_paths,
            unlinked_propagation_span_ids=unlinked,
        )

    def _collect_failure_paths(
        self, current_id: str, children: dict[str, list[str]], failures: set[str],
        path: list[str], paths: list[list[str]],
    ) -> None:
        for child_id in children.get(current_id, []):
            if child_id in path:
                continue
            candidate = [*path, child_id]
            if child_id in failures:
                paths.append(candidate)
            self._collect_failure_paths(child_id, children, failures, candidate, paths)

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
