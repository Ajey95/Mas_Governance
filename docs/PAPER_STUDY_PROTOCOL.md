# Paper study protocol and claim gates

This document is a preregistration template, not a report of completed experiments. The supplied plan targets 30–50 realistic tasks. The repository contains seven reference fixtures and 35 synthetic candidate variants; none of the variants has an independent gold label.

## Implemented study workflow

The repository now has commands for task review, frozen task-family splits, condition-masked outcome review, held-out metric checks, and descriptive guard-profile comparison. The commands validate records and hashes; they cannot verify a reviewer's real-world identity or turn template-derived cases into independently authored tasks.

Start with a clean 35-slot authoring packet and the [authoring guide](STUDY_AUTHORING_GUIDE.md). It contains no copied candidate prompts or claimed human authorship:

```powershell
python scripts/prepare_study.py intake --out datasets/study_intake
python scripts/prepare_study.py preflight --dataset datasets/study_intake/draft_scenarios.json --out datasets/study_intake/preflight.json
```

The blank packet deliberately fails preflight until human authors fill it. `preflight` detects incomplete fields, tool mismatch, duplicate/exact bundled-fixture prompts, and inadequate risk/family coverage; it cannot verify who authored a case or whether two cases are semantically independent. The generated task/review directories are ignored by Git by default so private study records are not accidentally staged.

To create blank review files for the current synthetic candidates *for workflow testing only*:

```powershell
python scripts/prepare_study.py packet --dataset datasets/candidate_scenarios.json --out datasets/review_packet
```

Reviewers must author or substantially replace tasks in a separate scenario JSON file, mark genuine independent authorship with `provenance: independent_human_authored`, and add one `family:<id>` tag to each task. The freeze gate requires 30–50 accepted tasks, every risk category, at least two task families per category, two separate timezone-stamped reviews per task, and a third adjudicator for disagreement. Reviews bind to exact scenario hashes. A provenance field is a submitted claim, not proof of human authorship. Keep source records and reviewer identity evidence outside the public repository.

For a one-task-at-a-time offline review interface, generate the [task review form](TASK_REVIEW_FORM.md) from the exact task JSON after content and provenance repair. Each reviewer gets a private copy and exports a separate hash-bound JSONL file. The current v3 form is for workflow review while its provenance remains unresolved.

```powershell
python scripts/prepare_study.py freeze --dataset datasets/curated_human_tasks.json --reviews reviewer_a.jsonl reviewer_b.jsonl --adjudications adjudications.jsonl --out datasets/frozen_study
```

The output contains `development.json`, `heldout.json`, and a manifest with hashes and family assignments. The command refuses to freeze the supplied synthetic candidate dataset as independently authored gold data.

## Task set

1. Have domain reviewers independently design or revise 30–50 software-workspace tasks across all seven risk categories. Record source case, prompt, user role, permitted and prohibited actions, resources, tool schemas, and expected outcome before model runs.
2. Separate development and held-out tasks by task family or source case, not by merely changing wording. Freeze the held-out JSON and record its SHA-256 before tuning guards or thresholds.
3. Use two blinded reviewers for each task rubric and each trial outcome. Resolve disagreement with a documented adjudicator. Keep reviewer identity, role, timestamps, and original labels separate from the model traces. Never relabel the synthetic example agreement file as human work.

## Execution matrix

Run both the single-agent comparator and Planner–Executor–Reviewer architecture on the same task set, each in baseline and guarded modes, with repeated trials. Record model identifier and returned model version, API response IDs, dataset hash, Git revision and dirty state, prompts, tool schemas, guard configuration, trial number, and trace ID. The runner keeps tool effects inside the isolated mock workspace; guard intervention stops a run before downstream tool feedback.

The CLI implements this matrix:

```powershell
python scripts/run_live_experiment.py --model <pinned-model-id> --dataset <frozen-task-json> --architectures single,multi --trials <N>
```

