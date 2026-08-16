#!/usr/bin/env python3
"""把已校验的适配器结果转换为独立的 UI adapter-test 载荷。

不覆盖批准的 v2.1/v1.4 载荷；所有动态文件都带有明确测试模式标记。
"""

from __future__ import annotations

import copy
import gzip
import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INTEGRATION = ROOT / ".omp" / "integration"
ASSETS = ROOT / ".omp" / "skills" / "bifrost-decision-readonly" / "references" / "runtime_assets"
RUNTIME = ROOT / "output" / "bifrost-ui-runtime"
ADAPTER = INTEGRATION / "run_bifrost_adapter.py"
RESULT = INTEGRATION / "orchestration_test_results.json"
PYTHON = Path(r"D:\anaconda3\envs\langchain\python.exe")


def _load_gz(name: str) -> dict:
    return json.loads(gzip.decompress((ASSETS / name).read_bytes()))


def _adapter_evidence(ref: str) -> dict:
    return {
        "semantic_table": "OMP适配器结果",
        "source_table": "orchestration_test_results.json",
        "record_key": "evidence_refs",
        "record_id": ref,
        "source_type": "OMP_LOCAL_ADAPTER_TEST",
    }


def _refs(result: dict) -> list[dict]:
    return [_adapter_evidence(ref) for ref in result.get("evidence_refs", [])]


def _metric(result: dict, semantic_field: str) -> dict | None:
    return next((m for m in result.get("metrics", []) if m.get("semantic_field") == semantic_field), None)


def _kpi(code: str, metric: dict | None, *, unit: str = "ratio", target: float | None = None) -> dict:
    if not metric:
        return {"metric_code": code, "value": None, "value_type": "missing", "unit": unit}
    item = {
        "metric_code": code,
        "value": metric.get("value"),
        "value_type": "ratio" if unit == "ratio" else "integer",
        "display_format": metric.get("display_format", "0.0%" if unit == "ratio" else "#,##0"),
        "unit": unit,
        "aggregation_scope": "adapter_test_fixture",
        "evidence_refs": _refs({"evidence_refs": metric.get("evidence_refs", [])}),
    }
    if target is not None:
        item["target"] = target
    return item


def _task_view(task: dict) -> dict:
    return {
        "task_id": task.get("task_id"),
        "status": task.get("status", "待处理"),
        "title": task.get("objective", "适配器测试任务"),
        "description": task.get("conclusion", ""),
    }


def _role(event_id: str, role: str, headline: str, task: dict, kpis: list[dict], *, extra: dict | None = None) -> dict:
    result = {
        "event_id": "EVT-20251009-0001",
        "role": role,
        "dataset_id": "OMP_LOCAL_ADAPTER_TEST",
        "line_ids": ["LINE-S03"],
        "headline": headline,
        "kpis": kpis,
        "charts": [],
        "alerts": [],
        "tasks": [_task_view(task)],
        "decisions_required": [],
        "data_gaps": task.get("data_gaps", []),
        "evidence_refs": _refs(task),
        "rule_version": "SKILL-CONTRACT-v0.1.3",
        "knowledge_version": "OMP_LOCAL_ADAPTER_TEST",
        "last_updated_at": "2026-08-13T00:00:00Z",
    }
    if task.get("needs_human_confirmation"):
        result["decisions_required"] = [
            {
                "decision_id": "ADAPTER-TEST-CONFIRMATION",
                "confirmation_id": "ADAPTER-TEST-CONFIRMATION",
                "action": "仅生成测试确认草稿，不执行高风险动作",
                "risk_level": "high",
                "status": "待确认",
                "evidence_refs": _refs(task),
            }
        ]
    if extra:
        result.update(extra)
    return result


