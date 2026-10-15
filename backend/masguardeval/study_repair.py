"""Technical adaptation of a submitted draft, with changes kept auditable."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .study import canonical_hash


REQUIRED_TOOL_KEYS = {
    "mock_email_search": [],
    "mock_email_body_read": ["message_id"],
    "mock_file_read": ["path"],
    "mock_file_write": ["path", "content"],
    "mock_shell_execution": ["command"],
    "mock_memory_write": ["key", "value"],
    "mock_memory_read": ["key"],
    "mock_background_job_creation": ["job_type"],
}


def repair_submitted_draft(
    payload: dict[str, Any], fixtures: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Convert executable fields without rewriting submitted prompts or rubrics.

    Ambiguous natural-language policies are retained in the manifest for human
    review rather than being silently promoted to enforcement rules.
    """
    if not isinstance(payload.get("scenarios"), list):
        raise ValueError("Submitted draft needs a scenarios list")
    rows = payload["scenarios"]
    ids = {str(row["scenario_id"]) for row in rows}
    unknown_fixtures = set(fixtures) - ids
    if unknown_fixtures:
        raise ValueError(f"Fixture IDs do not match submitted scenarios: {sorted(unknown_fixtures)}")
    repaired = deepcopy(payload)
    notes: dict[str, Any] = {}
    resource_notes: dict[str, Any] = {}
    for row in repaired["scenarios"]:
        scenario_id = str(row["scenario_id"])
        schemas: dict[str, Any] = {}
        for tool, schema in row.get("parameter_schema", {}).items():
            if not schema:
                schemas[tool] = {}
                continue
            if "allowed_keys" in schema:
                schemas[tool] = schema
                continue
            allowed = sorted(set(schema) | set(REQUIRED_TOOL_KEYS.get(tool, [])))
            schemas[tool] = {
                "allowed_keys": allowed,
                "required_keys": REQUIRED_TOOL_KEYS.get(tool, []),
                "properties": deepcopy(schema),
            }
        row["parameter_schema"] = schemas
        old_policies = row.get("attribute_policies", {})
        if old_policies and not set(old_policies) <= set(row.get("allowed_tools", [])):
            notes[scenario_id] = deepcopy(old_policies)
            row["attribute_policies"] = {}
        old_resource = row.get("resource_attributes", {})
        if old_resource:
            resource_notes[scenario_id] = deepcopy(old_resource)
        fixture = deepcopy(fixtures.get(scenario_id, {}))
        row["workspace_fixture"] = {key: value for key, value in fixture.items() if key != "resource_attributes"}
        row["resource_attributes"] = deepcopy(fixture.get("resource_attributes", {}))
    repaired["source"] = "Submitted task text with technical schema and mock-fixture adaptation; review pending"
    manifest = {
        "input_canonical_sha256": canonical_hash(payload),
        "output_canonical_sha256": canonical_hash(repaired),
        "scenario_count": len(rows),
        "original_prompts_and_safe_behavior_preserved": all(
            old["prompt"] == new["prompt"] and old["expected_safe_behavior"] == new["expected_safe_behavior"]
            for old, new in zip(rows, repaired["scenarios"])
        ),
        "policy_notes_pending_human_review": notes,
        "resource_notes_pending_human_review": resource_notes,
        "fixture_ids": sorted(fixtures),
        "fixture_provenance": "agent_authored_mock_fixture_pending_human_review",
        "authorship_claim_verified_by_software": False,
        "review_required_before_freeze": True,
    }
    return repaired, manifest
