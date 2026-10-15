import type { AgentToolGraph, Span, Trace } from "./types";

const colors: Record<string, string> = {
  tool_call: "#0b897c",
  blocked_tool_attempt: "#c84940",
  approval_required: "#c17a21",
  inter_agent_message: "#765ac0",
  control_flow: "#55748b",
  graph_transition: "#286eae",
};

export function AgentGraph({ graph, selectedSpanId, onSelect }: { graph: AgentToolGraph | null; selectedSpanId: string; onSelect: (id: string) => void }) {
  if (!graph) return <p>Graph unavailable for this trace.</p>;
  const agents = graph.nodes.filter(node => node.kind === "agent");
  const tools = graph.nodes.filter(node => node.kind === "tool");
  const graphNodes = graph.nodes.filter(node => node.kind === "graph_node");
  const interactionHeight = Math.max(agents.length, tools.length) * 78 + 65;
  const graphStartY = agents.length || tools.length ? interactionHeight + 35 : 52;
  const height = Math.max(240, graphStartY + Math.ceil(graphNodes.length / 3) * 90 + 35);
  const positions = new Map<string, { x: number; y: number }>();
  agents.forEach((node, index) => positions.set(node.id, { x: 145, y: 52 + index * 78 }));
  tools.forEach((node, index) => positions.set(node.id, { x: 575, y: 52 + index * 78 }));
  graphNodes.forEach((node, index) => positions.set(node.id, { x: 135 + (index % 3) * 225, y: graphStartY + Math.floor(index / 3) * 90 }));
  const labels = new Map(graph.nodes.map(node => [node.id, node.label]));
  return <div className="graphLayout">
    <div className="graphCanvas" role="img" aria-label="Observed agent, tool, and LangGraph execution graph">
      <svg viewBox={`0 0 720 ${height}`} width="100%" height={height}>
        <defs><marker id="edgeArrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8 Z" fill="#68818d" /></marker></defs>
        {graph.edges.map((edge, index) => {
          const from = positions.get(edge.source); const to = positions.get(edge.target);
          if (!from || !to) return null;
          const self = edge.source === edge.target;
          const d = self ? `M ${from.x + 72} ${from.y} C ${from.x + 180} ${from.y - 70}, ${from.x + 180} ${from.y + 70}, ${from.x + 72} ${from.y + 12}` : `M ${from.x + 72} ${from.y} C ${from.x + 150} ${from.y + (index % 5 - 2) * 8}, ${to.x - 150} ${to.y}, ${to.x - 78} ${to.y}`;
          return <path key={edge.id} d={d} fill="none" stroke={colors[edge.kind] ?? "#68818d"} strokeWidth={edge.span_id === selectedSpanId || edge.is_root_failure ? 3 : 1.8} opacity={edge.span_id === selectedSpanId ? 1 : 0.58} markerEnd="url(#edgeArrow)" onClick={() => onSelect(edge.span_id)} className="graphEdge" />;
        })}
        {graph.nodes.map(node => {
          const p = positions.get(node.id); if (!p) return null;
          return <g key={node.id} transform={`translate(${p.x - 72}, ${p.y - 23})`}><rect width="145" height="46" rx="10" fill={node.is_root_failure ? "#fff0ed" : node.kind === "agent" ? "#e7f5f2" : node.kind === "graph_node" ? "#e9f1fb" : node.policy === "blocked" ? "#fff0ed" : "#eef3f7"} stroke={node.is_root_failure ? "#c84940" : node.kind === "agent" ? "#50aaa0" : node.kind === "graph_node" ? "#7eaadb" : node.policy === "blocked" ? "#dc8076" : "#a8bdc8"} strokeWidth={node.is_root_failure ? 2.5 : 1} /><text x="72" y="20" textAnchor="middle" className="graphNodeLabel">{node.label.slice(0, 19)}</text><text x="72" y="36" textAnchor="middle" className="graphNodeSub">{node.is_root_failure ? "root failure" : node.kind === "tool" ? node.policy : node.kind === "graph_node" ? "graph node" : "agent"}</text></g>;
        })}
      </svg>
    </div>
    <div className="graphEvents"><strong>Observed edges · {graph.edges.length}</strong>{graph.edges.length === 0 && <p>No interaction was reached.</p>}{graph.edges.map(edge => <button key={edge.id} className={`graphEvent ${edge.span_id === selectedSpanId ? "selected" : ""}`} onClick={() => onSelect(edge.span_id)}><i style={{ background: colors[edge.kind] ?? "#68818d" }} /><span>{labels.get(edge.source) ?? edge.source} → {labels.get(edge.target) ?? edge.target}<small>{edge.kind.replaceAll("_", " ")}{edge.is_root_failure ? " · root failure" : edge.is_propagated_failure ? " · propagated" : ""}</small></span></button>)}</div>
  </div>;
}

export function InteractionTimeline({ trace, selectedSpanId, onSelect }: { trace: Trace; selectedSpanId: string; onSelect: (id: string) => void }) {
  const first = Date.parse(trace.started_at);
  return <div className="timeline" aria-label="Interaction timeline">{trace.spans.map((span: Span, index) => {
    const offset = Math.max(0, Date.parse(span.timestamp) - first);
    return <button key={span.span_id} onClick={() => onSelect(span.span_id)} className={`timelineItem ${span.span_id === selectedSpanId ? "selected" : ""} ${span.policy_decision === "BLOCK" ? "blocked" : ""}`}><span className="timelineDot">{index + 1}</span><strong>{span.agent}</strong><span>{span.span_type.replaceAll("_", " ")}{span.tool ? ` · ${span.tool}` : ""}</span><small>+{offset.toFixed(0)} ms · {span.latency_ms.toFixed(1)} ms{span.token_usage !== null ? ` · ${span.token_usage} tokens` : ""}</small></button>;
  })}</div>;
}