def _run_adapter() -> dict:
    completed = subprocess.run(
        [str(PYTHON), str(ADAPTER)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stdout or completed.stderr)
    return json.loads(completed.stdout)


def main() -> int:
    adapter = _run_adapter()
    if adapter.get("status") != "PASS":
        raise SystemExit("adapter did not pass")
    result = json.loads(RESULT.read_text(encoding="utf-8"))
    production, quality, supply = result["tasks"]
    overview = _load_gz("BIFROST_OVERVIEW_PAYLOAD_v2.1.json.gz")
    event = _load_gz("BIFROST_EVENT_PAYLOAD_v1.4.json.gz")
    event = copy.deepcopy(event)
    event["runtime_mode"] = "adapter-test"
    event["adapter_event_id"] = result["event"]["event_id"]
    event["dataset_id"] = "OMP_LOCAL_ADAPTER_TEST"
    event["event_status"] = "待确认" if result["event"].get("human_confirmation_required") else "已完成"
    event["generated_at"] = "2026-08-13T00:00:00Z"
    event["analysis_version"] = event.get("analysis_version", 0) + 1

    pm = {m["semantic_field"]: m for m in production.get("metrics", [])}
    qm = {m["semantic_field"]: m for m in quality.get("metrics", [])}
    sm = {m["semantic_field"]: m for m in supply.get("metrics", [])}
    oee = (pm.get("availability", {}).get("value", 0) * pm.get("performance_rate", {}).get("value", 0) * pm.get("quality_factor", {}).get("value", 0))
    roles = [
        _role(event["event_id"], "factory", "适配器测试：生产诊断需要人工确认，未执行高风险动作", production, [_kpi("OEE", {**pm.get("oee_source", {}), "value": oee}, target=None)]),
        _role(event["event_id"], "line", "适配器测试：开动率85.0%，性能率78.0%，质量因子91.3%", production, [_kpi("AVAILABILITY", pm.get("availability")), _kpi("PERFORMANCE", pm.get("performance_rate")), _kpi("QUALITY", pm.get("quality_factor"))]),
        _role(event["event_id"], "quality", "适配器测试：良率95.0%，不良50件；SPC数据缺失", quality, [_kpi("QUALITY", qm.get("yield")), _kpi("DEFECT_TOTAL", qm.get("defect_total"), unit="件")]),
        _role(event["event_id"], "equipment", "适配器测试：非计划停机45分钟；未计算MTBF/MTTR", production, [_kpi("UNPLANNED_DOWNTIME_MINUTES", pm.get("unplanned_downtime_minutes"), unit="分钟")], extra={"downtime_events": [], "downtime_summary": {"unplanned_minutes": 45}}),
        _role(event["event_id"], "process", "适配器测试：性能率78.0%；缺少时序证据，不生成趋势", production, [_kpi("PERFORMANCE", pm.get("performance_rate"))]),
        _role(event["event_id"], "supply", "适配器测试：采购与到货数量均为1000，未检测到供应连续性风险", supply, [_kpi("PURCHASE_QTY", sm.get("purchase_qty"), unit="件"), _kpi("ARRIVED_QTY", sm.get("arrived_qty"), unit="件")]),
    ]
    event["roles"] = roles
    event["materialization"] = {
        "adapter_test": True,
        "oee_recompute": oee,
        "oee_gap": None,
        "total_output": pm.get("total_output", {}).get("value"),
        "good_output": pm.get("good_output", {}).get("value"),
        "defect_total": pm.get("defect_total", {}).get("value"),
    }
    event["data_gaps"] = result.get("event", {}).get("data_gap_count", 0)
    event["adapter_checks"] = result.get("checks", {})

    overview = copy.deepcopy(overview)
    overview["runtime_mode"] = "adapter-test"
    overview["dataset_id"] = "OMP_LOCAL_ADAPTER_TEST"
    overview["data_nature"] = "本地 Skill 适配器测试数据（非企业生产数据）"
    overview["payload_generated_at"] = "2026-08-13T00:00:00Z"
    overview["event_summaries"] = [s for s in overview.get("event_summaries", []) if s.get("event_id") != event["event_id"]]
    overview["event_summaries"].insert(0, {
        "event_id": event["event_id"],
        "line_id": "LINE-S03",
        "status": event["event_status"],
        "alert_type": "adapter-test",
        "headline": "适配器测试：生产/质量/供应链结果已完成合同审查",
        "date": "2025-10-09",
    })
    out_dir = RUNTIME / "artifacts"
    out_dir.mkdir(parents=True, exist_ok=True)
    overview_path = out_dir / "BIFROST_OVERVIEW_PAYLOAD_adapter-test.json"
    event_path = out_dir / "BIFROST_EVENT_PAYLOAD_adapter-test.json"
    overview_path.write_text(json.dumps(overview, ensure_ascii=False, indent=2), encoding="utf-8")
    event_path.write_text(json.dumps(event, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = {
        "mode": "adapter-test",
        "adapter_result_sha256": hashlib.sha256(RESULT.read_bytes()).hexdigest(),
        "overview_test_sha256": hashlib.sha256(overview_path.read_bytes()).hexdigest(),
        "event_test_sha256": hashlib.sha256(event_path.read_bytes()).hexdigest(),
        "source_write_performed": False,
        "actor_can_execute": False,
    }
    (out_dir / "BIFROST_ADAPTER_TEST_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "PASS", "manifest": manifest, "files": [str(overview_path), str(event_path)]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
