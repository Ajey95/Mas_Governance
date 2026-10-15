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
        if token not in ('alice-access', 'bob-access'): raise AuthError('bad')
        owner = token.split('-')[0]
        return {'id': owner, 'email': owner + '@example.test'}
    def refresh(self, token):
        if token != 'alice-refresh': raise AuthError('bad')
        return {'access_token': 'alice-access', 'refresh_token': 'alice-refresh', 'expires_in': 3600}
    def logout(self, token): pass
web.auth = FakeAuth()

alice = TestClient(web.app, base_url='https://testserver')
bob = TestClient(web.app, base_url='https://testserver')
assert alice.get('/runs').status_code == 401
assert alice.post('/user-login', json={'email':'alice@example.test','password':'fictional-password'}).status_code == 401
assert alice.post('/site-login', json={'token':'fictional-site-token'}).status_code == 204
assert bob.post('/site-login', json={'token':'fictional-site-token'}).status_code == 204
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
