from __future__ import annotations

from collections import Counter


def evaluate(cases: list[dict]) -> dict:
    counts = {"cases": len(cases), "task_success": 0, "selection": 0,
              "arguments": 0, "edit": 0, "instruction": 0,
              "conflict_total": 0, "conflict_ok": 0,
              "quality_total": 0, "quality_ok": 0,
              "changed": 0, "unintended": 0}
    details = []
    for case in cases:
        expected, observed = case["expected"], case["scripted_observation"]
        tools = [call["name"] for call in observed["tool_calls"]]
        required = expected["required_tools"]
        selection = not (Counter(required) - Counter(tools)) and not any(
            tool in tools for tool in expected["forbidden_tools"])
        arguments = all(call.get("arguments_valid") is True for call in observed["tool_calls"])
        wanted, changed = set(expected["changed_nodes"]), set(observed["changed_nodes"])
        edit = changed == wanted and observed["revision_delta"] == expected["revision_delta"]
        unintended = changed - wanted
        instruction = observed["instruction_followed"] and selection
        if expected["quality_only"]:
            counts["quality_total"] += 1
            counts["quality_ok"] += int(not changed and observed["revision_delta"] == 0)
        if expected["requires_conflict_recovery"]:
            counts["conflict_total"] += 1
            counts["conflict_ok"] += int(observed.get("conflict_recovered") is True)
        success = observed["task_succeeded"] and selection and arguments and edit and instruction
        counts["task_success"] += int(success)
        counts["selection"] += int(selection)
        counts["arguments"] += int(arguments)
        counts["edit"] += int(edit)
        counts["instruction"] += int(instruction)
        counts["changed"] += len(changed)
        counts["unintended"] += len(unintended)
        details.append({"id": case["id"], "passed": success,
                        "unintended_nodes": sorted(unintended)})
    total = counts["cases"] or 1
    rate = lambda numerator, denominator=total: round(numerator / (denominator or 1), 4)
    return {"case_count": counts["cases"], "metrics": {
        "task_success_rate": rate(counts["task_success"]),
        "tool_selection_accuracy": rate(counts["selection"]),
        "tool_argument_accuracy": rate(counts["arguments"]),
        "artifact_edit_accuracy": rate(counts["edit"]),
        "unintended_modification_rate": rate(counts["unintended"], counts["changed"]),
        "instruction_following": rate(counts["instruction"]),
        "revision_conflict_recovery": rate(counts["conflict_ok"], counts["conflict_total"]),
        "quality_tool_non_mutation": rate(counts["quality_ok"], counts["quality_total"]),
    }, "details": details}
