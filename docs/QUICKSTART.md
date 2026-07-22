# Quickstart

Run MASGuardEval locally in under five minutes.

## Prerequisites

| Tool | Version used in verification |
| --- | --- |
| Python | 3.11 |
| Node.js | 24.x |
| npm | 11.x |

Use Python 3.11 explicitly on Windows. The generic `py` launcher may point to a different Python version.

## 1. Install the SDK

```powershell
cd C:\path\to\Mas_Governance
py -3.11 -m pip install -e backend
```

Verify:

```powershell
py -3.11 -c "from masguardeval import EvaluationEngine; print(EvaluationEngine)"
```

## 2. Run One Evaluation

```powershell
py -3.11 -c "from masguardeval import EvaluationEngine; e=EvaluationEngine.from_dataset_path('datasets/golden_scenarios.json'); r=e.evaluate('auth_001'); print(r.scenario.scenario_id, r.guarded_metrics['TSP'].score)"
```

Expected shape:

```text
auth_001 1.0
```

## 3. Start the API

```powershell
py -3.11 -m uvicorn masguardeval.api:app --host 127.0.0.1 --port 8000
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
py -3.11 scripts\run_evaluation.py
```

Output:

```text
reports/latest_evaluation.json
```

## 6. Run Tests

```powershell
py -3.11 -m pytest backend\tests
```

Expected result:

```text
3 passed
```

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `No module named masguardeval` | Run `py -3.11 -m pip install -e backend` from the repo root. |
| API returns connection error | Start Uvicorn on `127.0.0.1:8000`. |
| Dashboard says API offline | Confirm `GET /health` returns `{"status":"ok"}`. |
| `py` uses Python 3.14 without pip | Use `py -3.11` explicitly. |
