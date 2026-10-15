import { useEffect, useMemo, useState } from "react";
import type { AgentToolGraph, GraphEdge, GraphNode } from "./types";

type GraphGroup = { namespace: string; parent: string; owner: string; nodes: GraphNode[]; edges: GraphEdge[] };
const label = (name: string) => name === "__start__" ? "Start" : name === "__end__" ? "End" : name.replaceAll("_", " ");
const edgeName = (kind: string) => kind.replaceAll("_", " ");
const edgeTone = (edge: GraphEdge) => edge.decision === "BLOCK" || edge.is_root_failure ? "#ca6a49" : edge.is_propagated_failure ? "#c39548" : edge.kind === "graph_transition" ? "#738a88" : "#2e8a7d";

function groupsFor(graph: AgentToolGraph): GraphGroup[] {
  const graphNodes = graph.nodes.filter(node => node.kind === "graph_node");
  const namespaces = [...new Set(graphNodes.map(node => node.namespace ?? ""))];
  if (!namespaces.includes("")) namespaces.unshift("");
  return namespaces.map(namespace => {
    const nodes = graphNodes.filter(node => (node.namespace ?? "") === namespace);
    const ids = new Set(nodes.map(node => node.id));
    const cut = namespace.lastIndexOf("/");
    const part = namespace.slice(cut + 1);
    return { namespace, parent: cut >= 0 ? namespace.slice(0, cut) : "", owner: part.split(":")[0], nodes,
      edges: graph.edges.filter(edge => ids.has(edge.source) && ids.has(edge.target)) };
  });
}

function FlowLane({ group, selectedNodeId, selectedSpanId, onNode, onEdge, nestedRuns, isExpanded }: { group: GraphGroup; selectedNodeId: string; selectedSpanId: string; onNode: (id: string) => void; onEdge: (id: string) => void; nestedRuns: (node: GraphNode) => number; isExpanded: (id: string) => boolean }) {
  const width = Math.max(520, group.nodes.length * 170 + 30);
  const nodeIndex = new Map(group.nodes.map((node, index) => [node.id, index]));
  const pairs = new Map<string, { edge: GraphEdge; count: number }>();
  group.edges.forEach(edge => {
    const key = `${edge.source}|${edge.target}|${edge.kind}|${edge.decision}|${edge.is_root_failure}|${edge.is_propagated_failure}`;
    const found = pairs.get(key);
    if (found) found.count += 1; else pairs.set(key, { edge, count: 1 });
  });
  const routes = [...pairs.values()];
  const hasReturn = routes.some(({ edge }) => (nodeIndex.get(edge.target) ?? 0) <= (nodeIndex.get(edge.source) ?? 0));
  const height = hasReturn ? 230 : 175;
  return <div className="flowScroll"><div className="flowLane" style={{ width, height }}>
    <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} aria-hidden="true">
      <defs><marker id="graphArrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0 0 7 3.5 0 7" fill="#758985" /></marker></defs>
      {routes.map(({ edge, count }, routeIndex) => {
        const source = nodeIndex.get(edge.source); const target = nodeIndex.get(edge.target);
        if (source === undefined || target === undefined) return null;
        const x1 = 27 + source * 170 + 133, x2 = 27 + target * 170;
        const back = target <= source;
        const y = 88;
        const d = back ? `M ${x1 - 60} 112 C ${x1 - 60} ${170 + routeIndex % 3 * 14}, ${x2 + 70} ${170 + routeIndex % 3 * 14}, ${x2 + 70} 112` : `M ${x1} ${y} C ${x1 + 18} ${y - 12 - routeIndex % 3 * 8}, ${x2 - 18} ${y - 12 - routeIndex % 3 * 8}, ${x2 - 2} ${y}`;
        return <g key={`${edge.source}-${edge.target}-${edge.kind}-${routeIndex}`}><path d={d} fill="none" stroke={edgeTone(edge)} strokeWidth={edge.span_id === selectedSpanId ? 3 : 1.7} markerEnd="url(#graphArrow)" opacity={edge.span_id === selectedSpanId ? 1 : .8} /><title>{`${label(group.nodes[source].label)} → ${label(group.nodes[target].label)} · ${count} ${count === 1 ? "transition" : "transitions"}`}</title></g>;
      })}
    </svg>
    {group.nodes.map((node, index) => <button key={node.id} type="button" className={`flowNode ${node.id === selectedNodeId ? "selected" : ""} ${node.is_root_failure || node.policy === "blocked" ? "risk" : ""}`} style={{ left: 27 + index * 170 }} onClick={() => onNode(node.id)} aria-expanded={nestedRuns(node) ? isExpanded(node.id) : undefined}><small>{node.kind === "graph_node" ? "Graph node" : node.kind}</small><strong>{label(node.label)}</strong><span>{nestedRuns(node) ? `${nestedRuns(node)} nested runs · ` : ""}{group.edges.filter(edge => edge.source === node.id).length} outgoing</span></button>)}
  </div>{group.edges.length > 0 && <div className="routeList" aria-label="Observed graph transitions">{routes.map(({ edge, count }, index) => <button key={`${edge.id}-${index}`} className={edge.span_id === selectedSpanId ? "selected" : ""} onClick={() => onEdge(edge.span_id)}><span className="routeStroke" style={{ background: edgeTone(edge) }} /><strong>{label(group.nodes[nodeIndex.get(edge.source) ?? 0]?.label ?? edge.source)} → {label(group.nodes[nodeIndex.get(edge.target) ?? 0]?.label ?? edge.target)}</strong><small>{count}× · {edgeName(edge.kind)}{edge.decision ? ` · ${edge.decision}` : ""}{edge.is_root_failure ? " · root failure" : edge.is_propagated_failure ? " · propagated" : ""}</small></button>)}</div>}</div>;
}

