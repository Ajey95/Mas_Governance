"""Blank study intake and checks that run before independent task review."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .dataset import GoldenDataset
from .models import Scenario
from .study import RISK_TYPES


METRICS = ["TSP", "TSR", "PHR", "CPI", "CFP", "RSS", "CCR", "DT"]
AVAILABLE_TOOLS = {
    "mock_email_search", "mock_email_body_read", "mock_file_read",
    "mock_file_write", "mock_shell_execution", "mock_memory_write",
    "mock_memory_read", "mock_background_job_creation",
}


def build_blank_intake(tasks_per_risk: int = 5) -> dict[str, Any]:
    if tasks_per_risk < 1:
        raise ValueError("tasks_per_risk must be positive")
    scenarios = []
    for risk in sorted(RISK_TYPES):
        for index in range(1, tasks_per_risk + 1):
            scenarios.append({
                "scenario_id": f"draft_{risk}_{index:02d}",
                "source_case_study": "",
                "risk_type": risk,
                "user_role": "",
                "prompt": "",
                "expected_safe_behavior": "",
                "allowed_tools": [],
                "blocked_tools": [],
                "required_tools": [],
                "authorized_roles": [],
                "parameter_schema": {},
                "subject_attributes": {},
                "attribute_policies": {},
                "high_risk_tools": [],
                "sensitive_tools": [],
                "resource_attributes": {},
                "reference_events": [],
                "provenance": "unverified_author_draft",
                "metrics": METRICS.copy(),
                "tags": [],
            })
    return {
        "version": "0.1.0-intake-blank",
        "domain": "software_workspace_assistant",
        "source": "Blank authoring slots; no tasks, labels, or human authorship claims supplied",
        "scenarios": scenarios,
    }


def _normalized_prompt(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def _known_prompts(paths: list[str | Path]) -> set[str]:
    prompts: set[str] = set()
    for path in paths:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        prompts.update(
            _normalized_prompt(str(item.get("prompt", "")))
            for item in payload.get("scenarios", [])
            if str(item.get("prompt", "")).strip()
        )
    return prompts


def preflight_draft(payload: dict[str, Any], *, known_datasets: list[str | Path] | None = None) -> dict[str, Any]:
    """Report readiness for review without claiming to verify author identity."""
    if not isinstance(payload, dict):
        raise ValueError("Dataset must be a JSON object")
    rows = payload.get("scenarios")
    if not isinstance(rows, list):
        raise ValueError("Dataset must contain a scenarios list")
    issues: list[str] = []
    risk_counts: Counter[str] = Counter()
    risk_families: dict[str, set[str]] = defaultdict(set)
    family_risks: dict[str, set[str]] = defaultdict(set)
    source_families: dict[str, set[str]] = defaultdict(set)
    ids: Counter[str] = Counter()
    prompts: Counter[str] = Counter()
    known_prompts = _known_prompts(known_datasets or [])
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            issues.append(f"Row {index}: scenario must be an object")
            continue
        scenario_id = str(row.get("scenario_id", "")).strip()
        label = scenario_id or f"row {index}"
        ids[scenario_id] += 1
        for field in ("scenario_id", "source_case_study", "user_role", "prompt", "expected_safe_behavior"):
            if not str(row.get(field, "")).strip():
                issues.append(f"{label}: {field} is blank")
        risk = str(row.get("risk_type", ""))
        if risk not in RISK_TYPES:
            issues.append(f"{label}: unknown risk_type {risk!r}")
        else:
            risk_counts[risk] += 1
        tags = row.get("tags", [])
        families = [tag[7:] for tag in tags if isinstance(tag, str) and tag.startswith("family:") and tag[7:]] if isinstance(tags, list) else []
        if len(families) != 1:
            issues.append(f"{label}: exactly one nonempty family: tag is required")
        elif risk in RISK_TYPES:
            risk_families[risk].add(families[0])
            family_risks[families[0]].add(risk)
            source = str(row.get("source_case_study", "")).casefold().strip()
            if source:
                source_families[source].add(families[0])
        if row.get("provenance") != "independent_human_authored":
            issues.append(f"{label}: independent human authorship has not been declared")
        tools = row.get("allowed_tools", [])
        blocked = row.get("blocked_tools", [])
        if not isinstance(tools, list) or not isinstance(blocked, list) or not all(isinstance(tool, str) for tool in tools + blocked):
            issues.append(f"{label}: allowed_tools and blocked_tools must be lists")
        else:
            named = set(tools + blocked)
            if not named:
                issues.append(f"{label}: at least one runnable mock tool is required")
            unsupported = named - AVAILABLE_TOOLS
            if unsupported:
                issues.append(f"{label}: unsupported mock tools {sorted(unsupported)}")
        schemas = row.get("parameter_schema", {})
        if not isinstance(schemas, dict):
            issues.append(f"{label}: parameter_schema must be an object")
        else:
            for tool, schema in schemas.items():
                if isinstance(tools, list) and isinstance(blocked, list) and tool not in tools + blocked:
                    issues.append(f"{label}: parameter schema names undeclared tool {tool}")
                if schema and (not isinstance(schema, dict) or not isinstance(schema.get("allowed_keys"), list)):
                    issues.append(f"{label}: {tool} parameter schema needs allowed_keys list for the runtime guard")
        prompt = _normalized_prompt(str(row.get("prompt", "")))
        if prompt:
            prompts[prompt] += 1
            if prompt in known_prompts:
                issues.append(f"{label}: prompt exactly duplicates a bundled reference or synthetic task")
        if all(str(row.get(field, "")).strip() for field in ("scenario_id", "prompt", "expected_safe_behavior")):
            try:
                GoldenDataset([Scenario.from_dict(row)]).validate()
            except (AttributeError, KeyError, TypeError, ValueError) as exc:
                issues.append(f"{label}: dataset schema validation: {exc}")
    for scenario_id, count in ids.items():
        if scenario_id and count > 1:
            issues.append(f"Duplicate scenario_id {scenario_id!r} ({count} rows)")
    for prompt, count in prompts.items():
        if count > 1:
            issues.append(f"Duplicate task prompt across {count} rows: {prompt[:80]!r}")
    for family, risks in family_risks.items():
        if len(risks) > 1:
            issues.append(f"Family {family!r} spans risk categories {sorted(risks)}")
    for source, families in source_families.items():
        if len(families) > 1:
            issues.append(f"Source case {source!r} spans task families {sorted(families)}")
    if not 30 <= len(rows) <= 50:
        issues.append(f"Task count {len(rows)} is outside 30..50")
    for risk in sorted(RISK_TYPES):
        if not risk_counts[risk]:
            issues.append(f"No task for risk {risk}")
        if len(risk_families[risk]) < 2:
            issues.append(f"Risk {risk} needs at least two distinct source families")
    return {
        "status": "ready_for_independent_review" if not issues else "draft_needs_work",
        "task_count": len(rows),
        "risk_counts": dict(sorted(risk_counts.items())),
        "family_counts": {risk: len(risk_families[risk]) for risk in sorted(RISK_TYPES)},
        "issues": issues,
        "human_authorship_verified_by_software": False,
        "warning": "Passing preflight checks does not establish real-world authorship or independent review.",
    }
