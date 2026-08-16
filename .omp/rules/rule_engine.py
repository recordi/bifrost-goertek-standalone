"""Safe, deterministic rule calculation and what-if simulation for BIFROST.

This module deliberately evaluates a small expression language.  It never
executes Python code, imports modules, reads files, or writes business data.
"""

from __future__ import annotations

import ast
import datetime as _dt
import hashlib
import json
import math
import operator
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Sequence


ALLOWED_FUNCTIONS = {"sum", "avg", "count", "min", "max", "abs"}
ALLOWED_BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
}
ALLOWED_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
NAME_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


class RuleError(ValueError):
    """Raised for invalid formulas, rule definitions, or input data."""


def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuleError(f"expected numeric value, got {value!r}")
    value = float(value)
    if not math.isfinite(value):
        raise RuleError("non-finite numeric value")
    return value


def _validate_tree(node: ast.AST) -> None:
    if isinstance(node, ast.Expression):
        _validate_tree(node.body)
    elif isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float)) or isinstance(node.value, bool):
            raise RuleError("only numeric literals are allowed")
    elif isinstance(node, ast.Name):
        if not NAME_RE.fullmatch(node.id):
            raise RuleError(f"invalid field name: {node.id}")
    elif isinstance(node, ast.BinOp):
        if type(node.op) not in ALLOWED_BINARY:
            raise RuleError(f"operator not allowed: {type(node.op).__name__}")
        _validate_tree(node.left)
        _validate_tree(node.right)
    elif isinstance(node, ast.UnaryOp):
        if type(node.op) not in ALLOWED_UNARY:
            raise RuleError(f"unary operator not allowed: {type(node.op).__name__}")
        _validate_tree(node.operand)
    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in ALLOWED_FUNCTIONS:
            raise RuleError("function is not in the formula whitelist")
        if node.keywords:
            raise RuleError("keyword arguments are not allowed")
        for arg in node.args:
            _validate_tree(arg)
    else:
        raise RuleError(f"syntax is not allowed: {type(node).__name__}")


def parse_formula(expression: str) -> ast.Expression:
    if not isinstance(expression, str) or not expression.strip():
        raise RuleError("formula must be a non-empty string")
    if len(expression) > 1000:
        raise RuleError("formula is too long")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise RuleError(f"invalid formula syntax: {exc.msg}") from exc
    _validate_tree(tree)
    return tree


def formula_fields(expression: str) -> list[str]:
    """Return field dependencies for a formula without executing it."""
    tree = parse_formula(expression)
    return sorted({node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and node.id not in ALLOWED_FUNCTIONS})


def build_input_schema(rule_set: Mapping[str, Any] | str | Path) -> dict[str, Any]:
    """Describe the row fields required by every registered metric.

    This schema is consumed by adapters/UI builders to create sample inputs;
    it is not an authorization or publication mechanism.
    """
    rules = load_rule_set(rule_set)
    schema = {
        metric_id: {
            "fields": formula_fields(metric["formula"]),
            "unit": metric.get("unit", ""),
            "min_sample_size": int(metric.get("min_sample_size", 1)),
            "direction": metric.get("thresholds", {}).get("direction", "higher_is_better"),
        }
        for metric_id, metric in rules["metrics"].items()
    }
    field_specs: dict[str, dict[str, Any]] = {}
    for metric in rules["metrics"].values():
        for field in formula_fields(metric["formula"]):
            value_type = "ratio" if field in {"availability", "performance_rate", "quality_rate", "yield_rate", "oee"} else "number"
            field_specs.setdefault(field, {"value_type": value_type, "min": 0 if value_type in {"ratio", "number"} else None})
    schema["_fields"] = field_specs
    return schema


