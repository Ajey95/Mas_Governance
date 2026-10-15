# Independent task authoring guide

## Purpose and current state

The paper study needs **30–50 independently authored, reviewed tasks**. The default intake has 35 blank slots, five for each of the seven risk categories. A slot is an assignment, not a scenario, gold label, or claim that a person wrote it. The 35 bundled synthetic candidate tasks are engineering fixtures and should not be rewritten or relabelled as independent tasks.

## Set up the author packet

From the repository root, using the Python environment with `backend` installed:

```powershell
python scripts/prepare_study.py intake --out datasets/study_intake
```

This creates `draft_scenarios.json` with empty task content, `tool_catalog.json`, and an intake README. The task slots assign only a risk category. Authors must supply their own distinct source cases, prompts, roles, safe-behavior rubrics, and tool policies. A suitable source case may be a consented, de-identified incident or a newly designed workflow. Record its provenance and author identity in a private study register outside the public repository. Do not put real secrets, emails, customer data, or credentials in the mock workspace tasks.

For each scenario:

1. Replace the `draft_...` ID with a stable ID and fill `source_case_study` with a private register reference or safe public case reference.
2. Write a task prompt that a software-workspace assistant could actually receive, including the requester's `user_role`. Specify an observable `expected_safe_behavior` that does not depend on a guard score.
3. Select executable mock tools. Put permitted tools in `allowed_tools`, prohibited tools in `blocked_tools`, and task-essential permitted tools in `required_tools`. Fill `parameter_schema`, role/resource policy fields, and `sensitive_tools` or `high_risk_tools` where the case requires them. Keep `reference_events` empty for model-driven study tasks; they are scripted demonstration traces.

   The runtime parameter guard expects `{"mock_file_read": {"allowed_keys": ["path"], "required_keys": ["path"]}}`. A JSON-Schema-style map of `path` to a type description is not accepted by that guard. Attribute policies are keyed by **tool name** and use `subject`, `resource`, and/or `match` rules. For file calls, resource-attribute keys must match the exact `path` tool argument. Inspect `backend/masguardeval/guards.py` before adding a policy; an unrecognized policy key gives no protection.
4. Add **exactly one** `family:<source-id>` tag. Tasks derived from the same incident, workflow, or closely related wording belong to the same family. Each risk category needs at least two genuinely distinct source families so no family crosses the development/held-out split. A family must not span risk categories.
5. Change `provenance` to `independent_human_authored` only if the task was independently written. This field is an author declaration; software cannot verify a person's identity or the independence of the work.

The 35-slot intake is a target, not an obligation to approve every slot. Author replacement tasks if review rejects items so that the accepted set remains between 30 and 50 and all seven risks retain at least two source families.

### Available mock tools

| Tool | Effect in the isolated workspace | Common parameters |
| --- | --- | --- |
| `mock_email_search` | Returns email metadata | `date`, `sender`, `subject_only` |
| `mock_email_body_read` | Returns a fixed private example body | `date`, `message_id` |
| `mock_file_read` | Reads a workspace file | `path` |
| `mock_file_write` | Writes a workspace file | `path`, `content` |
| `mock_shell_execution` | Returns a simulated shell result; no host command runs | `command` |
| `mock_memory_write` | Stores a key and value for the run | `key`, `value` |
| `mock_memory_read` | Reads a key for the run | `key` |
| `mock_background_job_creation` | Adds a simulated job | `job_type` |

Only these tools have handlers in the built-in `MockWorkspace`. A real framework adapter can expose other tools, but this particular mock-workspace study needs an implementation for each tool it names.

Without a scenario fixture, the mock workspace has only three preset files (`/private/payroll.csv`, `/workspace/config.yml`, and `/workspace/shared.md`), a generic email search and body, empty run memory, and simulated shell/jobs. A scenario's `workspace_fixture` can instead seed isolated files, email messages, memory, shell responses, and job responses. Verify the baseline can observe each task's relevant facts before including it in the paper dataset. A task prompt alone does not create that state.

## Check, review, and freeze

Run a preflight check when the draft is filled:

```powershell
python scripts/prepare_study.py preflight --dataset datasets/study_intake/draft_scenarios.json --out datasets/study_intake/preflight.json
```

Preflight checks field completeness, risk and family coverage, executable tool names, schema consistency, duplicate prompts, and exact prompt overlap with bundled fixtures. It cannot establish human authorship, case independence, semantic novelty, or rubric quality. A nonzero exit means the draft is not ready for review; the blank packet intentionally fails.

Once preflight passes, generate reviewer templates from the completed task file:

```powershell
python scripts/prepare_study.py packet --dataset datasets/study_intake/draft_scenarios.json --out datasets/task_review_packet
```

Give each of two reviewers a separate template and no access to the other's decisions. They should assess task realism, source independence, category and family fit, permitted/prohibited actions, rubric clarity, tool feasibility, and privacy. Each reviewer supplies a distinct identity, role, timezone-stamped decision (`approve` or `reject`), and rationale. A third person adjudicates each disagreement. Keep identity evidence and consent records in the private study register. If an author changes a scenario after reviews, regenerate the packet: the hashes deliberately invalidate stale reviews.

Freeze only after the human reviews are complete:

```powershell
python scripts/prepare_study.py freeze --dataset datasets/study_intake/draft_scenarios.json --reviews datasets/task_review_packet/reviewer_a.jsonl datasets/task_review_packet/reviewer_b.jsonl --adjudications datasets/task_review_packet/adjudications.jsonl --out datasets/frozen_study
```

The freeze command checks reviewer separation, hashes, accepted count, risk coverage, and family-level split. The output manifest records the task-set hashes. Do not run held-out trials or adjust thresholds until that split is frozen. The full execution and outcome-label protocol is in [PAPER_STUDY_PROTOCOL.md](PAPER_STUDY_PROTOCOL.md).
