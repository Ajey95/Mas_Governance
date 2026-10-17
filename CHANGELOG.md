# Changelog

## 0.2.1 — 2026-10-17

- Correct TSR so optional allowed tools are not silently treated as required when `required_tools` is omitted.
- Require a resolved dependency or explicit negative assessment for each later failure before reporting an applicable CFP score. Unrelated dependency edges no longer produce a misleading zero.
- Exclude routine guard checks from DT's first-signal position. DT is now descriptive only: it has no threshold, pass/fail, paired improvement, or task-risk threshold tuning. Actual analyst time remains a separate human study measurement.
- Return a null pass/fail value for inapplicable metrics instead of reporting an invalid denominator as a failed rule.
- Clarify the seven operational measures versus DT in reports, the dashboard, public guides, and the manuscript. Exploratory thresholds remain unvalidated.

## 0.2.0 — 2026-10-16

- Add `compare-agent` for fresh baseline and guarded custom-agent runs with explicit unguarded opt-in, paired traces, graphs, findings, and applicable metric changes.
- Add `trace-report` for recomputed, span-linked provenance and observability evidence from JSON or a saved trace. Paired comparison files support `--mode baseline` and `--mode guarded`.
- Add blinded, timed diagnosis packet, assignment, review, reference, and analysis commands. These collect study evidence; no human outcome or timing result is bundled.
- Distinguish structural span nesting from declared candidate failure dependencies and expose graph paths in the interactive local workbench.
- Improve PHR, CPI, CFP, and CCR evidence coverage and N/A behavior. Thresholds and construct validity remain unvalidated.
- Add the public offline task-review guide and source generator, a frontend CI build, and a repository license for software and usage guides.
- Refresh the FastAPI/Starlette/Uvicorn compatibility range after a dependency audit, and update the frontend lockfile to resolve reported transitive advisories.

The seven reference cases and 35 synthetic candidates are not a validated golden dataset. This release does not claim measured safety improvement, causal root diagnosis, or human diagnosis-time savings.

## 0.1.3 — 2026-10-15

- Publish the maintained guides through the official website while retaining local Swagger for the evaluation API.
- Keep the public site separate from the localhost evaluation workbench.
