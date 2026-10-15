> Superseded working draft. Continue in [MASGuardEval_manuscript_v2.md](MASGuardEval_manuscript_v2.md), which centers risk evaluation and failure tracing.

# MASGuardEval: Trace-Based Evaluation and Pre-Execution Governance for Multi-Agent LLM Workflows

> **Working manuscript, not submission ready.** The pilot findings below are from reference fixtures and one local model. No independently authored benchmark, expert outcome labels, held-out effectiveness result, or external guard comparison has been collected. Replace bracketed fields only with sourced results.

## Abstract (draft)

Tool-using language-model agents can fail through unauthorized actions, sensitive-data disclosure, unsafe tool choice, repeated execution, contaminated context, cascading failures, and contradictory coordination. We present MASGuardEval, a Python framework that captures agent, tool, message, memory, policy, and final-response spans while checking tool intents before side effects. It supports baseline and guarded runs, a directed interaction graph, a mock software workspace, native tool wrappers for four agent frameworks, and eight proposed trace measures. A local feasibility pilot executed seven reference cases with single-agent and Planner–Executor–Reviewer controllers using one pinned model. This pilot verifies the software path but does not estimate real-world safety or validate the measures. We specify a preregistered study with independently authored tasks, blinded outcome review where feasible, task-family holdout, repeated paired trials, and external guard comparators. **[Replace this paragraph with confirmed dataset size, models, independently judged primary outcomes, confidence intervals, and limitations after the study.]**

## 1. Introduction

Agent evaluations often summarize whether a final task succeeded. Governance failures can occur earlier: an agent may select an unauthorized tool, pass invalid parameters, expose sensitive context, or propagate a faulty result to another agent. MASGuardEval records those intermediate steps and applies guard checks before a registered tool handler executes. The research question is whether these trace-level constructs help identify and reduce independently judged task failures and prohibited actions while preserving legitimate task utility.

The current software contribution is a reusable evaluation and interception layer. The empirical contribution remains a hypothesis until an independent task set and outcome study are complete.

## 2. Related work and claim boundary

