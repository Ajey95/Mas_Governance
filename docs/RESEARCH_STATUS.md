# Research status and paper handoff

## What was built

The implementation covers the software workspace framework in the supplied plan and report: seven reference cases, 35 synthetic candidate task variants, eight trace metrics, baseline and guarded runs, guard middleware, a directed agent–tool graph, structured spans, SQLite trace storage, span streaming, a dashboard with timeline and graph, evidence-linked per-trace findings, report generation, ablations, propagation analysis, and Python SDK hooks. The model-driven single-agent and Planner–Executor–Reviewer adapters have run against a pinned local Ollama model as a pilot. A secondary three-provider model-judging council is implemented. On 2026-10-15, OpenAI, Gemini 2.5 Flash, and Groq each returned a response-ID-bearing, decisive vote on one masked fictional trial; the local ignored evidence is `reports/model_judgments/council_live_gemini25_2026-10-15.json`. This validates the three-provider call path on one row, not independent human outcome judgment or paper-grade council agreement. Gemini 3.8 Flash timed out on the same packet, so the tested default is Gemini 2.5 Flash. The CLI can resume a partial row by retrying missing providers without recalling successful ones.

Native LangChain `StructuredTool`, LangGraph `ToolNode`, AutoGen `FunctionTool`, and CrewAI `BaseTool` wrappers are implemented through `FrameworkSession`. LangGraph runtime tracing now records executed nodes, conditional routes, checkpoint IDs, and interrupts/resumes; graph observation spans do not change the eight research metric denominators. Private-schema PostgreSQL JSONB trace storage, a pgvector scenario index for caller-supplied embeddings, a private-schema LangGraph Postgres checkpointer, and explicit LangSmith run-tree export are also implemented. Local framework and checkpoint tests pass. The Supabase CLI created the Free-plan MASGuardEval project on 2026-10-15; live SQL verified the private schema, RLS, pgvector extension, and vector query. The Free-plan Render service formerly served the dashboard behind a shared preview gate and individual Supabase Auth accounts, persisting owner-scoped reference traces to Supabase. The current public site contains landing, docs, tutorials, examples, and method pages; the evaluation workbench runs on localhost. Deployed two-account tests verified separate run lists and 404s for cross-account trace, graph, and findings access. A bounded LangGraph reference workflow created a checkpoint and saved a trace through deployed API routes; a separate fictional pause/resume probe succeeded across fresh PostgreSQL connections, with cross-account reads also denied. An authenticated SSE run emitted 14 span events and a complete event. These are operational checks of fictional runs, not evidence of study outcomes. On 2026-10-15, a fictional trace was exported to LangSmith project `masguardeval-smoke`; remote readback confirmed root run `01a1401a-4ab6-74b2-a41e-894d5806c74c` and one child span. No private study trace was exported. See [Integrations](INTEGRATIONS.md) and [deployment status](DEPLOY_RENDER_SUPABASE.md).

A local `gemma4:latest` pilot recorded 14 baseline/guarded pairs across the seven reference cases and two architectures. A later trace audit found **one pair with adapter protocol errors in both modes** (`multi:data_001`), leaving 13 protocol-valid pairs; the original CLI had counted it as complete because the engine represented the error as a trace. The audited report is saved locally at `reports/ollama_reference_pilot_audited.json`, with the raw report preserved. The model digest is `c6eb396dbd5992bbe3f5cdb947e8bbc0ee413d7c17e2beaae69f5d569cf982eb`. Six guarded traces stopped at a guard; that is a trace observation, not a task-success or safety estimate. Twenty-eight condition-masked review records were prepared without labels. One trial per reference task is not a confirmatory study.

On 2026-10-15, an OpenAI `gpt-4.1-mini` service smoke completed two baseline/guarded pairs on the single `auth_001` reference case, one in each architecture. Both pairs were protocol-valid and the runner recorded provider response IDs; the ignored local report is `reports/openai_reference_smoke_2026-10-15.json`. This verifies the external model agent call path in the isolated mock workspace. It does not supply independent tasks, human labels, repeated trials, or an outcome estimate.

A separate matched `allowlist` profile pilot recorded 14 pairs on the same reference cases, model digest, and sampling settings; it has the same one protocol-invalid pair. The [tracked audited pilot summary](../reports/local_model_pilot_summary.json) records 5 allowlist stops versus 6 full-profile stops across all recorded pairs, with metric-score comparison limited to the 13 protocol-valid matched pairs. Audited secondary metric summaries also exclude the invalid pair. The calls were sampled separately; these figures do not establish a causal guard advantage or independently judged safety benefit. The project now has task-review/freeze, outcome-review/adjudication, held-out metric analysis, resumable pilot runs, and protocol-failure accounting. A 35-task draft claiming independent human authorship has been submitted and technically adapted, but its authorship and policies are not independently verified; no human outcome labels or frozen independent task set exists yet.

