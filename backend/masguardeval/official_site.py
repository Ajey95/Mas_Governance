"""Public documentation site. Evaluation data and agent APIs stay on localhost."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


SITE = Path(__file__).resolve().parents[2] / "website"
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/health", include_in_schema=False)
def health() -> dict[str, str]:
    return {"status": "ok", "surface": "official_site"}


app.mount("/", StaticFiles(directory=SITE, html=True), name="official_site")