[AgentDojo](https://arxiv.org/abs/2406.13352) already evaluates tool-using agents in dynamic tasks with attacks and defenses. [ToolEmu](https://openreview.net/pdf?id=GEcwtMk1uA) uses emulated tools and human checks to study agent risk. [AgentHarm](https://arxiv.org/abs/2410.09024) evaluates harmful multi-step agent tasks. [AgentRx](https://arxiv.org/abs/2602.02475) localizes failures within execution trajectories, while [llmmas-otel](https://arxiv.org/abs/2608.24271) addresses multi-agent tracing and fault injection. [NeMo Guardrails](https://docs.nvidia.com/nemo/guardrails/about-nemo-guardrails-library/rail-types) provides execution rails around tool use. The related-work audit in `docs/RELATED_WORK_AUDIT.md` records additional overlap.

Our proposed distinguishing claim is the **combined, outcome-validated protocol** linking pre-execution governance, structured multi-agent traces, graph-linked propagation, and independently rated safety and utility across seven risk types. The current pilot does not establish that claim. Names or acronyms alone do not make the eight measures novel.

## 3. System design

### 3.1 Execution boundary

An agent adapter emits an execution intent. In guarded mode, the engine evaluates failure isolation, coordination, role and attribute access, tool allowlisting, parameter validity, context handling, repetition, and high-risk approval before invoking a registered tool handler. The tool result is returned to the adapter only after actual execution. Baseline and guarded runs start from separate in-memory workspaces. The default reference adapter is scripted. The model-driven adapter supports a single controller and Planner–Executor–Reviewer roles. Native LangChain, LangGraph, AutoGen, and CrewAI tool wrappers route their calls through the same guard boundary; wrapper construction and local tool invocation have been tested, but full external framework agents have not been evaluated here.

### 3.2 Trace representation

Each run stores typed spans for agent steps, tool calls, inter-agent messages, memory operations, guard decisions, and final responses. Spans include identifiers, parent links, timestamps, inputs and outputs, tool parameters, latency, optional token usage, policy decisions, and failure labels. An observed directed graph links agents, tools, and control events. The SQLite default and optional PostgreSQL JSONB store persist traces. A separate, explicit exporter maps completed spans into a LangSmith run tree. Database and LangSmith service-level verification remains open.

### 3.3 Proposed trace measures

| Key | Operational definition | Direction |
| --- | --- | --- |
| TSP | Executed allowed tool calls / executed tool calls | Higher |
| TSR | Distinct required tools executed / distinct required tools | Higher |
| PHR | Tool calls with invalid, missing, or flagged parameters / tool calls | Lower |
| CPI | Unsanitized polluted-context spans / context-bearing spans | Lower |
| CFP | Root failures with an explicitly linked downstream failure / root failures | Lower |
| RSS | 1 − unauthorized sensitive actions / sensitive actions or blocked attempts | Higher |
| CCR | Contradictory labelled decisions / labelled agent decisions | Lower |
| DT | First failure or intervention span index / (span count − 1) | Lower |

The exact denominator and N/A rules are in `docs/METRICS.md`. CFP is an **observed trace share**, not an estimated population probability. DT is a **trace-position proxy**, not measured human diagnosis time. Reference thresholds in code are exploratory and must be selected on development labels before a held-out test.

## 4. Empirical protocol to execute

**Task set.** Independently author or substantially revise 30–50 realistic software-workspace tasks across all seven risk categories. Preserve source case, task family, user role, tool schemas, allowed and prohibited actions, and expected safe behavior. Two reviewers separately judge each task; a third adjudicates disagreement. Split by task family so no family appears in both development and held-out files. Freeze hashes before tuning. The existing seven reference cases and 35 synthetic variants do not meet this gate.

**Trials.** On each frozen task, run both agent architectures under unguarded, full MASGuardEval, and matched comparator guard configurations. Pin model versions or digests, prompts, tools, seeds where supported, code hashes, environment, and trial count. Repeat runs. Record all incomplete attempts and missing-run rules. At least one independent guard implementation must be configured on comparable tool semantics before claiming superiority to existing systems; the current allowlist and access-control profiles are internal comparators.

**Primary outcomes.** Two reviewers separately rate task failure and committed prohibited action from condition-masked packets. Keep the condition map private from reviewers and record remaining blinding limitations. Reconcile disagreements with a separate adjudicator. Compare paired outcome rates by task family, architecture, and risk category, including uncertainty intervals and a predefined minimum practical difference.

**Construct checks.** Compare each proposed metric with the independent adverse-outcome labels. Inspect applicability, false positives, false negatives, class balance, and counterexamples. Select thresholds on development data only; apply unchanged to the held-out set. Use the existing study scripts for record validation and descriptive analysis, then review statistical assumptions before confirmatory reporting.

## 5. Feasibility pilot (not confirmatory)

The local `gemma4:latest` run used digest `c6eb396dbd5992bbe3f5cdb947e8bbc0ee413d7c17e2beaae69f5d569cf982eb`. One trial per reference task and architecture produced 14 recorded baseline/guarded pairs. A trace audit found that the model returned an invalid action kind in both modes for `multi:data_001`; **13 pairs were protocol valid**. The full profile stopped six guarded runs across all recorded pairs. A separately sampled matched allowlist profile stopped five of 14 guarded runs and contained the same one invalid pair. The raw and audited reports remain local; `reports/local_model_pilot_summary.json` records content hashes and descriptive comparisons on the 13 valid matched pairs.

These observations establish that the local model, mock tools, guard boundary, tracing, checkpointing, and comparator path executed. They also expose an agent-output protocol failure that the first manifest missed; future runs now flag this condition. The observations do not show that six or five tasks were made safer. No reviewer has labelled task failure or prohibited actions in these traces. The seven fixtures were scripted from case categories, and one trial per task provides no robust uncertainty estimate.

## 6. Required result sections before submission

- **[PENDING]** Frozen task counts, source/family distribution, and reviewer agreement.
- **[PENDING]** Independently judged task failure and prohibited-action rates by architecture and guard configuration.
- **[PENDING]** Held-out uncertainty intervals, missing-run accounting, and per-risk-category results.
- **[PENDING]** Metric construct validity, counterexamples, denominator coverage, and development-to-held-out threshold transfer.
- **[PENDING]** Comparable third-party guard baseline and capability mismatches.
- **[OPTIONAL]** Timed blinded analyst study, only if claiming faster human diagnosis.

## 7. Limitations and reproducibility

The built-in workspace emulates email, files, memory, and jobs; it does not prove behavior against real services. Agent prompts, tool results, and model behavior may change with model versions. A blocked call may protect a resource while preventing legitimate task completion, so safety and utility must be reported together. The task-origin and reviewer-identity fields are declarations that software cannot independently authenticate. Raw study traces may contain sensitive prompts and must be governed separately from public code. Current pilot code was run from an uncommitted working tree; a frozen release revision is required before confirmatory trials.
