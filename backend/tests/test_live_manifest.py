import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "run_live_experiment.py"
SPEC = importlib.util.spec_from_file_location("run_live_experiment", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_provider_endpoint_does_not_store_url_credentials_or_query():
    assert MODULE.endpoint_identity("https://user:secret@model.example:8443/v1?token=secret") == "https://model.example:8443"
    assert set(MODULE.source_hashes()) == {
        "backend/masguardeval/runner.py", "backend/masguardeval/live.py",
        "backend/masguardeval/guards.py", "backend/masguardeval/metrics.py",
        "backend/masguardeval/models.py", "backend/masguardeval/dataset.py",
        "backend/masguardeval/workspace.py",
    }
