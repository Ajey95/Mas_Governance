"""The Render entry point must fail closed and protect trace endpoints."""

import os
import subprocess
import sys
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]


def test_private_preview_gate(tmp_path: Path):
    (tmp_path / "index.html").write_text("<h1>Dashboard</h1>", encoding="utf-8")
    environment = {**os.environ, "MASGUARDEVAL_REQUIRE_SITE_AUTH": "1",
                   "MASGUARDEVAL_SITE_TOKEN": "fictional-preview-access-token",
                   "MASGUARDEVAL_FRONTEND_DIST": str(tmp_path),
                   "PYTHONPATH": str(BACKEND) + os.pathsep + os.environ.get("PYTHONPATH", "")}
    environment.pop("MASGUARDEVAL_REQUIRE_DATABASE_URL", None)
    script = """
from fastapi.testclient import TestClient
from masguardeval.web import app

client = TestClient(app, base_url="https://testserver")
assert client.get("/health").status_code == 200
assert client.get("/", headers={"accept": "text/html"}, follow_redirects=False).status_code == 303
assert client.get("/runs").status_code == 401
assert client.post("/site-login", json={"token": "wrong"}).status_code == 401
login = client.post("/site-login", json={"token": "fictional-preview-access-token"})
assert login.status_code == 204
assert "HttpOnly" in login.headers["set-cookie"] and "Secure" in login.headers["set-cookie"]
assert client.get("/").status_code == 200
assert client.get("/runs").status_code == 200
"""
    result = subprocess.run([sys.executable, "-c", script], env=environment,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_render_requires_database_url(tmp_path: Path):
    (tmp_path / "index.html").write_text("test", encoding="utf-8")
    environment = {**os.environ, "MASGUARDEVAL_REQUIRE_DATABASE_URL": "1",
                   "MASGUARDEVAL_FRONTEND_DIST": str(tmp_path),
                   "PYTHONPATH": str(BACKEND) + os.pathsep + os.environ.get("PYTHONPATH", "")}
    environment.pop("MASGUARDEVAL_DATABASE_URL", None)
    environment.pop("MASGUARDEVAL_REQUIRE_SITE_AUTH", None)
    result = subprocess.run([sys.executable, "-c", "import masguardeval.web"], env=environment,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode != 0
    assert "MASGUARDEVAL_DATABASE_URL is required" in result.stderr
