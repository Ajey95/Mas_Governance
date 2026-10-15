"""Verify that every declared mock fixture is observable and isolated."""

from __future__ import annotations

import argparse

from masguardeval import GoldenDataset
from masguardeval.workspace import MockWorkspace


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    args = parser.parse_args()
    dataset = GoldenDataset.load(args.dataset)
    probes = 0
    for scenario in dataset.scenarios:
        fixture = scenario.workspace_fixture
        workspace = MockWorkspace.from_fixture(fixture)
        for path, content in fixture.get("files", {}).items():
            observed = workspace.execute("mock_file_read", {"path": path})
            if observed != content:
                raise ValueError(f"{scenario.scenario_id}: file fixture {path} is not observable")
            probes += 1
        for email in fixture.get("emails", []):
            metadata = workspace.execute("mock_email_search", {"date": email["date"]})
            body = workspace.execute("mock_email_body_read", {"message_id": email["id"]})
            if email["id"] not in metadata or body != email["body"]:
                raise ValueError(f"{scenario.scenario_id}: email fixture {email['id']} is not observable")
            probes += 2
        for key, value in fixture.get("memory", {}).items():
            if workspace.execute("mock_memory_read", {"key": key}) != value:
                raise ValueError(f"{scenario.scenario_id}: memory fixture {key} is not observable")
            probes += 1
        if fixture.get("shell_response"):
            if workspace.execute("mock_shell_execution", {"command": "mock diagnostic"}) != fixture["shell_response"]:
                raise ValueError(f"{scenario.scenario_id}: shell fixture is not observable")
            probes += 1
        for command, response in fixture.get("shell_responses", {}).items():
            if workspace.execute("mock_shell_execution", {"command": command}) != response:
                raise ValueError(f"{scenario.scenario_id}: shell fixture {command} is not observable")
            probes += 1
        if fixture.get("job_response"):
            result = workspace.execute("mock_background_job_creation", {"job_type": "smoke"})
            if fixture["job_response"] not in result:
                raise ValueError(f"{scenario.scenario_id}: job fixture is not observable")
            probes += 1
        for key in scenario.resource_attributes:
            if key.startswith("/") and key not in workspace.files:
                raise ValueError(f"{scenario.scenario_id}: resource attributes name missing file {key}")
    print(f"Verified {probes} fixture observations across {len(dataset.scenarios)} scenarios")


if __name__ == "__main__":
    main()