For local pilot work, the same CLI can use a pinned Ollama model and its recorded digest:

```powershell
python scripts/run_live_experiment.py --provider ollama --model gemma4:latest --dataset datasets/frozen_study/development.json --architectures single,multi --trials 5 --guard-profile full --out reports/development_full.json
```

Run the held-out file only after choosing thresholds on development data. `--guard-profile allowlist` and `--guard-profile access_control` provide internal rule-based comparators; they are not independent third-party guard products. The CLI saves a partial report after each paired trial, records raised failures without inventing results, flags adapter protocol errors embedded inside traces, and accepts `--resume` only when the run configuration and dataset hash match. The local pilot exposed one such invalid-action pair; `scripts/audit_live_report.py` preserves the raw report and writes an audited copy.

Create condition-masked outcome packets after a report completes:

```powershell
python scripts/review_outcomes.py packet --report reports/development_full.json --review-out reports/development_review_packet --private-map-out reports/development_private_map.json
```

Give each reviewer only the packet and one blank review template. Keep the private condition map separate. The packet hides the explicit mode and guard-decision spans, but output text may still reveal that a request stopped; blinding is therefore partial. Two reviewers independently label task failure and committed prohibited action; a distinct adjudicator resolves disagreement. Reconcile labels with `scripts/review_outcomes.py reconcile`. **Preregister how invalid agent actions count as task failures.** The current analysis includes independently labelled protocol failures in primary outcomes and excludes those pairs from metric construct checks. Once development and held-out reports are fully labelled, run `scripts/analyze_study.py` with both frozen datasets, reports, outcomes, and the manifest. It selects exploratory metric thresholds on development labels and applies them unchanged to held-out labels.

### Secondary three-model judge council

The optional council runs **after** packet generation and uses the same masked packet. Configure `OPENAI_API_KEY`, `GEMINI_API_KEY`, and `GROQ_API_KEY` in the process environment. Do not give its votes or majority result to the human reviewers. Keep the output outside the reviewer packet directory:

```powershell
$env:PYTHONPATH = "backend"
python scripts/judge_outcomes.py council --packet reports/development_review_packet/blinded_trials.jsonl --out reports/development_model_council.json
python scripts/judge_outcomes.py compare --packet reports/development_review_packet/blinded_trials.jsonl --private-map reports/development_private_map.json --judgments reports/development_model_council.json --human-outcomes reports/development_human_outcomes.json --out reports/development_model_human_agreement.json
```

OpenAI, Gemini, and Groq vote independently. Each vote binds to the packet hash and records the prompt version, provider/model, response ID, cited span IDs, and rationale. A per-label majority requires two decisive votes; errors and uncertain votes remain visible. The council is a **secondary agreement and error-analysis instrument**. Adjudicated human outcomes remain the primary labels, including when the council unanimously disagrees. The comparison excludes unresolved council rows and reports their count.
`--resume` retries only providers missing from a partial council row and preserves successful votes. A row with two decisive votes but one provider error is marked `complete_with_provider_errors`, not a complete three-provider council. The default Gemini model is the operationally tested `gemini-2.5-flash`; model versions and response IDs in the saved report are the provenance record. A one-row fictional service smoke succeeded on 2026-10-15, but a full blinded packet should only be judged after the study task set is frozen; it is not a human agreement result.

The experiment manifest and SQLite database are raw evidence. Store access and retention rules are the study owner's responsibility before using confidential tasks.

## Outcomes and analysis

Primary outcomes should be independently judged task failure and prohibited-action rate. Treat TSP, TSR, PHR, CPI, CFP, RSS, and CCR as secondary proposed trace constructs. Validate their formulas against reviewer labels, inspect false positives and false negatives, and freeze any exploratory thresholds using development data before evaluating held-out tasks. CFP is an observed candidate propagation share. DT is a descriptive first-signal position, excluded from directional safety summaries and threshold tuning; the separate analyst study measures actual diagnosis time.

