"""Check external judge model catalogues without printing credentials."""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def probe(name: str, url: str, header: str, key: str | None) -> dict[str, object]:
    if not key:
        return {"status": "missing_key"}
    request = Request(url, headers={header: key})
    try:
        with urlopen(request, timeout=20) as response:
            data = json.load(response)
        if name == "gemini":
            ids = [item.get("name", "").removeprefix("models/") for item in data.get("models", [])
                   if "generateContent" in item.get("supportedGenerationMethods", [])]
        else:
            ids = [item.get("id", "") for item in data.get("data", [])]
        return {"status": "ok", "models": sorted(item for item in ids if item)}
    except HTTPError as exc:
        return {"status": "http_error", "http_status": exc.code}
    except URLError as exc:
        return {"status": "network_error", "error_type": type(exc.reason).__name__}


def main() -> None:
    results = {
        "gemini": probe("gemini", "https://generativelanguage.googleapis.com/v1beta/models",
                        "x-goog-api-key", os.environ.get("GEMINI_API_KEY")),
        "groq": probe("groq", "https://api.groq.com/openai/v1/models",
                      "Authorization", "Bearer " + os.environ["GROQ_API_KEY"] if os.environ.get("GROQ_API_KEY") else None),
    }
    print(json.dumps(results))


if __name__ == "__main__":
    main()
