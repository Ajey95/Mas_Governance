from fastapi.testclient import TestClient

from masguardeval.official_site import GUIDES, app


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


def test_public_guides_render_current_markdown_with_internal_navigation():
    client = TestClient(app)
    for slug in GUIDES:
        response = client.get(f"/docs/{slug}/")
        assert response.status_code == 200
        assert 'class="guide-body"' in response.text
        assert 'aria-label="Guide contents"' in response.text
    home = client.get("/docs/overview/").text
    assert 'href="/docs/quickstart/"' in home
    assert 'href="/docs/sdk/#run-your-agent-from-the-cli"' in home
    assert 'href="https://github.com/Ajey95/Mas_Governance/blob/main/examples/README.md"' in home
    assert client.get("/docs/unknown/").status_code == 404
    assert client.get("/docs/openapi.json").status_code == 404


def test_public_site_explains_offline_task_review_without_exposing_private_packet():
    response = TestClient(app).get("/docs/task-review/")
    assert response.status_code == 200
    assert "Offline task review form" in response.text
    assert "independent" in response.text
    assert "datasets/task_review_packet_v3/offline_review_form.html" in response.text
