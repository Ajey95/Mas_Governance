# SAIS 2027 LaTeX source

The working conference source is [`MASGuardEval_SAIS27.tex`](MASGuardEval_SAIS27.tex), with the official [`usenix2019_v3.sty`](usenix2019_v3.sty) downloaded from the [USENIX template page](https://www.usenix.org/conferences/author-resources/paper-templates) on 14 October 2026. Its style rules are unchanged; blank-comment trailing whitespace was normalized. The downloaded sample `usenix2019_v3.2.tex` is retained for reference, not used as the paper source.

The source uses US letter, two columns, 10-point type, and the official style. It has an anonymous author block, in-text citations with eight matching bibliography entries, and an Open Science appendix. It contains only the audited local feasibility observations; diagnostic and mitigation results remain pending. The [SAIS preliminary CFP](https://www.usenix.org/sites/default/files/sais27_cfp_100826.pdf) limits the main body to 13 pages and the complete paper to 30 pages. The 15 October XeTeX build has six main-body pages and eight pages total.

Compile with a conventional LaTeX installation from this directory:

```powershell
pdflatex -interaction=nonstopmode -halt-on-error MASGuardEval_SAIS27.tex
pdflatex -interaction=nonstopmode -halt-on-error MASGuardEval_SAIS27.tex
```

The app's standalone compiler uses Tectonic/XeTeX. The source embeds a XeTeX-compatible copy of the official style for the single-file editor, while the adjacent official `.sty` retains the venue's pdfLaTeX rules. `scripts/build_paper.ps1` copies the source to an isolated build directory so the adjacent style cannot override that compatibility copy. Tectonic 0.17.0 produced an eight-page PDF on 15 October 2026; all pages were rendered and visually checked, the PDF metadata contained no author field, and the log contained no overfull boxes after widening the glossary column. The separate pdfLaTeX build remains an acceptance check because that engine is not installed here.

The 14 October layout pass kept the official typography and added two vector diagrams (an explicitly illustrative trace and the implemented paired-run workflow), a compact local-pilot table, booktabs rules for the metric table, sentence-case headings, and a three-part contributions paragraph. The editor compiler returned success after these changes. The compile result does not provide a page-count or visual inspection report.

Before submission, add adjudicated diagnostic and outcome results, review all AI-assisted text and references, prepare an anonymous non-tracking artifact, check PDF metadata and identifying content, and recheck the final CFP.

On 15 October, Figure 2 was restored to the original inline TikZ paired-run workflow that preceded the GPT image request. The generated image remains at `figures/masguardeval_architecture_gpt.png` but is not used in the manuscript. The Related Work section was expanded into a literature survey covering risk benchmarks, telemetry and diagnosis, runtime controls, and the paper's position. The built-in editor compiler returned success after these edits.

Later on 15 October, Figure 2 was redrawn in-place as a restrained-color vector architecture diagram with separate baseline and guarded mock states, solid execution arrows, dashed trace-capture arrows, and independent graph and metric outputs. The [SAIS 2027 preliminary CFP](https://www.usenix.org/sites/default/files/sais27_cfp_100826.pdf) requires legibility in grayscale, not a grayscale-only figure. The editor compiler returned success. The generated PNG remains unused.

The user then requested a revert. Figure 2 and its caption are again the original pre-color TikZ version; the color definitions were removed. The literature survey remains. The editor compiler returned success.

The literature survey was subsequently moved intact to Section 2, immediately after the Introduction and before Problem and scope. The built-in editor compiler returned success.

Table 1 was rechecked against `backend/masguardeval/metrics.py`. Its formula column was widened, the applicability column narrowed, mathematical cells vertically centered, and `t(X)` defined for the set notation in TSR. The built-in editor compiler returned success.