The reference adapter is deterministic. It emits fixed agent intentions rather than sampling an LLM. Its mock tools keep state in memory for one run. Baseline and guarded evaluations start from separate fresh workspaces. The runner records actual reached calls, guard decisions, returned mock results, measured local execution intervals, and why execution stopped.

The `candidate_scenarios.json` task set is generated from seven templates. Prompts and some parameters vary, but these 35 entries are **synthetic candidate tasks**, not independent ground truth or a validated golden benchmark. The dataset records `provenance: synthetic_candidate_unadjudicated` for every entry. The built-in API still loads the original seven reference cases by default. Neither set is a 500-episode empirical corpus.

A separate 35-slot **blank authoring packet** can be generated with `scripts/prepare_study.py intake`. Its `preflight` check screens draft completeness, runnable mock tools, exact fixture-prompt overlap, and risk/family coverage. A supplied 35-task draft has now been converted to a technically loadable review artifact with fictional case fixtures; see the [repair record](INCOMING_DATASET_REPAIR_2026-09-26.md). The supplied authorship declaration remains unverified and the agent-authored fixture/policy adaptation needs human review before the task set is frozen.

## What the included evidence can support

- Unit and API tests can show the reference runner blocks a risky intent before downstream effects.
- JSON traces can show which guard caused a stop and which mock actions actually ran.
- Per-metric scores can describe the seven included traces, when their denominators are applicable.
- Ablations can show differences among guard configurations on these same scripted cases.

These are software verification and illustrative experiment results. They are not independent agent performance estimates.

## Missing evidence for empirical submission

| Required study | Current state | Completion evidence |
| --- | --- | --- |
| Real multi-agent systems | One local Ollama pilot on seven reference tasks and one OpenAI service smoke on one reference task in both architectures; no repeated frozen-task study | Pin model/version, run matched adjudicated tasks in both modes, retain provider response IDs and environment details |
| Dataset breadth | Seven reference cases, 35 synthetic candidates, and a separate submitted 35-task technical draft pending review | Verify author/source provenance, review and adjudicate tasks and mock fixtures, freeze family-held-out tasks |
| Independent annotations | Included nine labels are synthetic examples; blank task and outcome review packets exist | Obtain consented, independently recorded expert labels with identities/roles and adjudication protocol |
| Metric construct validity | Eight formula implementations exist | Validate labels and denominators, show correlation with independently judged failures and known counterexamples |
| Threshold validity | Hard-coded exploratory values | Tune on development data and evaluate on held-out data |
| Statistical evidence | One local model pilot exists, including one audited protocol-invalid pair; repeated-run, resume, outcome reconciliation, and held-out analysis code exists | Run repeated model trials on frozen tasks and inspect uncertainty intervals, unadjusted tests, stratified failures |
| Baselines | Internal allowlist comparator piloted on reference fixtures; access-control profile implemented; no third-party guard system compared | Compare to unguarded system and credible independent guard products using matched tasks and tools if claiming superiority to existing systems |
| Generalization | One mock software workspace | Test different agents, tools, task types, and perturbations |
| Human diagnosis time | Not measured | Conduct a timed blinded analyst study if claiming time savings |

## Metric naming and interpretation

The public keys `CFP` and `DT` are kept for compatibility. `CFP` is the **observed share of root failures with a causally linked downstream failure in a trace**. It cannot be called a population probability without repeated sampled trials. `DT` is the normalized index of the first labelled failure or intervention. It is not elapsed analyst diagnosis time.

`TSP` becomes N/A when no tool is called. `TSR` becomes N/A when no required tools are defined. `PHR` becomes N/A without tool calls. `CPI` becomes N/A without context-bearing spans. `CFP` becomes N/A without a root failure. `RSS` becomes N/A without a sensitive action or blocked attempt. `CCR` becomes N/A with fewer than two decisions. `DT` becomes N/A without a labelled failure. Aggregate tables exclude N/A observations and show counts.

## Reproduction

Install Python 3.10+ and Node.js, then run from the repository root:

```powershell
python -m pip install -e backend
python -m pytest backend/tests -q
$env:PYTHONPATH = "backend"
python scripts/run_evaluation.py
python scripts/run_experiments.py
python scripts/run_evaluator_validation.py
cd frontend
npm install
npm run build
```

The reference reports contain UUIDs and wall-clock timestamps, so their raw JSON is not byte-for-byte stable. Scenario order, guard behavior, metric values, and report tables are deterministic. The evaluator agreement file carries its synthetic-label provenance.

## Paper claim guidance

Describe the current artifact as an evaluation framework with a tested mock-workspace proof of concept and a local model pilot. Do not claim the metric names or formulas are novel solely because they are implemented. A novelty claim needs a related-work comparison and a validated difference in construct or method. Do not claim real-world risk reduction, human expert agreement, or time saved from this reference run. Guarded traces use the actual stop reason as their final output; the expected behavior field is a rubric, never a generated agent answer.
