"""Deterministic validation for the synthetic OMP adapter fixture.

This is deliberately separate from the business Skills and official BIFROST
payloads. It catches impossible test data before an LLM is asked to interpret
it, especially OEE values outside the metric domain [0, 1].
"""

from __future__ import annotations

import csv
import math
import sys
from pathlib import Path


REQUIRED = {
    "prod_date",
    "line_code",
    "process_step",
    "shift",
    "good_qty",
    "input_qty",
    "defect_qty",
    "first_pass_qty",
    "ideal_cycle_time",
    "planned_time",
    "actual_output",
    "target_output",
    "downtime_minutes",
    "available_time",
    "actual_run_time",
    "status",
    "data_label",
}


def validate(path: Path) -> list[str]:
    errors: list[str] = []
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    if not rows:
        return ["fixture is empty"]
    missing = REQUIRED - set(rows[0])
    if missing:
        errors.append(f"missing columns: {sorted(missing)}")

    by_line: dict[str, dict[str, float]] = {}
    for index, row in enumerate(rows, start=2):
        try:
            good = float(row["good_qty"])
            input_qty = float(row["input_qty"])
            defect = float(row["defect_qty"])
            first_pass = float(row["first_pass_qty"])
            cycle = float(row["ideal_cycle_time"])
            planned = float(row["planned_time"])
            downtime = float(row["downtime_minutes"])
            available = float(row["available_time"])
            actual_run = float(row["actual_run_time"])
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"row {index}: non-numeric required value ({exc})")
            continue

        if any(value < 0 for value in (good, input_qty, defect, first_pass, cycle, planned, downtime, available, actual_run)):
            errors.append(f"row {index}: negative production value")
        if not math.isclose(good + defect, input_qty, rel_tol=0, abs_tol=1):
            errors.append(f"row {index}: good_qty + defect_qty != input_qty")
        if first_pass > good:
            errors.append(f"row {index}: first_pass_qty > good_qty")
        if downtime > planned:
            errors.append(f"row {index}: downtime_minutes > planned_time")
        if not math.isclose(available, planned - downtime, rel_tol=0, abs_tol=1e-9):
            errors.append(f"row {index}: available_time != planned_time - downtime_minutes")
        if actual_run > available:
            errors.append(f"row {index}: actual_run_time > available_time")

        line = row["line_code"]
        bucket = by_line.setdefault(line, {"numerator": 0.0, "denominator": 0.0})
        bucket["numerator"] += good * cycle
        bucket["denominator"] += planned

    for line, bucket in sorted(by_line.items()):
        if bucket["denominator"] <= 0:
            errors.append(f"line {line}: planned_time denominator is zero")
            continue
        oee = bucket["numerator"] / bucket["denominator"]
        if not 0 <= oee <= 1:
            errors.append(f"line {line}: aggregated OEE={oee:.6f} outside [0, 1]")

    labels = {row.get("data_label") for row in rows}
    if labels != {"SYNTHETIC_GOERTEK_FIXTURE_V2"}:
        errors.append(f"unexpected data_label values: {sorted(labels)}")
    return errors


if __name__ == "__main__":
    fixture = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("fixtures/goertek/omp-bridge-input.csv")
    problems = validate(fixture)
    if problems:
        print("FAIL")
        print("\n".join(f"- {problem}" for problem in problems))
        raise SystemExit(1)
    print(f"PASS: {fixture} has valid schema, row constraints, and OEE domain")
