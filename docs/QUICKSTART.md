# Quickstart

Run MASGuardEval locally in under five minutes.

## Prerequisites

| Tool | Version used in verification |
| --- | --- |
| Python | 3.10 or newer |
| Node.js | 24.x |
| npm | 11.x |

Use a Python 3.10+ environment with pip available. On Windows, `python --version` shows the interpreter used by the commands below.

## 1. Install the SDK

```powershell
cd C:\path\to\Mas_Governance
python -m pip install -e backend
```

Verify:

```powershell
masguardeval --version
masguardeval validate --dataset examples/fictional_scenarios.json
```

## 2. Run One Evaluation

```powershell
masguardeval evaluate --dataset datasets/golden_scenarios.json --scenario auth_001 --out reports/reference_auth_001.json
```

The JSON contains baseline and guarded traces, graphs, and applicable metrics.

## 3. Start the local dashboard and API

To run a custom agent factory before starting the dashboard, try the fictional
example. Replace the factory with your own trusted adapter and guarded tool
handlers for a real integration:

```powershell
masguardeval run-agent --dataset examples/fictional_scenarios.json --scenario fictional_tool_boundary --factory examples/cli_agent_factory.py:create_engine --out reports/my-agent.json --sqlite reports/runs.sqlite3
```

This command runs guarded only and records trace spans, metrics, and the
observed graph. It does not automatically discover tools or intercept an agent
whose actions bypass the registered handlers.

To compare fresh baseline and guarded runs of the same trusted factory, use
`compare-agent` with isolated test handlers. Its baseline intentionally has no
guards, so the explicit flag is required:

```powershell
masguardeval compare-agent --dataset examples/fictional_scenarios.json --scenario fictional_tool_boundary --factory examples/cli_agent_factory.py:create_engine --allow-unguarded --out reports/comparison.json --sqlite reports/runs.sqlite3
masguardeval trace-report --input reports/comparison.json --mode guarded --json-out reports/guarded-detail.json --md-out reports/guarded-detail.md
```

The comparison includes both traces, graphs, findings, and applicable metric
changes. These are observed trace differences, not independent task outcomes.

```powershell
python scripts/start_local_dashboard.py
```

Verify:

```powershell
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok"}
```

## 4. Inspect the dashboard

Open `http://127.0.0.1:8000`. The launcher builds the frontend and serves it
with the API on loopback. Use the nested graph probe buttons to inspect two
subgraphs, repeated reason–act cycles, and a blocked branch. These probes are
fictional topology checks, not live-agent performance evidence.

## 5. Generate a Report

```powershell
cd C:\path\to\Mas_Governance
masguardeval report --dataset datasets/golden_scenarios.json --json-out reports/reference_report.json --md-out reports/reference_report.md
```

The CLI's report uses the scripted reference adapter. For the dashboard's
`reports/latest_evaluation.json`, run `python scripts/run_evaluation.py`.

## 6. Run Tests

```powershell
python -m pytest backend\tests
```

The exact test count changes as the framework grows.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `No module named masguardeval` | Run `python -m pip install -e backend` from the repo root. |
| API returns connection error | Start `python scripts/start_local_dashboard.py` and check `127.0.0.1:8000`. |
| Dashboard says API offline | Confirm `GET /health` returns `{"status":"ok"}`. |
| `python` has no pip | Select a Python 3.10+ installation with pip and verify `python -m pip --version`. |

## Candidate tasks and optional live agent runs

The default seven cases are reference fixtures. To regenerate the 35 synthetic, unadjudicated candidate tasks and validate they load:

```powershell
$env:PYTHONPATH = "backend"
python scripts/generate_candidate_dataset.py
python -c "from masguardeval import GoldenDataset; print(len(GoldenDataset.load('datasets/candidate_scenarios.json').scenarios))"
```

For real model calls, install the optional dependency, set your own API key, and run the paired single/multi architecture CLI. This incurs external API use and is not part of the bundled verification:

```powershell
python -m pip install -e 'backend[live]'
$env:OPENAI_API_KEY = '<your key>'
python scripts/run_live_experiment.py --model <pinned-model-id> --dataset datasets/candidate_scenarios.json --architectures single,multi --trials 3
```

The model-study script writes `reports/live_experiment.json` and stores each
trace in `reports/runs.sqlite3`. It remains separate from the installed
`masguardeval` reference CLI. Its analysis averages repeated runs within each
scenario before computing scenario-level intervals and exploratory sign-flip
tests. Independent task labels and a held-out evaluation are still needed for
paper claims.
