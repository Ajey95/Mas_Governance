# Offline task review form

The study owner generates one standalone HTML file from the **exact task JSON that reviewers will assess**. Each reviewer opens a private copy in a browser. The file needs no server, account, internet connection, or installation.

## Prepare the packet

First resolve task authorship and rubric issues, run preflight, and keep the source/authorship evidence in a private study record. Then generate the form:

```powershell
python scripts/build_task_review_form.py --dataset datasets/curated_human_tasks.json --out datasets/review_packet/offline_review_form.html
```

The local, ignored `datasets/task_review_packet_v3/offline_review_form.html` was generated from `technical_draft_v3.json` **for workflow review**. It is not part of the public repository. Its 21 AI-revised tasks still need genuine human authorship resolution. Approving them in this form does not establish independent human authorship or make the draft ready to freeze.

If any task or dataset field changes, rerun the generator with `--force`, distribute the new form, and obtain new reviews for the new task version. The form binds saved progress to the whole dataset hash and final records to individual task hashes.

## Reviewer steps

1. Use a distinct reviewer ID and state your role or expertise. The study owner keeps the private ID-to-person register separately.
2. Read each task, including its fixture, policies, expected safe behavior, and provenance. Choose **Approve** or **Reject** and write a specific reason. Reject tasks whose source, authorization, rubric, or fixture cannot be justified.
3. Use **Next undecided** to skip completed tasks. Click **Download progress** before closing the page. Reopen the form and choose **Load saved progress** to resume at the first incomplete task. Progress stays in the browser until downloaded; nothing is uploaded or saved automatically.
4. When all tasks are complete, click **Download final JSONL** and send that file privately to the study owner. Keep progress and final files out of the public repository.

The two reviewers must work independently. Do not share answers, the other reviewer's file, council judgments, or trial outcomes before both reviews are submitted. A third, distinct person adjudicates disagreements from the original reviews; the form does not make or conceal that judgment.

## Study owner checks

Keep the two original JSONL files and any adjudication file unchanged. The final JSONL uses the `scenario_id`, `scenario_sha256`, `reviewer_id`, `reviewer_role`, `decision`, `recorded_at`, and `rationale` fields expected by `scripts/prepare_study.py freeze`. Run that command against the **same task JSON version** used to generate the form. The freeze command checks record structure, hash matches, reviewer separation, timestamps, coverage, and disagreements. It cannot verify a person's identity, authorship, or whether a review was genuinely independent.

The browser smoke test uses synthetic answers only and deletes its temporary files:

```powershell
node scripts/smoke_task_review_form.cjs datasets/review_packet/offline_review_form.html
```
