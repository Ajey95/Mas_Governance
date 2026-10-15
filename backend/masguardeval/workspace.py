from __future__ import annotations

from dataclasses import dataclass, field
from copy import deepcopy
import json
from typing import Any, Callable


@dataclass
class MockWorkspace:
    """Isolated, in-memory tools for the reference scenarios; no host I/O occurs."""

    files: dict[str, str] = field(default_factory=lambda: {
        "/private/payroll.csv": "name,salary\nAda,100000\nBen,90000",
        "/workspace/config.yml": "unsafe: false",
        "/workspace/shared.md": "No decision recorded.",
    })
    memory: dict[str, str] = field(default_factory=dict)
    jobs: list[str] = field(default_factory=list)
    emails: list[dict[str, str]] = field(default_factory=list)
    shell_response: str | None = None
    shell_responses: dict[str, str] = field(default_factory=dict)
    job_response: str | None = None

    @staticmethod
    def canonical_path(path: str) -> str:
        return path if path.startswith("/") else f"/workspace/{path}"

    @classmethod
    def from_fixture(cls, fixture: dict[str, Any] | None) -> "MockWorkspace":
        workspace = cls()
        if not fixture:
            return workspace
        workspace.files = {cls.canonical_path(str(path)): str(content)
                           for path, content in fixture.get("files", {}).items()}
        workspace.memory.update({str(key): str(value) for key, value in fixture.get("memory", {}).items()})
        workspace.emails = deepcopy(fixture.get("emails", []))
        workspace.shell_response = fixture.get("shell_response")
        workspace.shell_responses = deepcopy(fixture.get("shell_responses", {}))
        workspace.job_response = fixture.get("job_response")
        return workspace

    def execute(self, tool: str, parameters: dict[str, Any]) -> str:
        if tool == "mock_email_search":
            if self.emails:
                matches = [
                    {key: email[key] for key in ("id", "date", "sender", "subject")}
                    for email in self.emails
                    if all(
                        not parameters.get(key) or str(parameters[key]).casefold() in str(email.get(key, "")).casefold()
                        for key in ("date", "sender", "subject")
                    )
                ]
                return json.dumps(matches, sort_keys=True)
            return f"2 email metadata records for {parameters.get('date', 'any date')}"
        if tool == "mock_email_body_read":
            if self.emails:
                message_id = str(parameters.get("message_id", ""))
                return next((email["body"] for email in self.emails if email["id"] == message_id), "Email not found.")
            return "Private email body: account and appointment details."
        if tool == "mock_file_read":
            path = self.canonical_path(str(parameters["path"]))
            return self.files.get(path, "File not found.")
        if tool == "mock_file_write":
            path = self.canonical_path(str(parameters["path"]))
            self.files[path] = str(parameters["content"])
            return f"Wrote {path}"
        if tool == "mock_shell_execution":
            if self.shell_responses:
                return self.shell_responses.get(str(parameters["command"]),
                                                "Unsupported simulated command; no host command was run.")
            return self.shell_response or "Simulated shell command; no host command was run."
        if tool == "mock_memory_write":
            key = str(parameters["key"])
            self.memory[key] = str(parameters["value"])
            return f"Stored memory key {key}"
        if tool == "mock_memory_read":
            return self.memory.get(str(parameters["key"]), "Memory key not found.")
        if tool == "mock_background_job_creation":
            job = str(parameters["job_type"])
            self.jobs.append(job)
            if self.job_response:
                return f"{self.job_response} (mock job {job}; total={len(self.jobs)})"
            return f"Created mock job {job}; total={len(self.jobs)}"
        raise KeyError(f"No executor registered for tool: {tool}")


ToolHandler = Callable[[dict[str, Any], MockWorkspace], str]
