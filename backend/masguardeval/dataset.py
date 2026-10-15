from __future__ import annotations

import json
from pathlib import Path

from .models import Scenario


class GoldenDataset:
    """JSON-backed golden dataset loader with domain validation."""

    def __init__(self, scenarios: list[Scenario]) -> None:
        self.scenarios = scenarios
        self._by_id = {scenario.scenario_id: scenario for scenario in scenarios}
        if len(self._by_id) != len(scenarios):
            raise ValueError("Duplicate scenario_id values found in golden dataset")

    @classmethod
    def load(cls, path: str | Path) -> "GoldenDataset":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        scenarios = [Scenario.from_dict(item) for item in payload["scenarios"]]
        dataset = cls(scenarios)
        dataset.validate()
        return dataset

    def validate(self) -> None:
        required_metrics = {"TSP", "TSR", "PHR", "CPI", "CFP", "RSS", "CCR", "DT"}
        if not self.scenarios:
            raise ValueError("Golden dataset must contain at least one scenario")
        for scenario in self.scenarios:
            if not scenario.scenario_id or not scenario.prompt or not scenario.expected_safe_behavior:
                raise ValueError("Scenarios require a nonempty ID, prompt, and expected safe behavior")
            unknown_metrics = set(scenario.metrics) - required_metrics
            if unknown_metrics:
                raise ValueError(f"{scenario.scenario_id} has unknown metrics: {sorted(unknown_metrics)}")
            overlap = set(scenario.allowed_tools) & set(scenario.blocked_tools)
            if overlap:
                raise ValueError(f"{scenario.scenario_id} allows and blocks the same tools: {sorted(overlap)}")
            unavailable = set(scenario.required_tools) - set(scenario.allowed_tools)
            if unavailable:
                raise ValueError(f"{scenario.scenario_id} requires tools outside its allowlist: {sorted(unavailable)}")
            for tool, schema in scenario.parameter_schema.items():
                invalid_required = set(schema.get("required_keys", [])) - set(schema.get("allowed_keys", []))
                if invalid_required:
                    raise ValueError(f"{scenario.scenario_id} schema for {tool} requires disallowed parameters: {sorted(invalid_required)}")
                max_calls = schema.get("max_calls")
                if max_calls is not None and (isinstance(max_calls, bool) or not isinstance(max_calls, int) or max_calls < 1):
                    raise ValueError(f"{scenario.scenario_id} schema for {tool} needs positive max_calls")
                properties = schema.get("properties", {})
                if not isinstance(properties, dict):
                    raise ValueError(f"{scenario.scenario_id} schema for {tool} needs object properties")
                for key, rule in properties.items():
                    if not isinstance(rule, dict):
                        raise ValueError(f"{scenario.scenario_id} schema for {tool}.{key} needs an object rule")
                    if "enum" in rule and (not isinstance(rule["enum"], list) or not rule["enum"]):
                        raise ValueError(f"{scenario.scenario_id} schema for {tool}.{key} needs nonempty enum")
                    length = rule.get("max_length")
                    if length is not None and (isinstance(length, bool) or not isinstance(length, int) or length < 1):
                        raise ValueError(f"{scenario.scenario_id} schema for {tool}.{key} needs positive max_length")
            unknown_policies = set(scenario.attribute_policies) - set(scenario.allowed_tools)
            if unknown_policies:
                raise ValueError(f"{scenario.scenario_id} has attribute policies for unavailable tools: {sorted(unknown_policies)}")
            for tool, rule in scenario.attribute_policies.items():
                if not isinstance(rule, dict) or not isinstance(rule.get("subject", {}), dict) or not isinstance(rule.get("resource", {}), dict) or not isinstance(rule.get("match", []), list):
                    raise ValueError(f"{scenario.scenario_id} has invalid attribute policy for {tool}")
            invalid_high_risk = set(scenario.high_risk_tools) - (set(scenario.allowed_tools) | set(scenario.blocked_tools))
            if invalid_high_risk:
                raise ValueError(f"{scenario.scenario_id} marks unavailable tools high-risk: {sorted(invalid_high_risk)}")
            invalid_sensitive = set(scenario.sensitive_tools) - (set(scenario.allowed_tools) | set(scenario.blocked_tools))
            if invalid_sensitive:
                raise ValueError(f"{scenario.scenario_id} marks unavailable tools sensitive: {sorted(invalid_sensitive)}")
            fixture = scenario.workspace_fixture
            if not isinstance(fixture, dict) or set(fixture) - {"files", "emails", "memory", "shell_response", "shell_responses", "job_response"}:
                raise ValueError(f"{scenario.scenario_id} has invalid workspace fixture keys")
            for field_name in ("files", "memory"):
                values = fixture.get(field_name, {})
                if not isinstance(values, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in values.items()):
                    raise ValueError(f"{scenario.scenario_id} fixture {field_name} must map strings to strings")
            emails = fixture.get("emails", [])
            email_fields = {"id", "date", "sender", "subject", "body"}
            if not isinstance(emails, list) or any(
                not isinstance(email, dict) or not email_fields <= set(email)
                or not all(isinstance(email[field_name], str) for field_name in email_fields)
                for email in emails
            ):
                raise ValueError(f"{scenario.scenario_id} fixture email needs id, date, sender, subject, and body strings")
            if len({email["id"] for email in emails}) != len(emails):
                raise ValueError(f"{scenario.scenario_id} fixture email IDs must be unique")
            for field_name in ("shell_response", "job_response"):
                if field_name in fixture and not isinstance(fixture[field_name], str):
                    raise ValueError(f"{scenario.scenario_id} fixture {field_name} must be a string")
            shell_responses = fixture.get("shell_responses", {})
            if not isinstance(shell_responses, dict) or not all(
                isinstance(command, str) and isinstance(response, str)
                for command, response in shell_responses.items()
            ):
                raise ValueError(f"{scenario.scenario_id} fixture shell_responses must map strings to strings")
            for event in scenario.reference_events:
                if not isinstance(event, dict) or event.get("event_type") not in {"agent_step", "tool_call", "inter_agent_message", "memory_operation"} or not event.get("agent") or not event.get("action"):
                    raise ValueError(f"{scenario.scenario_id} has an invalid reference event")
                if event["event_type"] == "tool_call" and event.get("tool") not in set(scenario.allowed_tools) | set(scenario.blocked_tools):
                    raise ValueError(f"{scenario.scenario_id} references an undeclared tool")

    def get(self, scenario_id: str) -> Scenario:
        try:
            return self._by_id[scenario_id]
        except KeyError as exc:
            raise KeyError(f"Unknown scenario_id: {scenario_id}") from exc

    def to_dict(self) -> dict[str, list[dict[str, object]]]:
        return {"scenarios": [scenario.to_dict() for scenario in self.scenarios]}
