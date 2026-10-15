"""Serve the dashboard and API with preview and optional per-user gates."""

import asyncio
import hmac
import os
import time
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from .api import ROOT, app
from .user_auth import AuthError, SupabaseAuth


COOKIE_NAME = "mge_site_session"
SITE_TOKEN = os.environ.get("MASGUARDEVAL_SITE_TOKEN", "")
REQUIRE_SITE_AUTH = os.environ.get("MASGUARDEVAL_REQUIRE_SITE_AUTH") == "1"
REQUIRE_USER_AUTH = os.environ.get("MASGUARDEVAL_REQUIRE_USER_AUTH") == "1"
PUBLIC_ORIGIN = os.environ.get("MASGUARDEVAL_PUBLIC_ORIGIN", "https://masguardeval.onrender.com").rstrip("/")
SESSION_SECONDS = 12 * 60 * 60
USER_ACCESS_COOKIE = "mge_user_access"
USER_REFRESH_COOKIE = "mge_user_refresh"

if os.environ.get("MASGUARDEVAL_REQUIRE_DATABASE_URL") == "1" and not os.environ.get("MASGUARDEVAL_DATABASE_URL"):
    raise RuntimeError("MASGUARDEVAL_DATABASE_URL is required for the Render deployment")
if REQUIRE_USER_AUTH and not os.environ.get("MASGUARDEVAL_DATABASE_URL"):
    raise RuntimeError("MASGUARDEVAL_DATABASE_URL is required for per-user trace isolation")
if REQUIRE_USER_AUTH and not PUBLIC_ORIGIN.startswith("https://"):
    raise RuntimeError("MASGUARDEVAL_PUBLIC_ORIGIN must use HTTPS")
auth = (SupabaseAuth(os.environ.get("MASGUARDEVAL_SUPABASE_URL", ""),
                     os.environ.get("MASGUARDEVAL_SUPABASE_PUBLISHABLE_KEY", ""))
        if REQUIRE_USER_AUTH else None)


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


def _set_user_cookies(response: Response, session: dict) -> None:
    access_age = max(60, min(int(session.get("expires_in", 3600)), 3600))
    response.set_cookie(USER_ACCESS_COOKIE, session["access_token"], max_age=access_age,
                        secure=True, httponly=True, samesite="lax")
    response.set_cookie(USER_REFRESH_COOKIE, session["refresh_token"], max_age=30 * 86400,
                        secure=True, httponly=True, samesite="lax")


