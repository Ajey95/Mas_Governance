"""Per-user dashboard access must scope saved traces at the API boundary."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from masguardeval.user_auth import SupabaseAuth


BACKEND = Path(__file__).resolve().parents[1]


def test_supabase_auth_uses_publishable_key_and_auth_server(monkeypatch):
    requests = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def read(self):
            return b'{"id":"user-a","email":"a@example.test"}'

    def fake_urlopen(request, timeout):
        requests.append((request.full_url, request.headers, timeout))
        return Response()

    monkeypatch.setattr("masguardeval.user_auth.urlopen", fake_urlopen)
    user = SupabaseAuth("https://example.supabase.co", "sb_publishable_test").user("fictional-jwt")
    assert user["id"] == "user-a"
    assert requests[0][0] == "https://example.supabase.co/auth/v1/user"
    assert requests[0][1]["Authorization"] == "Bearer fictional-jwt"
    assert requests[0][1]["Apikey"] == "sb_publishable_test"


def test_recovery_uses_supabase_auth_and_fixed_https_redirect(monkeypatch):
    requests = []

    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self): return b'{}'

    def fake_urlopen(request, timeout):
        requests.append(request)
        return Response()

    monkeypatch.setattr("masguardeval.user_auth.urlopen", fake_urlopen)
    bridge = SupabaseAuth("https://example.supabase.co", "sb_publishable_test")
    bridge.request_recovery("a@example.test", "https://masguardeval.onrender.com/user-reset")
    bridge.update_password("fictional-recovery-token", "fictional-new-password")
    assert requests[0].full_url == ("https://example.supabase.co/auth/v1/recover?"
                                    "redirect_to=https%3A%2F%2Fmasguardeval.onrender.com%2Fuser-reset")
    assert requests[0].get_method() == "POST"
    assert requests[1].full_url == "https://example.supabase.co/auth/v1/user"
    assert requests[1].get_method() == "PUT"
    assert requests[1].headers["Authorization"] == "Bearer fictional-recovery-token"


def test_authenticated_routes_do_not_cross_user_boundaries(tmp_path: Path):
    (tmp_path / "index.html").write_text("<h1>Dashboard</h1>", encoding="utf-8")
    environment = {**os.environ, "PYTHONPATH": str(BACKEND) + os.pathsep + os.environ.get("PYTHONPATH", ""),
                   "MASGUARDEVAL_FRONTEND_DIST": str(tmp_path)}
    for name in ("MASGUARDEVAL_DATABASE_URL", "MASGUARDEVAL_REQUIRE_USER_AUTH",
                 "MASGUARDEVAL_REQUIRE_SITE_AUTH", "MASGUARDEVAL_SITE_TOKEN"):
        environment.pop(name, None)
    script = """
import os
from fastapi.testclient import TestClient
from masguardeval import api
from masguardeval.store import PostgresTraceStore
from masguardeval.user_auth import AuthError

os.environ['MASGUARDEVAL_DATABASE_URL'] = 'postgresql://fictional.invalid/db'
os.environ['MASGUARDEVAL_REQUIRE_USER_AUTH'] = '1'
os.environ['MASGUARDEVAL_REQUIRE_SITE_AUTH'] = '1'
os.environ['MASGUARDEVAL_SITE_TOKEN'] = 'fictional-site-token'
os.environ['MASGUARDEVAL_SUPABASE_URL'] = 'https://example.supabase.co'
os.environ['MASGUARDEVAL_SUPABASE_PUBLISHABLE_KEY'] = 'sb_publishable_test'
store = object.__new__(PostgresTraceStore)
store.list = lambda limit, owner_id=None: [{'trace_id': owner_id + '-trace'}]
store.get = lambda trace_id, owner_id=None: {'trace_id': trace_id} if trace_id == owner_id + '-trace' else None
api.trace_store = store
from masguardeval import web

class FakeAuth:
    def password_login(self, email, password):
        if password != 'fictional-password': raise AuthError('bad')
        owner = email.split('@')[0]
        return {'access_token': owner + '-access', 'refresh_token': owner + '-refresh', 'expires_in': 3600}
    def user(self, token):
        if token not in ('alice-access', 'bob-access', 'alice-recovery-token'): raise AuthError('bad')
        owner = token.split('-')[0]
        return {'id': owner, 'email': owner + '@example.test'}
    def refresh(self, token):
        if token != 'alice-refresh': raise AuthError('bad')
        return {'access_token': 'alice-access', 'refresh_token': 'alice-refresh', 'expires_in': 3600}
    def logout(self, token): pass
    def request_recovery(self, email, redirect_url):
        assert redirect_url == 'https://masguardeval.onrender.com/user-reset'
    def update_password(self, token, password):
        assert token == 'alice-recovery-token' and password == 'fictional-new-password'
web.auth = FakeAuth()

alice = TestClient(web.app, base_url='https://testserver')
bob = TestClient(web.app, base_url='https://testserver')
assert alice.get('/runs').status_code == 401
assert alice.post('/user-login', json={'email':'alice@example.test','password':'fictional-password'}).status_code == 401
assert alice.post('/site-login', json={'token':'fictional-site-token'}).status_code == 204
assert bob.post('/site-login', json={'token':'fictional-site-token'}).status_code == 204
assert alice.get('/user-recover').status_code == 200
assert alice.post('/user-recover', json={'email':'alice@example.test'}).status_code == 202
assert 'Forgot your password?' in alice.get('/user-login').text
assert alice.get('/user-reset').status_code == 200
assert alice.post('/user-reset', json={'access_token':'bad','password':'fictional-new-password'}).status_code == 422
assert alice.post('/user-reset', json={'access_token':'alice-recovery-token','password':'fictional-new-password'}).status_code == 204
assert alice.post('/user-login', json={'email':'alice@example.test','password':'fictional-password'}).status_code == 204
assert bob.post('/user-login', json={'email':'bob@example.test','password':'fictional-password'}).status_code == 204
assert alice.get('/runs').json()[0]['trace_id'] == 'alice-trace'
assert bob.get('/runs').json()[0]['trace_id'] == 'bob-trace'
assert alice.get('/runs/bob-trace').status_code == 404
assert bob.get('/runs/alice-trace').status_code == 404
assert alice.get('/user-session').json()['email'] == 'alice@example.test'
assert alice.post('/user-logout').status_code == 204
assert alice.get('/runs').status_code == 401
"""
    result = subprocess.run([sys.executable, "-c", script], env=environment,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
