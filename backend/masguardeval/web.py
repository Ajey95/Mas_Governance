"""Serve the dashboard and API from one origin, with a private preview gate."""

import hmac
import os
import time
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from .api import ROOT, app


COOKIE_NAME = "mge_site_session"
SITE_TOKEN = os.environ.get("MASGUARDEVAL_SITE_TOKEN", "")
REQUIRE_SITE_AUTH = os.environ.get("MASGUARDEVAL_REQUIRE_SITE_AUTH") == "1"
SESSION_SECONDS = 12 * 60 * 60

if os.environ.get("MASGUARDEVAL_REQUIRE_DATABASE_URL") == "1" and not os.environ.get("MASGUARDEVAL_DATABASE_URL"):
    raise RuntimeError("MASGUARDEVAL_DATABASE_URL is required for the Render deployment")


def _session_signature(expires_at: int) -> str:
    return hmac.digest(SITE_TOKEN.encode(), f"masguardeval:{expires_at}".encode(), "sha256").hex()


def _valid_session(value: str | None) -> bool:
    if not value or "." not in value:
        return False
    expiry, signature = value.split(".", 1)
    if not expiry.isdigit() or int(expiry) <= int(time.time()):
        return False
    return hmac.compare_digest(signature, _session_signature(int(expiry)))


if REQUIRE_SITE_AUTH:
    if not SITE_TOKEN:
        raise RuntimeError("MASGUARDEVAL_SITE_TOKEN is required for the Render preview")

    @app.middleware("http")
    async def private_preview_gate(request: Request, call_next):
        if request.url.path in {"/health", "/site-login"}:
            return await call_next(request)
        if _valid_session(request.cookies.get(COOKIE_NAME)):
            return await call_next(request)
        if request.method == "GET" and "text/html" in request.headers.get("accept", ""):
            return RedirectResponse("/site-login", status_code=303)
        return JSONResponse({"detail": "Sign in to the private research preview"}, status_code=401)

    @app.get("/site-login", include_in_schema=False)
    def site_login_page() -> HTMLResponse:
        html = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
        <title>MASGuardEval private preview</title><style>body{font:16px system-ui;max-width:26rem;margin:12vh auto;padding:1.5rem;background:#f4f7f8;color:#17333b}
        form{display:grid;gap:1rem}input,button{font:inherit;padding:.75rem;border-radius:.5rem;border:1px solid #b6c9cb}button{background:#087b73;color:white;cursor:pointer}</style>
        <h1>MASGuardEval</h1><p>Private research preview</p><form id="login"><label>Access token <input type="password" name="token" required autocomplete="off"></label>
        <button>Sign in</button></form><p id="error" role="alert"></p><script>
        document.getElementById('login').addEventListener('submit',async event=>{event.preventDefault();const token=new FormData(event.target).get('token');
        const response=await fetch('/site-login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token})});
        if(response.ok)location.replace('/');else document.getElementById('error').textContent='Access denied';});</script></html>"""
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    @app.post("/site-login", include_in_schema=False)
    async def site_login(request: Request) -> Response:
        try:
            payload = await request.json()
        except ValueError:
            payload = {}
        candidate = payload.get("token") if isinstance(payload, dict) else None
        if not isinstance(candidate, str) or not hmac.compare_digest(candidate, SITE_TOKEN):
            return JSONResponse({"detail": "Access denied"}, status_code=401)
        expires_at = int(time.time()) + SESSION_SECONDS
        response = Response(status_code=204, headers={"Cache-Control": "no-store"})
        response.set_cookie(COOKIE_NAME, f"{expires_at}.{_session_signature(expires_at)}",
                            max_age=SESSION_SECONDS, secure=True, httponly=True, samesite="lax")
        return response


FRONTEND_DIST = Path(os.environ.get("MASGUARDEVAL_FRONTEND_DIST", str(ROOT / "frontend" / "dist")))
app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="dashboard")
