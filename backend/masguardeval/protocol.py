"""Detect agent-adapter protocol failures recorded inside completed traces."""

from __future__ import annotations

from typing import Any


def protocol_errors(result: dict[str, Any]) -> list[dict[str, str]]:
    errors = []
    for mode in ("baseline", "guarded"):
        trace = result[f"{mode}_trace"]
        if any(span.get("failure_label") == "adapter_error" for span in trace.get("spans", [])):
            errors.append({"mode": mode, "type": "adapter_error",
                           "reason": str(trace.get("stop_reason") or "adapter failed")})
    return errors


def audit_report(report: dict[str, Any]) -> dict[str, Any]:
    failures = 0
    for result in report.get("results", []):
        errors = protocol_errors(result)
        result["protocol_errors"] = errors
        result["protocol_valid"] = not errors
        failures += bool(errors)
    report["protocol_failure_pair_count"] = failures
    report["protocol_valid_pair_count"] = len(report.get("results", [])) - failures
    if report.get("incomplete_pair_count", 0):
        report["status"] = "partial"
    elif failures:
        report["status"] = "complete_with_protocol_errors"
    else:
        report["status"] = "complete"
    return report
