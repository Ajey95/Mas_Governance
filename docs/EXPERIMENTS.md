# Experiments

Use this guide when you need reproducible research artifacts beyond the live dashboard.

## Broad Scenario Run

Run all golden scenarios and generate scenario-level, metric-level, and ablation tables:

```powershell
$env:PYTHONPATH="backend"
py -3.11 scripts\run_experiments.py
```

Outputs:

```text
reports/experiment_report.json
reports/experiment_report.md
```

The Markdown report includes:

- Scenario results with baseline RSS, guarded RSS, and RSS delta.
- Aggregate metric table across all scenarios.
- Guard ablation table for `no_guards`, `rbac_only`, and `full_guard_stack`.

## Guard Ablation

The ablation runner compares guard stacks under the same dataset and deterministic adapter:

| Stack | Meaning |
| --- | --- |
| `no_guards` | Guarded path with guard middleware disabled. |
| `rbac_only` | Only role-boundary protection enabled. |
| `full_guard_stack` | RBAC, tool allowlist, parameter validation, context sanitizer, loop detector, and approval gate. |

This makes mitigation contribution measurable instead of only visually comparing one guarded run.

## Evaluator Validation

Compute Cohen's Kappa between human expert labels and LLM-judge labels:

```powershell
$env:PYTHONPATH="backend"
py -3.11 scripts\run_evaluator_validation.py
```

Outputs:

```text
reports/evaluator_agreement.json
```

The implementation lives in `backend/masguardeval/evaluator.py` and returns observed agreement, expected agreement, Cohen's Kappa, and a confusion table.

## Failure Propagation

Analyze rooted failure paths for a trace:

```powershell
$env:PYTHONPATH="backend"
py -3.11 scripts\run_propagation_analysis.py --scenario-id cascade_001
```

Outputs:

```text
reports/propagation_analysis.json
```

The implementation builds a directed graph from span parent IDs and propagation metadata, then reports root spans, propagated spans, edges, paths, longest path length, and impact score.

## Batch / Scalability Run

Run all scenarios through a chunked executor:

```powershell
$env:PYTHONPATH="backend"
py -3.11 scripts\run_scalability_batch.py --max-workers 2 --chunk-size 3
```

Outputs:

```text
reports/scalability_batch.json
```

The batch executor is intentionally backend-agnostic: local threads are the default runner, while the shard manifest can be handed to queue workers or remote executors later.

## API Endpoints

When the backend is running:

```text
GET  /experiments
GET  /propagation/{scenario_id}
GET  /scalability/batch?max_workers=2&chunk_size=3
POST /evaluator/agreement
```
