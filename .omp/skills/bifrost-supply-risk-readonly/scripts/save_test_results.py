#!/usr/bin/env python3
"""Save machine-readable test results for 36 regression + v0.1.3 new tests."""
import json, os, subprocess, sys, time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD_ROOT = os.path.dirname(HERE)
RESULTS_DIR = os.path.join(BUILD_ROOT, "tests", "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

def run_pytest(test_file, label):
    start = time.time()
    r = subprocess.run(
        [sys.executable, "-m", "pytest", test_file, "-v", "--tb=short", "--json-report",
         f"--json-report-file={RESULTS_DIR}/{label}_raw.json"],
        capture_output=True, text=True, cwd=BUILD_ROOT
    )
    elapsed = round(time.time() - start, 2)
    return r, elapsed

# Run main test suite
r1, t1 = run_pytest("tests/test_supply_risk_analyzer.py", "main")

# Parse results manually from stdout since json plugin may not be installed
passed = r1.stdout.count(" PASSED")
failed = r1.stdout.count(" FAILED")
skipped = r1.stdout.count(" SKIPPED")
errors = r1.returncode != 0 and "ERROR" in r1.stdout

results = {
    "test_suite": "BIFROST_SUPPLY_RISK_v0.1.2_REGRESSION_AND_V013_NEW",
    "run_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    "elapsed_seconds": t1,
    "exit_code": r1.returncode,
    "summary": {
        "total": passed + failed + skipped,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "errors": int(errors),
    },
    "status": "ALL_PASSED" if r1.returncode == 0 else "HAS_FAILURES",
    "tests": [],
}

# Parse individual test results from stdout
for line in r1.stdout.splitlines():
    if "::" in line and ("PASSED" in line or "FAILED" in line or "SKIPPED" in line):
        parts = line.strip().split()
        test_name = parts[0] if parts else ""
        status = "PASSED" if "PASSED" in line else ("FAILED" if "FAILED" in line else "SKIPPED")
        results["tests"].append({"test": test_name, "status": status})

# Integration test results
integration_path = os.path.join(os.path.dirname(BUILD_ROOT), "integration", "integration_test_results.json")
if os.path.exists(integration_path):
    with open(integration_path) as f:
        integration = json.load(f)
    results["integration"] = integration

out_path = os.path.join(RESULTS_DIR, "test_results.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"Test results saved to {out_path}")
print(f"Summary: {results['summary']}")
