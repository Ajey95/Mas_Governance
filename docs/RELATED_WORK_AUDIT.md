# Related-work and novelty audit (25 September 2026)

This is a targeted primary-source audit for the planned MASGuardEval paper, not a systematic literature review. It identifies nearby work that makes a blanket claim of novel metrics, tracing, or tool guards unsafe. The paper should claim a specific, validated contribution only after comparing formulas, tasks, and outcomes against these sources and searching additional work.

| Work | Relevant existing contribution | Consequence for this paper |
| --- | --- | --- |
| [AgentDojo](https://arxiv.org/abs/2406.13352) | Dynamic tool-agent tasks and prompt-injection attacks/defenses across realistic application environments. | Compare task-success and attack/prohibited-action outcomes; do not call tool-agent safety evaluation itself new. |
| [ToolEmu](https://openreview.net/pdf?id=GEcwtMk1uA) | Emulated risky tool environments, evaluator results, and human validation of failures. | A mock workspace and risk-labelled tool traces alone are not a new experimental method. |
| [AgentHarm](https://arxiv.org/abs/2410.09024) | Harmful multi-step agent tasks and capability-aware harmfulness evaluation. | Distinguish governance failures in otherwise legitimate work from overt harmful-task completion. |
| [AgentRx](https://arxiv.org/abs/2602.02475) | Step-level failure localization from agent trajectories with auditable constraint evidence. | `DT` is currently only a trace-position proxy; it cannot imply faster or better human diagnosis. |
| [llmmas-otel](https://arxiv.org/abs/2608.24271) | Framework-agnostic distributed tracing and fault injection for software-engineering multi-agent systems. | Framework-agnostic tracing and fault injection require a concrete comparative novelty claim. |
| [Runtime Policy Enforcement for MCP-Based LLM Agents](https://www.mdpi.com/2079-9292/15/13/2829) | Pre-execution policy rules, label propagation, audit logging, and call/task error rates. | Tool allowlisting, policy violation rates, and trace-based detection are established constructs; compare exact formulas and intervention points. |
| [AgentTelemetry](https://doi.org/10.1145/3805760.3814931) | Loop/fault patterns in agent traces and an observability toolkit. | Loop and failure detection alone are not distinctive. |
| [NeMo Guardrails execution rails](https://docs.nvidia.com/nemo/guardrails/about-nemo-guardrails-library/rail-types) | Validation around tool calls and other LLM interaction stages. | Candidate independent guard stack for matched comparison on supported task types. Configuration and tool semantics must be matched and documented. |

## Defensible contribution to test

The strongest current hypothesis is that one paired evaluation protocol can join **pre-execution guard decisions, observed multi-agent and tool traces, graph-linked failure propagation, and independently validated task outcomes** across seven governance risk categories. The current repository implements the software mechanism; it has not validated this combined construct against independent outcomes or shown superiority to related tools.

The eight named metrics should be described as **proposed operationalizations**. Each needs a formula-by-formula comparison to prior constructs, counterexamples, denominator rules, inter-rater evidence, and held-out predictive validity. A new acronym is not evidence of a new metric. The model pilot and internal allowlist comparator are useful feasibility checks, not a literature-level novelty or effectiveness result.

## Comparator selection

1. Keep unguarded runs as the control and the implemented `allowlist`/`access_control` profiles as simple internal baselines.
2. Choose at least one independently maintained guard implementation whose tool boundary can be applied to the **same** frozen tasks and mocked tools. NeMo execution rails are a candidate; check configuration feasibility before preregistration.
3. Report task completion and prohibited-action rates from independent reviewers for every comparator. Trace metric movement without outcome judgments is not enough.
4. Match model digest/version, prompts, tool schemas, task order, trial count, and environment. Record any comparator capability mismatch instead of treating unsupported tasks as wins.
