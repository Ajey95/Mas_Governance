from fastapi.testclient import TestClient

from masguardeval.api import app


def test_local_api_keeps_swagger_and_removes_project_docs():
    client = TestClient(app)
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json")
    assert schema.status_code == 200
    assert schema.json()["info"]["title"] == "MASGuardEval API"
    assert client.get("/project-docs").status_code == 404
    assert client.get("/project-docs/README.md").status_code == 404
