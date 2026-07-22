# Frontend QA Archive

Captured on July 31, 2026 against the local dashboard at `http://127.0.0.1:5173`.

Browser path:

```text
Playwright fallback; in-app Browser unavailable: iab
```

Evidence files:

| File | View |
| --- | --- |
| `dashboard-desktop-100.png` | Desktop viewport, 100% zoom. |
| `dashboard-desktop-110.png` | Desktop viewport, 110% zoom. |
| `dashboard-mobile-390.png` | Mobile viewport, 390px width. |
| `dashboard-timeline-step5.png` | Timeline interaction after clicking guard marker at step 5. |
| `implementation-report-html.png` | Static HTML implementation report rendered in Chrome headless. |
| `frontend_qa_report.json` | Machine-readable QA result with title, viewport, console, overlay, blank-page, and mojibake checks. |

Checks covered:

- Page identity: title `MASGuardEval`.
- Blank page check: false for all captured views.
- Framework overlay check: false for all captured views.
- Console errors/warnings: none recorded.
- Encoding artifacts: zero mojibake matches.
- Interaction proof: step-5 guard marker selected `Step 5` in the Selected Event panel.
