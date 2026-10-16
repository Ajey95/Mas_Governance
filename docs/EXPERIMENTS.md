# Reproduce the reference experiments

From the repository root, install the backend and set its module path:

```powershell
python -m pip install -e backend
$env:PYTHONPATH = "backend"
python scripts/run_experiments.py
python scripts/run_evaluation.py
python scripts/run_propagation_analysis.py --scenario-id cascade_001
python scripts/run_scalability_batch.py --max-workers 2 --chunk-size 3
python scripts/run_evaluator_validation.py
```

These commands write files under `reports/`. They run scripted intents in a fresh mock workspace, not live LLM agents. The experiment report contains per-scenario RSS where applicable, aggregate metrics with sample counts, and guard ablations: no guards, RBAC only, full stack, and one-guard-removed variants. A blocked run stops before later scripted steps. Ablation figures are descriptive for these seven scenarios.

`run_evaluator_validation.py` demonstrates Cohen's kappa using `datasets/evaluator_annotations.json`. Those nine label pairs are **synthetic example labels**. The output includes `provenance` and must not be presented as human-versus-LLM agreement.

`run_propagation_analysis.py` reports structural parent-span links separately from declared `caused_by`/`causal_parent_span_id` dependencies. Only resolved dependency links support candidate failure-propagation paths; neither nesting nor event order proves causality. `run_scalability_batch.py` checks chunked local execution and shard manifests; it is not a performance benchmark for remote agents.

API equivalents: `GET /experiments`, `GET /dashboard`, `GET /propagation/{scenario_id}`, `GET /scalability/batch`, and `POST /evaluator/agreement`.

See [metric definitions](METRICS.md) and [research status](RESEARCH_STATUS.md) before using these outputs in a paper.

## Extended candidate and live study path

`python scripts/generate_candidate_dataset.py` writes 35 synthetic candidate tasks spanning the seven risk categories. Each has a concrete scripted event fixture so prompt and tool parameters can vary. These tasks are pilot material, not independently adjudicated ground truth.

`python scripts/run_live_experiment.py --model <pinned-model-id> --dataset datasets/candidate_scenarios.json --architectures single,multi --trials 3` runs baseline and guarded executions for each selected task using model-driven single- and multi-agent adapters. The runner executes only isolated mock workspace tools. It records model token usage, model call latency, guard spans, tool feedback, agent messages, and the observed graph. Install `backend[live]` and supply `OPENAI_API_KEY` for an external OpenAI run. For a local run, select `--provider ollama`; the CLI records the installed model digest, bounds each response, checkpoints each paired trial, and supports `--resume` for matching partial reports.

One local `gemma4:latest` pilot on the seven reference tasks recorded 14 pairs (single and multi architecture, one trial each). A trace audit found one pair with adapter protocol errors in both modes, leaving 13 protocol-valid pairs. The raw and audited pilot reports are kept as ignored local files in `reports/ollama_*.json` because they may contain prompts and model outputs. The full guard profile stopped six guarded runs across all recorded pairs, while the matched internal allowlist profile stopped five. These are intervention counts on reference fixtures, not independently judged task outcomes. `scripts/compare_guard_profiles.py` produces a descriptive matched table, excludes protocol-invalid pairs from metric-score differences, and refuses mismatched configurations. `scripts/audit_live_report.py` preserves raw reports while producing the audited copies.

Use [the study protocol](PAPER_STUDY_PROTOCOL.md) to prepare independent task reviews, freeze task-family splits, collect two outcome judgments per trace, and run held-out metric checks. A local model run cannot substitute for those steps.

The live manifest includes paired per-task results and scenario-clustered exploratory summaries. Each task's repeated-run mean is one analysis unit. The report gives mean guarded improvement, a percentile bootstrap interval across tasks, and an unadjusted two-sided sign-flip p-value. These exploratory statistics do not establish construct validity, solve multiple testing, or substitute for held-out tasks and independent expert labels.