if REQUIRE_USER_AUTH:
    @app.middleware("http")
    async def user_auth_gate(request: Request, call_next):
        path = request.url.path
        if path == "/health" or path == "/site-login":
            return await call_next(request)
        if REQUIRE_SITE_AUTH and not _valid_session(request.cookies.get(COOKIE_NAME)):
            if request.method == "GET" and "text/html" in request.headers.get("accept", ""):
                return RedirectResponse("/site-login", status_code=303)
            return JSONResponse({"detail": "Sign in to the private research preview"}, status_code=401)
        if path in {"/user-login", "/user-register", "/user-logout", "/user-recover", "/user-reset"}:
            return await call_next(request)

        session = None
        user = None
        access = request.cookies.get(USER_ACCESS_COOKIE)
        if access:
            try:
                user = await asyncio.to_thread(auth.user, access)
            except AuthError:
                pass
        if user is None and request.cookies.get(USER_REFRESH_COOKIE):
            try:
                session = await asyncio.to_thread(auth.refresh, request.cookies[USER_REFRESH_COOKIE])
                user = await asyncio.to_thread(auth.user, session["access_token"])
            except AuthError:
                pass
        if user is None:
            if request.method == "GET" and "text/html" in request.headers.get("accept", ""):
                return RedirectResponse("/user-login", status_code=303)
            return JSONResponse({"detail": "Sign in with a user account"}, status_code=401)
        request.state.owner_id = user["id"]
        request.state.user_email = user.get("email", "")
        response = await call_next(request)
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Vary"] = "Cookie"
        if session is not None:
            _set_user_cookies(response, session)
        return response

    @app.get("/user-login", include_in_schema=False)
    def user_login_page() -> HTMLResponse:
        html = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
        <title>MASGuardEval user sign in</title><style>body{font:16px system-ui;max-width:27rem;margin:8vh auto;padding:1.5rem;background:#f4f7f8;color:#17333b}
        form{display:grid;gap:.9rem}input,button{font:inherit;padding:.75rem;border-radius:.5rem;border:1px solid #b6c9cb}button{background:#087b73;color:white;cursor:pointer}</style>
        <h1>MASGuardEval</h1><p>Sign in to your private traces and reports.</p><form id="login">
        <label>Email <input type="email" name="email" required autocomplete="username"></label>
        <label>Password <input type="password" name="password" required autocomplete="current-password"></label>
        <button>Sign in</button><button type="button" id="register">Create account</button></form>
        <p><a href="/user-recover">Forgot your password?</a></p><p id="message" role="alert"></p><script>
        const form=document.getElementById('login');const message=document.getElementById('message');
        async function submit(path){const body=Object.fromEntries(new FormData(form));const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        if(response.ok){if(path==='/user-login')location.replace('/');else message.textContent='Check your email to confirm your account, then sign in.';}
        else message.textContent=path==='/user-login'?'Sign in failed. Check your account details.':'Registration failed.';}
        form.addEventListener('submit',event=>{event.preventDefault();submit('/user-login')});
        document.getElementById('register').addEventListener('click',()=>submit('/user-register'));</script></html>"""
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    @app.post("/user-login", include_in_schema=False)
    async def user_login(request: Request) -> Response:
        try:
            payload = await request.json()
        except ValueError:
            payload = {}
        email = payload.get("email") if isinstance(payload, dict) else None
        password = payload.get("password") if isinstance(payload, dict) else None
        if not isinstance(email, str) or not isinstance(password, str) or len(email) > 254 or len(password) > 1024:
            return JSONResponse({"detail": "Invalid sign-in request"}, status_code=422)
        try:
            session = await asyncio.to_thread(auth.password_login, email, password)
        except AuthError:
            return JSONResponse({"detail": "Sign in failed"}, status_code=401)
        response = Response(status_code=204, headers={"Cache-Control": "no-store"})
        _set_user_cookies(response, session)
        return response

    @app.post("/user-register", include_in_schema=False)
    async def user_register(request: Request) -> Response:
        try:
            payload = await request.json()
        except ValueError:
            payload = {}
        email = payload.get("email") if isinstance(payload, dict) else None
        password = payload.get("password") if isinstance(payload, dict) else None
        if not isinstance(email, str) or not isinstance(password, str) or len(email) > 254 or not 8 <= len(password) <= 1024:
            return JSONResponse({"detail": "Invalid registration request"}, status_code=422)
        try:
            await asyncio.to_thread(auth.register, email, password)
        except AuthError:
            return JSONResponse({"detail": "Registration failed"}, status_code=400)
        return Response(status_code=202, headers={"Cache-Control": "no-store"})

    @app.get("/user-recover", include_in_schema=False)
    def user_recover_page() -> HTMLResponse:
        html = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
        <title>Reset password | MASGuardEval</title><style>body{font:16px system-ui;max-width:27rem;margin:8vh auto;padding:1.5rem;background:#f4f7f8;color:#17333b}
        form{display:grid;gap:.9rem}input,button{font:inherit;padding:.75rem;border-radius:.5rem;border:1px solid #b6c9cb}button{background:#087b73;color:white;cursor:pointer}</style>
        <h1>Reset password</h1><p>Enter your account email. If an account exists, we will send a reset link.</p>
        <form id="recover"><label>Email <input type="email" name="email" required autocomplete="email"></label><button>Send reset link</button></form>
        <p id="message" role="status"></p><p><a href="/user-login">Back to sign in</a></p><script>
        document.getElementById('recover').addEventListener('submit',async event=>{event.preventDefault();
        const email=new FormData(event.target).get('email');const response=await fetch('/user-recover',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email})});
        document.getElementById('message').textContent=response.ok?'If an account exists, check its email for a reset link.':'Unable to request a reset right now.';});</script></html>"""
        return HTMLResponse(html, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})

    @app.post("/user-recover", include_in_schema=False)
    async def user_recover(request: Request) -> Response:
        try:
            payload = await request.json()
        except ValueError:
            payload = {}
        email = payload.get("email") if isinstance(payload, dict) else None
        if not isinstance(email, str) or len(email) > 254 or "@" not in email:
            return JSONResponse({"detail": "Invalid email"}, status_code=422)
        try:
            await asyncio.to_thread(auth.request_recovery, email, PUBLIC_ORIGIN + "/user-reset")
        except AuthError:
            # Match the response for unknown accounts and provider-side rate limits.
            pass
        return Response(status_code=202, headers={"Cache-Control": "no-store"})

    @app.get("/user-reset", include_in_schema=False)
    def user_reset_page() -> HTMLResponse:
        html = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
        <title>Choose a new password | MASGuardEval</title><style>body{font:16px system-ui;max-width:27rem;margin:8vh auto;padding:1.5rem;background:#f4f7f8;color:#17333b}
        form{display:grid;gap:.9rem}input,button{font:inherit;padding:.75rem;border-radius:.5rem;border:1px solid #b6c9cb}button{background:#087b73;color:white;cursor:pointer}</style>
        <h1>Choose a new password</h1><form id="reset"><label>New password <input type="password" name="password" required minlength="8" autocomplete="new-password"></label>
        <button>Update password</button></form><p id="message" role="alert"></p><p><a href="/user-login">Back to sign in</a></p><script>
        const params=new URLSearchParams(location.hash.slice(1));const token=params.get('access_token');
        history.replaceState(null,'',location.pathname);if(!token)document.getElementById('message').textContent='Reset link is missing or expired. Request a new one.';
        document.getElementById('reset').addEventListener('submit',async event=>{event.preventDefault();if(!token)return;
        const password=new FormData(event.target).get('password');const response=await fetch('/user-reset',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({access_token:token,password})});
        if(response.ok){document.getElementById('message').textContent='Password updated. Sign in with your new password.';event.target.reset();}
        else document.getElementById('message').textContent='Reset failed. Request a new link and try again.';});</script></html>"""
        return HTMLResponse(html, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})

    @app.post("/user-reset", include_in_schema=False)
    async def user_reset(request: Request) -> Response:
        try:
            payload = await request.json()
        except ValueError:
            payload = {}
        token = payload.get("access_token") if isinstance(payload, dict) else None
        password = payload.get("password") if isinstance(payload, dict) else None
        if (not isinstance(token, str) or not 16 <= len(token) <= 8192
                or not isinstance(password, str) or not 8 <= len(password) <= 1024):
            return JSONResponse({"detail": "Invalid reset request"}, status_code=422)
        try:
            await asyncio.to_thread(auth.user, token)
            await asyncio.to_thread(auth.update_password, token, password)
        except AuthError:
            return JSONResponse({"detail": "Reset link expired or invalid"}, status_code=401)
        response = Response(status_code=204, headers={"Cache-Control": "no-store"})
        response.delete_cookie(USER_ACCESS_COOKIE)
        response.delete_cookie(USER_REFRESH_COOKIE)
        return response

    @app.post("/user-logout", include_in_schema=False)
    def user_logout(request: Request) -> Response:
        access = request.cookies.get(USER_ACCESS_COOKIE)
        if access:
            try:
                auth.logout(access)
            except AuthError:
                pass
        response = Response(status_code=204, headers={"Cache-Control": "no-store"})
        response.delete_cookie(USER_ACCESS_COOKIE)
        response.delete_cookie(USER_REFRESH_COOKIE)
        return response

    @app.get("/user-session", include_in_schema=False)
    def user_session(request: Request) -> dict[str, object]:
        return {"enabled": True, "email": request.state.user_email}


FRONTEND_DIST = Path(os.environ.get("MASGUARDEVAL_FRONTEND_DIST", str(ROOT / "frontend" / "dist")))
app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="dashboard")
