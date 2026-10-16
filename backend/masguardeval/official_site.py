"""Public documentation site. Evaluation data and agent APIs stay on localhost."""

import re
from html import escape
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from markdown_it import MarkdownIt


SITE = Path(__file__).resolve().parents[2] / "website"
DOCS = Path(__file__).resolve().parents[2] / "docs"
GUIDES = {
    "overview": ("README.md", "Overview"),
    "quickstart": ("QUICKSTART.md", "Quickstart"),
    "sdk": ("SDK.md", "Python SDK"),
    "cli-api": ("SDK_PUBLIC_API.md", "Package and CLI"),
    "integrations": ("INTEGRATIONS.md", "Integrations"),
    "api": ("API.md", "Local API"),
    "examples": ("EXAMPLES.md", "Examples"),
    "architecture": ("ARCHITECTURE.md", "Architecture"),
    "metrics": ("METRICS.md", "Metrics"),
    "experiments": ("EXPERIMENTS.md", "Experiments"),
    "research-status": ("RESEARCH_STATUS.md", "Research status"),
    "study-authoring": ("STUDY_AUTHORING_GUIDE.md", "Study authoring"),
    "task-review": ("TASK_REVIEW_FORM.md", "Offline task review"),
    "study-protocol": ("PAPER_STUDY_PROTOCOL.md", "Study protocol"),
    "related-work": ("RELATED_WORK_AUDIT.md", "Related work"),
}
GUIDE_BY_FILE = {filename: slug for slug, (filename, _) in GUIDES.items()}
REPO = "https://github.com/Ajey95/Mas_Governance"
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/health", include_in_schema=False)
def health() -> dict[str, str]:
    return {"status": "ok", "surface": "official_site"}


def _heading_id(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^\w -]", "", value.lower()).replace(" ", "-")).strip("-")


def _guide_html(source: str) -> str:
    markdown = MarkdownIt("commonmark", {"html": False}).enable("table")
    tokens = markdown.parse(source)
    headings: dict[str, int] = {}
    for index, token in enumerate(tokens):
        if token.type == "heading_open":
            label = tokens[index + 1].content
            stem = _heading_id(label)
            count = headings.get(stem, 0)
            headings[stem] = count + 1
            token.attrSet("id", stem if not count else f"{stem}-{count}")
        if token.type != "inline" or not token.children:
            continue
        for child in token.children:
            if child.type != "link_open":
                continue
            href = child.attrGet("href") or ""
            parsed = urlsplit(href)
            if parsed.scheme or parsed.netloc or href.startswith(("#", "/")):
                continue
            filename = Path(parsed.path).name
            if filename in GUIDE_BY_FILE and not parsed.path.startswith("../"):
                target = f"/docs/{GUIDE_BY_FILE[filename]}/"
            else:
                target = f"{REPO}/blob/main/{'docs/' if not parsed.path.startswith('../') else ''}{parsed.path.removeprefix('../')}"
            child.attrSet("href", target + (f"#{parsed.fragment}" if parsed.fragment else ""))
    return markdown.renderer.render(tokens, markdown.options, {})


@app.get("/docs/{slug}/", response_class=HTMLResponse, include_in_schema=False)
def guide(slug: str) -> HTMLResponse:
    if slug not in GUIDES:
        raise HTTPException(status_code=404, detail="Unknown guide")
    filename, title = GUIDES[slug]
    path = DOCS / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Guide unavailable")
    navigation = ""
    for key, (_, label) in GUIDES.items():
        current = ' aria-current="page"' if key == slug else ""
        navigation += f'<a href="/docs/{key}/"{current}>{escape(label)}</a>'
    body = _guide_html(path.read_text(encoding="utf-8"))
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)} — MASGuardEval</title><link rel="stylesheet" href="/site.css"><link rel="stylesheet" href="/docs.css"></head><body><div class="site-shell"><header class="site-header"><a class="wordmark" href="/">MASGuardEval<span class="wordmark-mark">◈</span></a><nav aria-label="Main navigation"><a href="/">Overview</a><a href="/docs/" aria-current="page">Docs</a><a href="/tutorials/">Tutorials</a><a href="/examples/">Examples</a><a href="/method/">Method</a><a class="github-link" href="{REPO}">GitHub ↗</a></nav><span class="header-meta">LOCAL-FIRST / OPEN RESEARCH</span><button class="menu-toggle" aria-label="Toggle menu" aria-expanded="false">Menu</button></header><main class="guide-layout"><aside class="guide-sidebar"><a class="guide-back" href="/docs/">← Documentation</a><nav aria-label="Guide contents">{navigation}</nav></aside><article class="guide-body"><div class="guide-meta"><span>MAINTAINED GUIDE / {escape(title.upper())}</span><a href="{REPO}/blob/main/docs/{filename}">View source ↗</a></div>{body}</article></main><footer><div><strong>MASGuardEval</strong><p>Guarded agent execution, made inspectable.</p></div><div><a href="/docs/">Documentation</a><a href="/method/">Research method</a><a href="{REPO}">Source code ↗</a></div><small>Reference implementation · Human study pending</small></footer></div><script src="/docs.js" defer></script></body></html>'''
    return HTMLResponse(page)


app.mount("/", StaticFiles(directory=SITE, html=True), name="official_site")