export function AgentGraph({ graph, selectedSpanId, onSelect }: { graph: AgentToolGraph | null; selectedSpanId: string; onSelect: (id: string) => void }) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [selectedNodeId, setSelectedNodeId] = useState("");
  useEffect(() => { setExpanded(new Set()); setSelectedNodeId(""); }, [graph?.trace_id]);
  const groups = useMemo(() => graph ? groupsFor(graph) : [], [graph]);
  if (!graph) return <div className="blankState">No graph is available for this trace.</div>;
  const root = groups.find(group => group.namespace === "")!;
  const interactionNodes = graph.nodes.filter(node => node.kind !== "graph_node");
  const interactionIds = new Set(interactionNodes.map(node => node.id));
  const interactions: GraphGroup = { namespace: "interactions", parent: "", owner: "Agents and tools", nodes: interactionNodes,
    edges: graph.edges.filter(edge => interactionIds.has(edge.source) && interactionIds.has(edge.target)) };
  const chosen = graph.nodes.find(node => node.id === selectedNodeId);
  const related = chosen ? graph.edges.filter(edge => edge.source === chosen.id || edge.target === chosen.id) : [];
  const nestedCount = groups.filter(group => group.namespace !== "").length;
  const nestedRuns = (node: GraphNode) => node.kind === "graph_node" ? groups.filter(group => group.namespace !== "" && group.parent === (node.namespace ?? "") && group.owner === node.label).length : 0;

  function toggle(id: string) { setExpanded(current => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next; }); }
  function selectNode(node: GraphNode) {
    setSelectedNodeId(node.id);
    const children = node.kind === "graph_node" ? groups.filter(group => group.namespace !== "" && group.parent === (node.namespace ?? "") && group.owner === node.label) : [];
    if (children.length) toggle(node.id);
    const first = graph!.edges.find(edge => edge.source === node.id || edge.target === node.id);
    if (first) onSelect(first.span_id);
  }
  function renderChildren(parentNode: GraphNode, depth: number): React.ReactNode {
    if (depth > 8 || !expanded.has(parentNode.id)) return null;
    const children = groups.filter(group => group.namespace !== "" && group.parent === (parentNode.namespace ?? "") && group.owner === parentNode.label);
    return children.map((group, index) => <div className="nestedGroup" key={group.namespace} style={{ marginLeft: Math.min(depth * 14, 42) }}><div className="nestedHeader"><span className="fieldLabel">{label(parentNode.label)} / run {index + 1}</span><span>{group.edges.length} transitions · {group.nodes.length} nodes</span></div><FlowLane group={group} selectedNodeId={selectedNodeId} selectedSpanId={selectedSpanId} onNode={id => { const node = graph!.nodes.find(item => item.id === id); if (node) selectNode(node); }} onEdge={onSelect} nestedRuns={nestedRuns} isExpanded={id => expanded.has(id)} />{group.nodes.map(node => <div key={node.id}>{renderChildren(node, depth + 1)}</div>)}</div>);
  }
  const fallbackGroups = groups.filter(group => group.namespace !== "" && !groups.some(parent => parent.nodes.some(node => node.label === group.owner && (node.namespace ?? "") === group.parent)));
  return <div className="interactiveGraph"><div className="graphSummary"><div><strong>Observed execution graph</strong><span>{graph.nodes.length} nodes · {graph.edges.length} connections · {nestedCount} nested runs</span></div><div>{nestedCount > 0 && <><button onClick={() => setExpanded(new Set(graph.nodes.filter(node => nestedRuns(node) > 0).map(node => node.id)))}>Expand all</button><button onClick={() => setExpanded(new Set())}>Collapse all</button></>}</div></div>
    {root.nodes.length > 0 && <section className="graphSection"><div className="graphSectionTitle"><h3>Main route</h3><small>Select a node to inspect it. Nodes with nested runs expand on selection.</small></div><FlowLane group={root} selectedNodeId={selectedNodeId} selectedSpanId={selectedSpanId} onNode={id => { const node = graph.nodes.find(item => item.id === id); if (node) selectNode(node); }} onEdge={onSelect} nestedRuns={nestedRuns} isExpanded={id => expanded.has(id)} />{root.nodes.map(node => <div key={node.id}>{renderChildren(node, 1)}</div>)}{fallbackGroups.map(group => <div className="nestedGroup" key={group.namespace}><div className="nestedHeader"><span className="fieldLabel">{label(group.owner)}</span><span>{group.edges.length} transitions</span></div><FlowLane group={group} selectedNodeId={selectedNodeId} selectedSpanId={selectedSpanId} onNode={id => { const node = graph.nodes.find(item => item.id === id); if (node) selectNode(node); }} onEdge={onSelect} nestedRuns={nestedRuns} isExpanded={id => expanded.has(id)} /></div>)}</section>}
    {interactionNodes.length > 0 && <section className="graphSection"><div className="graphSectionTitle"><h3>Agent and tool interactions</h3><small>{interactions.edges.length} observed connections</small></div><FlowLane group={interactions} selectedNodeId={selectedNodeId} selectedSpanId={selectedSpanId} onNode={id => { const node = graph.nodes.find(item => item.id === id); if (node) selectNode(node); }} onEdge={onSelect} nestedRuns={nestedRuns} isExpanded={id => expanded.has(id)} /></section>}
    {chosen && <section className="graphNodeDetails"><span className="fieldLabel">Selected node</span><h3>{label(chosen.label)}</h3><p>{chosen.kind === "graph_node" ? "Graph step" : chosen.kind === "agent" ? "Agent" : "Tool"} · {related.length} observed connections{chosen.is_root_failure ? " · root failure" : ""}{chosen.policy ? ` · ${chosen.policy}` : ""}</p><div className="nodeConnections">{related.slice(0, 30).map(edge => <button key={edge.id} onClick={() => onSelect(edge.span_id)} className={edge.span_id === selectedSpanId ? "selected" : ""}><span className="routeStroke" style={{ background: edgeTone(edge) }} />{label(graph.nodes.find(node => node.id === edge.source)?.label ?? edge.source)} → {label(graph.nodes.find(node => node.id === edge.target)?.label ?? edge.target)} <small>{edgeName(edge.kind)}{edge.decision ? ` · ${edge.decision}` : ""}</small></button>)}{related.length > 30 && <small>{related.length - 30} more connections in this run</small>}</div></section>}
    {graph.nodes.length === 0 && <div className="blankState">No graph nodes were recorded.</div>}
  </div>;
}