def _eval_node(node: ast.AST, row: Mapping[str, Any], context: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> float:
    if isinstance(node, ast.Constant):
        return _number(node.value)
    if isinstance(node, ast.Name):
        if node.id in context:
            return _number(context[node.id])
        if node.id in row:
            return _number(row[node.id])
        raise RuleError(f"field is missing: {node.id}")
    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left, row, context, rows)
        right = _eval_node(node.right, row, context, rows)
        if isinstance(node.op, ast.Div) and right == 0:
            raise RuleError("division by zero")
        return _number(ALLOWED_BINARY[type(node.op)](left, right))
    if isinstance(node, ast.UnaryOp):
        return _number(ALLOWED_UNARY[type(node.op)](_eval_node(node.operand, row, context, rows)))
    if isinstance(node, ast.Call):
        name = node.func.id
        if name == "abs":
            if len(node.args) != 1:
                raise RuleError("abs expects one argument")
            return _number(abs(_eval_node(node.args[0], row, context, rows)))
        if name in {"min", "max"} and len(node.args) > 1:
            values = [_eval_node(arg, row, context, rows) for arg in node.args]
            return _number(min(values) if name == "min" else max(values))
        if name == "count" and not node.args:
            return float(len(rows))
        if name in {"sum", "avg", "min", "max"} and len(node.args) == 1:
            values = [_eval_node(node.args[0], item, context, rows) for item in rows]
            if not values:
                raise RuleError("cannot aggregate an empty input")
            if name == "sum":
                return _number(sum(values))
            if name == "avg":
                return _number(sum(values) / len(values))
            return _number(min(values) if name == "min" else max(values))
        raise RuleError(f"invalid arguments for {name}")
    raise RuleError(f"node cannot be evaluated: {type(node).__name__}")


def evaluate_formula(expression: str, rows: Sequence[Mapping[str, Any]], context: Mapping[str, Any] | None = None) -> float:
    """Evaluate one whitelisted formula against immutable input rows."""
    rows = list(rows)
    if not rows:
        raise RuleError("at least one input row is required")
    tree = parse_formula(expression)
    return _eval_node(tree.body, rows[0], context or {}, rows)


def _status(value: float, policy: Mapping[str, Any]) -> tuple[str, list[str]]:
    direction = policy.get("direction", "higher_is_better")
    warning = _number(policy["warning"])
    critical = _number(policy["critical"])
    if direction not in {"higher_is_better", "lower_is_better"}:
        raise RuleError("threshold direction must be higher_is_better or lower_is_better")
    if direction == "higher_is_better":
        if critical > warning:
            raise RuleError("critical threshold cannot exceed warning for higher-is-better")
        if value < critical:
            return "critical", ["critical_threshold"]
        if value < warning:
            return "warning", ["warning_threshold"]
    else:
        if critical < warning:
            raise RuleError("critical threshold cannot be below warning for lower-is-better")
        if value > critical:
            return "critical", ["critical_threshold"]
        if value > warning:
            return "warning", ["warning_threshold"]
    return "pass", []


