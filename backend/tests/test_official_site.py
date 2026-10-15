from fastapi.testclient import TestClient

from masguardeval.official_site import app


def test_public_site_serves_guides_without_evaluation_api():
    client = TestClient(app)
    for path in ("/", "/docs/", "/tutorials/", "/examples/", "/method/"):
        response = client.get(path)
        assert response.status_code == 200
        assert "MASGuardEval" in response.text
    assert client.get("/health").json()["surface"] == "official_site"
    for path in ("/dashboard", "/runs", "/scenarios", "/user-login", "/openapi.json"):
        assert client.get(path).status_code == 404
    assert client.post("/langgraph/nested-probe").status_code in (404, 405)
