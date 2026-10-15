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
python -c "from masguardeval import EvaluationEngine; print(EvaluationEngine)"
```

## 2. Run One Evaluation

```powershell
python -c "from masguardeval import EvaluationEngine; e=EvaluationEngine.from_dataset_path('datasets/golden_scenarios.json'); r=e.evaluate('auth_001'); print(r.scenario.scenario_id, r.guarded_trace.blocked, r.guarded_metrics['TSP'].applicable)"
```

Expected shape:

```text
auth_001 True False
```

## 3. Start the API

```powershell
python -m uvicorn masguardeval.api:app --host 127.0.0.1 --port 8000
```

Verify:

```powershell
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok"}
```

## 4. Start the Dashboard

Open a second terminal:

```powershell
cd C:\path\to\Mas_Governance\frontend
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

## 5. Generate a Report

```powershell
cd C:\path\to\Mas_Governance
python scripts\run_evaluation.py
```

Output:

```text
reports/latest_evaluation.json
```

## 6. Run Tests

```powershell
python -m pytest backend\tests
```

Expected result:

```text
32 passed
```

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `No module named masguardeval` | Run `python -m pip install -e backend` from the repo root. |
| API returns connection error | Start Uvicorn on `127.0.0.1:8000`. |
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

The CLI writes `reports/live_experiment.json` and stores each trace in `reports/runs.sqlite3`. Its analysis averages repeated runs within each scenario before computing scenario-level intervals and exploratory sign-flip tests. Independent task labels and a held-out evaluation are still needed for paper claims.