def load_rule_set(source: Mapping[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(source, (str, Path)):
        source = json.loads(Path(source).read_text(encoding="utf-8"))
    rule_set = deepcopy(dict(source))
    required = {"rule_set_id", "rule_version", "effective_from", "status", "metrics"}
    missing = required - set(rule_set)
    if missing:
        raise RuleError(f"rule set missing fields: {sorted(missing)}")
    if rule_set["status"] not in {"draft", "published", "retired"}:
        raise RuleError("rule set status must be draft, published, or retired")
    if rule_set.get("threshold_strategy", "strict") not in {"strict", "soft", "configurable"}:
        raise RuleError("threshold_strategy must be strict, soft, or configurable")
    if not isinstance(rule_set.get("effective_from"), str) or not rule_set["effective_from"].strip():
        raise RuleError("effective_from must be a non-empty ISO timestamp")
    try:
        _dt.datetime.fromisoformat(rule_set["effective_from"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuleError("effective_from must be an ISO timestamp") from exc
    if not isinstance(rule_set["metrics"], dict) or not rule_set["metrics"]:
        raise RuleError("rule set metrics must be a non-empty object")
    for metric_id, metric in rule_set["metrics"].items():
        if not NAME_RE.fullmatch(metric_id):
            raise RuleError(f"invalid metric id: {metric_id}")
        parse_formula(metric["formula"])
        for field in ("target", "warning", "critical"):
            _number(metric["thresholds"][field])
        direction = metric["thresholds"].get("direction", "higher_is_better")
        if direction not in {"higher_is_better", "lower_is_better"}:
            raise RuleError("threshold direction must be higher_is_better or lower_is_better")
        if int(metric.get("min_sample_size", 1)) < 1:
            raise RuleError("min_sample_size must be positive")
    return rule_set


def calculate(rule_set: Mapping[str, Any] | str | Path, rows: Sequence[Mapping[str, Any]], *, calculation_id: str = "CALC-LOCAL", timestamp: str | None = None) -> dict[str, Any]:
    rules = load_rule_set(rule_set)
    rows = list(rows)
    result: dict[str, Any] = {
        "calculation_id": calculation_id,
        "rule_set_id": rules["rule_set_id"],
        "rule_version": rules["rule_version"],
        "threshold_strategy": rules.get("threshold_strategy", "strict"),
        "input_row_count": len(rows),
        "results": {},
        "data_gaps": [],
        "timestamp": timestamp or _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "readonly": True,
        "source_write_performed": False,
    }
    if not rows:
        result["data_gaps"].append({"reason": "empty_input", "status": "blocked"})
        return result
    for metric_id, metric in rules["metrics"].items():
        min_sample = int(metric.get("min_sample_size", 1))
        if len(rows) < min_sample:
            result["results"][metric_id] = {
                "value": None,
                "status": "insufficient_data",
                "threshold_violations": ["minimum_sample_size"],
                "formula": metric["formula"],
            }
            result["data_gaps"].append({"metric_id": metric_id, "reason": "minimum_sample_size", "required": min_sample, "observed": len(rows)})
            continue
        try:
            value = evaluate_formula(metric["formula"], rows)
            status, violations = _status(value, metric["thresholds"])
            result["results"][metric_id] = {
                "value": value,
                "unit": metric.get("unit", ""),
                "status": status,
                "threshold_violations": violations,
                "formula": metric["formula"],
                "target": metric["thresholds"].get("target"),
            }
        except RuleError as exc:
            result["results"][metric_id] = {
                "value": None,
                "status": "blocked",
                "threshold_violations": ["formula_error"],
                "formula": metric["formula"],
            }
            result["data_gaps"].append({"metric_id": metric_id, "reason": "formula_error", "detail": str(exc)})
    return result


def simulate_change(
    baseline: Mapping[str, Any] | str | Path,
    candidate: Mapping[str, Any] | str | Path,
    rows: Sequence[Mapping[str, Any]],
    *,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a read-only what-if calculation with reproducible provenance.

    ``context`` is deliberately metadata only (dataset/window/source hash); it
    never changes the calculation.  Keeping it in the simulation receipt lets
    an approver reproduce which snapshot was used without coupling the formula
    engine to a particular workbook.
    """
    rows = [dict(row) for row in rows]
    before = calculate(baseline, rows, calculation_id="CALC-BASELINE")
    after = calculate(candidate, rows, calculation_id="CALC-CANDIDATE")
    baseline_rule = load_rule_set(baseline)
    candidate_rule = load_rule_set(candidate)
    baseline_sha256 = hashlib.sha256(json.dumps(baseline_rule, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    candidate_sha256 = hashlib.sha256(json.dumps(candidate_rule, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    changes = {}
    for metric_id in sorted(set(before["results"]) | set(after["results"])):
        left = before["results"].get(metric_id, {})
        right = after["results"].get(metric_id, {})
        if left.get("value") != right.get("value") or left.get("status") != right.get("status"):
            changes[metric_id] = {
                "before": {"value": left.get("value"), "status": left.get("status")},
                "after": {"value": right.get("value"), "status": right.get("status")},
            }
    sample_bytes = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sample_sha256 = hashlib.sha256(sample_bytes).hexdigest()
    receipt_context = dict(context or {})
    receipt_context.setdefault("sample_sha256", sample_sha256)
    receipt_context.setdefault("input_row_count", len(rows))
    context_bytes = json.dumps(receipt_context, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    context_sha256 = hashlib.sha256(context_bytes).hexdigest()
    simulation_seed = f"{baseline_sha256}:{candidate_sha256}:{sample_sha256}:{context_sha256}"
    simulation_id = "SIM-RULE-" + hashlib.sha256(simulation_seed.encode("ascii")).hexdigest()[:16]
    return {
        "simulation_id": simulation_id,
        "baseline_version": before["rule_version"],
        "candidate_version": after["rule_version"],
        "baseline_sha256": baseline_sha256,
        "candidate_sha256": candidate_sha256,
        "input_row_count": len(rows),
        "sample_sha256": sample_sha256,
        "context_sha256": context_sha256,
        "context": receipt_context,
        "input_schema": build_input_schema(candidate_rule),
        "changed_metrics": changes,
        "baseline": before,
        "candidate": after,
        "data_gaps": list(after["data_gaps"]),
        "publishable": not after["data_gaps"],
        "readonly": True,
        "source_write_performed": False,
    }