The built-in summary groups repeated trials within scenario before calculating an exploratory mean improvement, scenario-bootstrap interval, and unadjusted sign-flip p-value. Specify primary metrics, minimum practical effect, multiplicity handling, and missing-run rules before confirmatory analysis. Show per-risk-category counts and N/A denominators. Compare against at least one credible existing mitigation stack on matched tasks if claiming an improvement beyond the unguarded baseline.

### Timed human diagnosis

The installed CLI supports a separate measured-time protocol. Select **one repeated trial per scenario and one architecture** for a four-panel diagnosis comparison; the report used here must be complete. Two independent reviewers see each condition, but each reviewer sees only one condition of a scenario, reducing paired-condition carryover. Panel order is randomized with a recorded seed. The condition map and assignment manifest must stay with the study owner, outside reviewer directories.

```powershell
masguardeval diagnosis-packet --report reports/development_full.json --architecture single --trial 1 --review-out reports/diagnosis_blinded --private-map-out reports/private/diagnosis_map.json
masguardeval diagnosis-assign --packet reports/diagnosis_blinded/blinded_trials.jsonl --private-map reports/private/diagnosis_map.json --out-dir reports/diagnosis_panels --private-manifest-out reports/private/diagnosis_assignment.json
masguardeval diagnosis-reference-template --packet reports/diagnosis_blinded/blinded_trials.jsonl --out reports/private/diagnosis_reference.jsonl
masguardeval diagnosis-review --packet reports/diagnosis_panels/panel_a_1.jsonl --reviewer-id reviewer_a1 --reviewer-role domain_expert --out reports/private/diagnosis_a1.jsonl
masguardeval diagnosis-analyze --packet reports/diagnosis_blinded/blinded_trials.jsonl --private-map reports/private/diagnosis_map.json --reviews reports/private/diagnosis_a1.jsonl reports/private/diagnosis_a2.jsonl reports/private/diagnosis_b1.jsonl reports/private/diagnosis_b2.jsonl --reference reports/private/diagnosis_reference.jsonl --out reports/private/diagnosis_analysis.json
```

Repeat `diagnosis-review` with the other three panel files and distinct people before analysis. Run each architecture with a separate reviewer pool so a person does not learn the same scenario from another architecture. The reference template is **blank**: an independent expert must set `reference_status` to `root_present`, `no_visible_root`, or `unscorable`, provide visible `accepted_span_ids` when a root is present, and record identity, time, and rationale. Do not copy candidate roots or failure labels from MASGuardEval into the reference. The reviewer sees the prompt, visible agent/tool and graph events, and final response, but no guard-decision spans, condition label, or failure labels; final response text may still reveal an intervention.

The timer starts when a reviewer opens each trial and stops when they submit a visible span ID or `none`; rationale entry is outside the timed interval. Records bind to each packet hash and contain UTC start/answer times plus local monotonic elapsed milliseconds. Analysis requires two distinct timed records per condition, checks visible span citations and independent reference coverage, reports accuracy and median correct-answer time in `actual_diagnosis_time`, and calculates a descriptive paired difference only when both reviewers were correct in both conditions. It rejects a reviewer who saw both conditions of the same scenario. The collector has a 60-minute maximum per trial. Software cannot authenticate reviewers, detect off-task time, or verify reference independence. Predefine any shorter time cap, practice trials, exclusion rules, panel assignment, and primary comparison before collection. No genuine analyst timing records are supplied here.

If a review is interrupted, rerun the same `diagnosis-review` command with `--resume`; completed rows must still match the exact panel hash and reviewer ID. Keep the partial JSONL private.

## Claims allowed by the current repository

The code can demonstrate that a guard intercepted an attempted mock action, that a trace and graph contain observed steps, and that the metric calculations are reproducible on those steps. It cannot yet establish general risk reduction, novel validated metrics, inter-rater reliability from human labels, or paper-ready statistical significance. Those claims require the external study above.
