# Contributing to MASGuardEval

MASGuardEval is a research reference framework. Contributions to the software,
examples, and usage guides are welcome under the repository [MIT software
license](LICENSE). The manuscript, study data, reviewer records, and reports
have separate provenance and are outside that license.

## Development checks

From the repository root with Python 3.10+ and Node.js installed:

```powershell
python -m pip install -e "backend[langgraph]"
python -m pytest backend/tests -q
cd frontend
npm ci
npm run build
```

Optional AutoGen and CrewAI tests need their corresponding package extras.
The `backend[all-integrations]` extra installs all four framework adapters;
integration examples use fictional local handlers.

## Changes to execution and metrics

- Add a failing behavior test before changing a guard, runner, CLI, or metric.
- Keep unguarded baseline handlers inside an isolated test environment. A
  wrapper can only guard or trace calls routed through it.
- Preserve span IDs, policy decisions, actual reached tool effects, metric
  applicability, and evidence counts. Do not convert missing evidence to a
  clean score.
- Describe dependency paths as candidate explanations, not causal proof.
- Keep DT distinct from measured human diagnosis time.

## Research provenance

Do not submit generated tasks, model votes, scripted traces, or synthetic labels
as independently human-authored study evidence. Keep reviewer identity records,
private packets, API keys, and confidential traces out of Git. If a dataset or
scenario changes, obtain reviews against its new hash before freezing it.

Please explain what changed, why it is needed, how it was tested, and any
limits to the claim in your pull request.
