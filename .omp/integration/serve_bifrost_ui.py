#!/usr/bin/env python3
"""Serve the generated BIFROST UI and expose a read-only local AI bridge.

The bridge intentionally reads the same custom-grok provider configuration used
by OMP. The browser never receives the API key and every request is gated by
the fixed read-only BIFROST adapter before a model call is made.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import subprocess
import tempfile
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import sys

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "output" / "bifrost-ui-runtime"
ADAPTER = ROOT / ".omp" / "integration" / "run_bifrost_adapter.py"
PEER_ADAPTER = ROOT / ".omp" / "integration" / "run_peer_adapters.py"
RULES_DIR = ROOT / ".omp" / "rules"
DEFAULT_RULE_SET = RULES_DIR / "rule_definitions_v1.json"
sys.path.insert(0, str(RULES_DIR))
from rule_engine import RuleError, build_input_schema, load_rule_set, simulate_change  # noqa: E402
WORKSTREAMS = ROOT / ".omp" / "workstreams"
sys.path.insert(0, str(WORKSTREAMS))
from autoadapt.pipeline import AutoAdaptPipeline  # noqa: E402
from peer_pipeline.peer_postprocessor import run_peer_postprocessors  # noqa: E402
sys.path.insert(0, str(WORKSTREAMS / "compile"))
from dynamic_peer_bridge import build_formal_derived_insights, build_peer_task_payload  # noqa: E402
sys.path.insert(0, str(WORKSTREAMS / "presentation"))
from business_interpreter import build_business_interpretation  # noqa: E402
OMP_CONFIGS = (
    Path(r"C:\Users\zhr12\.omp\agent\models.yml"),
    Path(r"D:\Codex\智能体\.omp-runtime\agent\models.yml"),
)
PYTHON = Path(r"D:\anaconda3\envs\langchain\python.exe")
OMP_EXE = Path(r"D:\Codex\智能体\oh-my-pi\omp-windows-x64.exe")
MAX_BODY = 24 * 1024
MODEL_TIMEOUT = 12
BRIDGE_VERSION = "OMP-CLI-BRIDGE-v2"
RESULT_CONTRACT_VERSION = "BIFROST-AI-RESULT-v1"
VALID_ROLES = {"factory", "line", "quality", "equipment", "process", "supply"}
VALID_TIME_WINDOWS = {
    "last_7_shifts", "last_30_shifts", "recent_7_shifts", "recent_30_shifts",
    "pre_improvement", "post_improvement", "before_improvement", "after_improvement",
    "full_history",
}
CONTEXT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


def json_response(handler: SimpleHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(raw)


def provider_config() -> tuple[str, str, str, str] | None:
    config_path = next((path for path in OMP_CONFIGS if path.is_file()), None)
    if config_path is None:
        return None
    text = config_path.read_text(encoding="utf-8")
    base = re.search(r"baseUrl:\s*([^\s#]+)", text)
    model = re.search(r"- id:\s*([^\s#]+)", text)
    env_name = re.search(r"apiKey:\s*([^\s#]+)", text)
    if not (base and model and env_name):
        return None
    key = os.environ.get(env_name.group(1), "")
    # A desktop process may have started before the user-level variable was
    # added. Read only that named variable from the Windows user environment as
    # a fallback; the value is never returned to the browser or logs.
    if not key and os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as env_key:
                key, _ = winreg.QueryValueEx(env_key, env_name.group(1))
        except (FileNotFoundError, OSError):
            key = ""
    if not key:
        return None
    return base.group(1).rstrip("/"), model.group(1), env_name.group(1), key


def normalized_child_env(**overrides: str) -> dict[str, str]:
    """Avoid Windows PATH/Path duplicates when the bridge is detached."""
    result: dict[str, str] = {}
    seen: set[str] = set()
    for key, value in os.environ.items():
        folded = key.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        result[key] = value
    # The desktop test shell may export a dead loopback proxy (127.0.0.1:9).
    # Bypass only that known broken endpoint; preserve any real corporate or
    # user-configured proxy so normal network policy is not changed.
    for key in list(result):
        if key.casefold() not in {"http_proxy", "https_proxy", "all_proxy"}:
            continue
        value = str(result.get(key) or "").lower()
        if re.search(r"(?:https?://)?(?:127\.0\.0\.1|localhost):9(?:/|$)", value):
            result.pop(key, None)
    result.update(overrides)
    return result


def run_adapter(peer: bool = False) -> dict[str, Any]:
    adapter_path = PEER_ADAPTER if peer else ADAPTER
    if not adapter_path.is_file():
        raise RuntimeError("BIFROST_PEER_ADAPTER_MISSING" if peer else "BIFROST_READONLY_ADAPTER_MISSING")
    result = subprocess.run(
        [str(PYTHON), str(adapter_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
        env=normalized_child_env(PYTHONUTF8="1", PYTHONIOENCODING="utf-8"),
    )
    if result.returncode != 0:
        raise RuntimeError("BIFROST_PEER_ADAPTER_FAILED" if peer else "BIFROST_READONLY_ADAPTER_FAILED")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("BIFROST_PEER_ADAPTER_INVALID_OUTPUT" if peer else "BIFROST_READONLY_ADAPTER_INVALID_OUTPUT") from exc
    if payload.get("status") != "PASS":
        raise RuntimeError("BIFROST_PEER_ADAPTER_NOT_PASS" if peer else "BIFROST_READONLY_ADAPTER_NOT_PASS")
    # The interpretation layer is additive: it translates already returned
    # facts into business language, while preserving the adapter's KPI/task
    # objects and their hashes.  It is intentionally disabled for the peer
    # adapter itself; peer output must remain an advisory input to the main
    # workflow.
    if not peer:
        payload["business_interpretations"] = {
            role: build_business_interpretation(payload, role=role, scope="ALL_LINES")
            for role in ("factory", "line", "quality", "equipment", "process", "supply")
        }
    return payload


def validate_ai_context(*, role: Any, scope: Any, time_window: Any, event_id: Any = None) -> None:
    """Validate client context before it reaches the model bridge.

    Context is routing metadata, not authorization by itself; the adapter is
    still reduced by ``adapter_for_context`` below before model invocation.
    """
    if role not in VALID_ROLES:
        raise ValueError("INVALID_ROLE")
    if not isinstance(scope, str) or not scope or len(scope) > 128:
        raise ValueError("INVALID_SCOPE")
    if scope != "ALL_LINES" and not CONTEXT_ID_RE.fullmatch(scope):
        raise ValueError("INVALID_SCOPE")
    if time_window not in VALID_TIME_WINDOWS:
        raise ValueError("INVALID_TIME_WINDOW")
    if event_id is not None and (not isinstance(event_id, str) or not CONTEXT_ID_RE.fullmatch(event_id)):
        raise ValueError("INVALID_EVENT_ID")


def submit_rule_draft(candidate: Any, simulation: Any = None) -> dict[str, Any]:
    """Validate a rule candidate and return an approval artifact without writing.

    This is deliberately not a publish operation: the formal rule file is only
    read, the candidate must remain ``draft``, and the response requires a
    separate human approval step that this bridge cannot execute.
    """
    if not isinstance(candidate, dict):
        raise RuleError("candidate rule set must be an object")
    if not isinstance(simulation, dict):
        raise RuleError("a readonly simulation is required before approval")
    if simulation.get("readonly") is not True or simulation.get("source_write_performed") is not False:
        raise RuleError("simulation must satisfy readonly contract")
    if simulation.get("publishable") is not True or simulation.get("data_gaps"):
        raise RuleError("simulation has data gaps and cannot enter approval")
    if not simulation.get("simulation_id") or not simulation.get("sample_sha256"):
        raise RuleError("simulation receipt is missing reproducibility identifiers")
    baseline_bytes = DEFAULT_RULE_SET.read_bytes()
    baseline = load_rule_set(json.loads(baseline_bytes.decode("utf-8")))
    candidate_rules = load_rule_set(candidate)
    if candidate_rules.get("status") != "draft":
        raise RuleError("candidate rule set must have draft status")
    if candidate_rules.get("rule_set_id") != baseline.get("rule_set_id"):
        raise RuleError("candidate rule set id must match baseline")
    if candidate_rules.get("rule_version") == baseline.get("rule_version"):
        raise RuleError("candidate version must differ from baseline")
    version = str(candidate_rules.get("rule_version", ""))
    if not CONTEXT_ID_RE.fullmatch(version):
        raise RuleError("candidate version is invalid")
    baseline_sha256 = hashlib.sha256(baseline_bytes).hexdigest()
    candidate_bytes = json.dumps(candidate_rules, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    candidate_sha256 = hashlib.sha256(candidate_bytes).hexdigest()
    canonical_baseline_sha256 = hashlib.sha256(json.dumps(baseline, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    if simulation.get("baseline_sha256") != canonical_baseline_sha256:
        raise RuleError("simulation baseline is stale; run the simulation again")
    if simulation.get("candidate_version") != candidate_rules.get("rule_version"):
        raise RuleError("simulation does not match candidate version")
    if simulation.get("candidate_sha256") != candidate_sha256:
        raise RuleError("simulation does not match candidate rule set")
    draft_id = "DRAFT-RULE-" + candidate_sha256[:16]
    return {
        "draft_id": draft_id,
        "rule_set_id": candidate_rules["rule_set_id"],
        "rule_version": version,
        "baseline_version": baseline["rule_version"],
        "baseline_sha256": baseline_sha256,
        "baseline_canonical_sha256": canonical_baseline_sha256,
        "candidate_sha256": candidate_sha256,
        "simulation_candidate_sha256": simulation.get("candidate_sha256") if isinstance(simulation, dict) else None,
        "review_status": "pending_human_approval",
        "requires_human_confirmation": True,
        "readonly": True,
        "source_write_performed": False,
        "actor_can_execute": False,
    }


def submit_governance_action_draft(issue: Any, *, role: Any = "factory") -> dict[str, Any]:
    """Create a human-reviewable data-governance action without writing data."""
    if not isinstance(issue, dict):
        raise ValueError("governance issue must be an object")
    evidence_ref = issue.get("evidence_ref")
    action = issue.get("suggested_action") or issue.get("action")
    if not isinstance(evidence_ref, str) or not evidence_ref.strip():
        raise ValueError("governance issue requires evidence_ref")
    if not isinstance(action, str) or not action.strip():
        raise ValueError("governance issue requires suggested_action")
    if role not in VALID_ROLES:
        raise ValueError("INVALID_ROLE")
    digest = hashlib.sha256(json.dumps({"role": role, "evidence_ref": evidence_ref, "action": action}, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "draft_id": "DRAFT-DQ-" + digest[:16],
        "role": role,
        "issue_id": issue.get("id"),
        "evidence_ref": evidence_ref,
        "action": action,
        "review_status": "pending_human_confirmation",
        "requires_human_confirmation": True,
        "readonly": True,
        "source_write_performed": False,
        "actor_can_execute": False,
    }


def adapter_for_context(
    adapter: dict[str, Any], *, role: str, scope: str, event_id: str | None = None
) -> dict[str, Any]:
    """Return a role-scoped copy for model context; never mutate adapter input."""
    scoped = copy.deepcopy(adapter)
    role_tasks = _task_for_role(adapter, role)
    canonical_event_id = adapter.get("event", {}).get("event_id") or adapter.get("event_id")
    event_context_match = not event_id or not canonical_event_id or event_id == canonical_event_id
    if not event_context_match:
        # The adapter only contains evidence for its canonical event. Never
        # relabel it as another UI-selected event; expose an explicit no-data
        # context until that event has its own read-only payload.
        role_tasks = []
    if scope != "ALL_LINES":
        # Tasks without an explicit line locator cannot be safely attributed to
        # a requested line, so omit them rather than leaking cross-line data.
        # Any task with locators must match the requested line.
        filtered = []
        for task in role_tasks:
            lines = set()
            for key in ("line_id", "line", "line_ids"):
                value = task.get(key)
                if isinstance(value, str):
                    lines.add(value)
                elif isinstance(value, list):
                    lines.update(x for x in value if isinstance(x, str))
            for item in task.get("affected_objects", []) or []:
                if isinstance(item, dict):
                    value = item.get("id") or item.get("line_id")
                    if isinstance(value, str):
                        lines.add(value)
            if scope in lines:
                filtered.append(task)
        role_tasks = filtered
    scoped["tasks"] = copy.deepcopy(role_tasks)
    projections = scoped.get("role_projections")
    if isinstance(projections, dict):
        scoped["role_projections"] = {role: copy.deepcopy(projections.get(role, {}))}
    scoped["context_scope"] = scope
    scoped["context_role"] = role
    scoped["context_event_id"] = event_id
    scoped["event_context_match"] = event_context_match
    # Validated business findings follow the same role/event gate as tasks.
    # They are explanatory inputs only; the model cannot promote or rewrite them.
    event = scoped.get("event") if isinstance(scoped.get("event"), dict) else {}
    findings = event.get("formal_findings") or event.get("role_findings") or {}
    if isinstance(findings, dict):
        scoped["business_findings"] = copy.deepcopy(findings.get(role, []))
    else:
        scoped["business_findings"] = []
    # Fall back to deterministic, evidence-first business interpretation when
    # a formal derived finding has not yet been attached.  This is explanatory
    # only; it never changes authoritative metrics or promotes peer output.
    interpretations = adapter.get("business_interpretations")
    if not scoped["business_findings"] and isinstance(interpretations, dict):
        brief = interpretations.get(role) or interpretations.get("factory")
        if isinstance(brief, dict):
            scoped["business_findings"] = copy.deepcopy(brief.get("findings") or [])
    return scoped


def call_model_via_omp(query: str, context: dict[str, Any], adapter: dict[str, Any]) -> str:
    """Ask the already-configured OMP CLI instead of bypassing its network stack."""
    if not OMP_EXE.is_file():
        raise RuntimeError("OMP_CLI_NOT_FOUND")
    configured = provider_config()
    if not configured:
        raise RuntimeError("AI_PROVIDER_NOT_CONFIGURED")
    _base_url, _model, env_name, api_key = configured
    system = (
        "你是BIFROST只读决策助手。只能基于用户上下文和附带的只读适配器结果回答。"
        "不得编造指标、事件、证据引用或业务数据；若数据不足必须明确说明。"
        "不得执行写入、解除冻结、修改规则、改变交付承诺或其他高风险动作；"
        "这类请求只能生成待人工确认的动作草稿。回答使用简洁中文，先给结论，再给依据和下一步。"
    )
    system += (
        "\nOutput contract: use four short sections in Chinese: 结论、重点风险、依据、下一步。"
        "重点风险最多3条，每条不超过45个汉字；依据最多5条；下一步最多3条。"
        "不要输出Markdown加粗符号、JSON、英文变量名（保留TaskID/EvidenceRef等编号即可），不要重复同一事实。"
        "总长度控制在600个汉字以内。"
    )
    user_payload = {
        "context": context,
        "readonly_adapter_result": adapter,
        "business_findings": adapter.get("business_findings", []),
        "workflow_contract": {
            "authoritative_metrics_are_immutable": True,
            "validated_findings_are_explanatory": True,
            "data_gaps_must_be_explained_before_actions": True,
            "high_risk_actions_require_human_confirmation": True,
        },
        "user_query": query,
    }
    prompt = system + "\n\n" + json.dumps(user_payload, ensure_ascii=False)
    prompt_file = None
    try:
        # OMP performs a small SQLite migration even for --no-session.  Give
        # the child process an isolated writable home so a locked/read-only
        # desktop profile cannot make the bridge look healthy while requests
        # fail at startup.
        runtime_home = ROOT / ".omp" / "runtime-home"
        (runtime_home / ".omp" / "agent").mkdir(parents=True, exist_ok=True)
        source_cfg = Path(r"C:\Users\zhr12\.omp\agent\models.yml")
        source_setup = Path(r"C:\Users\zhr12\.omp\agent\config.yml")
        for src in (source_cfg, source_setup):
            dst = runtime_home / ".omp" / "agent" / src.name
            if src.is_file() and not dst.exists():
                dst.write_bytes(src.read_bytes())
        child_env = normalized_child_env(**{env_name: api_key, "PYTHONUTF8": "1"})
        child_env["HOME"] = str(runtime_home)
        child_env["USERPROFILE"] = str(runtime_home)
        # Bun/OMP on Windows may resolve its SQLite state directory through
        # APPDATA/LOCALAPPDATA instead of HOME. Keep every user-data root in
        # the isolated writable runtime home so a locked desktop profile
        # cannot make the bridge report healthy while model calls fail with
        # SQLITE_READONLY during schema migration.
        child_env["APPDATA"] = str(runtime_home / "AppData" / "Roaming")
        child_env["LOCALAPPDATA"] = str(runtime_home / "AppData" / "Local")
        child_env["XDG_CONFIG_HOME"] = str(runtime_home / ".config")
        child_env["XDG_DATA_HOME"] = str(runtime_home / ".local" / "share")
        for data_root in (
            runtime_home / "AppData" / "Roaming",
            runtime_home / "AppData" / "Local",
            runtime_home / ".config",
            runtime_home / ".local" / "share",
        ):
            data_root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".md", prefix="bifrost_ai_", delete=False
        ) as handle:
            handle.write(prompt)
            prompt_file = Path(handle.name)
        result = subprocess.run(
            [str(OMP_EXE), "--model", "custom-grok/grok-4.6", "--no-session", "--no-tools", "-p", f"@{prompt_file}"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            env=child_env,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("OMP_PROVIDER_TIMEOUT") from exc
    except OSError as exc:
        raise RuntimeError(f"OMP_CLI_EXEC_FAILED: {exc.__class__.__name__}") from exc
    finally:
        if prompt_file and prompt_file.exists():
            prompt_file.unlink(missing_ok=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().replace("\n", " ")[-240:]
        raise RuntimeError("OMP_PROVIDER_FAILED" + (f": {detail}" if detail else ""))
    answer = (result.stdout or "").strip()
    # OMP may print a progress line before the model answer.
    answer = re.sub(r"^Working\.\.\.\s*", "", answer, flags=re.IGNORECASE).strip()
    if not answer:
        raise RuntimeError("OMP_PROVIDER_EMPTY_RESPONSE")
    return answer


def build_local_ai_fallback(query: str, context: dict[str, Any], adapter: dict[str, Any]) -> str:
    """Data-backed answer used only when the external model is unavailable.

    It is deliberately explicit about the mode: it summarizes verified
    adapter facts and never pretends that a model call succeeded.
    """
    metrics = adapter.get("authoritative_metrics") or adapter.get("metrics") or {}
    findings = adapter.get("business_findings") or []
    lines = []
    if isinstance(metrics, dict):
        for key in ("oee", "availability", "performance_rate", "quality_rate", "yield"):
            value = metrics.get(key)
            if isinstance(value, dict):
                value = value.get("value")
            if isinstance(value, (int, float)):
                label = {"oee":"OEE", "availability":"开动率", "performance_rate":"性能率", "quality_rate":"良品率", "yield":"良品率"}[key]
                lines.append(f"{label}{value*100:.1f}%" if abs(value) <= 1 else f"{label}{value:.1f}%")
    summary = "、".join(lines) if lines else "当前适配结果未提供可核验指标"
    finding_text = []
    if isinstance(findings, list):
        for item in findings[:3]:
            if isinstance(item, dict):
                text = item.get("text") or item.get("summary") or item.get("title")
                if text:
                    finding_text.append(str(text))
    return (
        "当前为本地数据解释模式（模型服务暂不可用）。\n"
        f"结论：{summary}。\n"
        + ("重点：" + "；".join(finding_text) + "。\n" if finding_text else "重点：当前结果没有足够的异常证据，需要继续查看班次、停机和质量明细。\n")
        + "依据：以上内容仅来自当前角色、产线和时间范围内已核验的适配数据。\n"
        + "下一步：按产线→班次→停机/不良记录下钻；涉及停线、排产或解除冻结的动作需人工确认。"
    )


def _unique_strings(values: Any) -> list[str]:
    result: list[str] = []
    if not isinstance(values, list):
        return result
    for value in values:
        if isinstance(value, str) and value and value not in result:
            result.append(value)
    return result


def _model_headline(answer: str) -> str:
    """Extract a compact display headline without trusting model structure."""
    lines = [line.strip(" -*#：:，,。 ") for line in answer.replace("\r", "").split("\n")]
    lines = [line for line in lines if line]
    if not lines:
        return "当前没有可展示的分析结论"
    for line in lines:
        if line in {"结论", "结论：", "结论:"}:
            continue
        if line.startswith(("依据", "下一步", "本周最大三个风险")):
            continue
        return re.sub(r"^(?:\*\*)?(?:结论|核心结论)(?:\*\*)?[：:]\s*", "", line)[:180]
    return re.sub(r"^(?:\*\*)?(?:结论|核心结论)(?:\*\*)?[：:]\s*", "", lines[0])[:180]


def _task_for_role(adapter: dict[str, Any], role: str) -> list[dict[str, Any]]:
    tasks = adapter.get("tasks", [])
    if not isinstance(tasks, list):
        return []
    task_agent = {
        "line": "production-specialist",
        "quality": "quality-specialist",
        "equipment": "production-specialist",
        "process": "production-specialist",
        "supply": "supply-specialist",
    }.get(role)
    if role == "factory" or task_agent is None:
        return [task for task in tasks if isinstance(task, dict)]
    selected = [task for task in tasks if isinstance(task, dict) and task.get("agent_id") == task_agent]
    # Unknown/empty role mappings must not fall back to the full adapter.
    # Returning an empty set makes missing role evidence explicit instead of
    # leaking another role's tasks into the model context.
    return selected


def infer_view_request(query: str, context: dict[str, Any]) -> dict[str, Any] | None:
    """Turn a natural-language request into a read-only view specification.

    The specification is deliberately small and auditable: it selects existing
    source-backed charts; it never invents a KPI or writes a new dashboard.
    """
    text = str(query or "").lower()
    if not any(token in text for token in ("看板", "趋势", "走势", "图表", "排行", "分析", "对比", "明细")):
        return None
    window = context.get("time_window", "last_7_shifts")
    if any(token in text for token in ("30天", "三十天", "30个班", "一个月")):
        window = "last_30_shifts"
    elif any(token in text for token in ("7天", "七天", "7个班", "七个班", "一周")):
        window = "last_7_shifts"
    role = context.get("role", "factory")
    if any(token in text for token in ("质量", "良率", "不良", "缺陷")):
        role = "quality"
    elif any(token in text for token in ("设备", "停机", "故障", "维修")):
        role = "equipment"
    elif any(token in text for token in ("工艺", "换产", "工序")):
        role = "process"
    elif any(token in text for token in ("供应", "物料", "缺料", "库存")):
        role = "supply"
    elif any(token in text for token in ("线长", "产线", "生产线")):
        role = "line"
    elif any(token in text for token in ("厂长", "全厂", "所有产线", "总体")):
        role = "factory"
    scope = context.get("scope", "ALL_LINES")
    for tokens, candidate_scope in (
        (("一号产线", "一线", "s01"), "LINE-S01"),
        (("二号产线", "二线", "s02"), "LINE-S02"),
        (("三号产线", "三线", "s03"), "LINE-S03"),
    ):
        if any(token in text for token in tokens):
            scope = candidate_scope
            break
    charts: list[dict[str, str]] = []
    if any(token in text for token in ("趋势", "走势", "变化")):
        metric = "质量率" if role == "quality" else ("停机时长" if role == "equipment" else "OEE")
        charts.append({"chart_id": "oee_trend", "title_zh": f"{metric}趋势"})
    if any(token in text for token in ("停机", "故障")):
        charts.append({"chart_id": "stop_pareto", "title_zh": "主要停机原因及累计影响"})
    if any(token in text for token in ("不良", "缺陷", "良率")):
        charts.append({"chart_id": "defect_table", "title_zh": "主要缺陷及累计影响"})
    if any(token in text for token in ("排行", "对比")):
        charts.append({"chart_id": "ranking_bar", "title_zh": "产线指标对比"})
    if not charts:
        charts.append({"chart_id": "oee_trend", "title_zh": "OEE趋势"})
    return {
        "view_type": "generated_readonly_view",
        "title_zh": "按问题生成的临时看板",
        "role": role,
        "scope": scope,
        "time_window": window,
        "charts": charts[:3],
        "data_policy": "仅从当前数据源已有记录生成；没有数据的图表显示为暂无数据，不补造指标。",
    }


def build_result_contract(answer: str, context: dict[str, Any], adapter: dict[str, Any], query: str = "") -> dict[str, Any]:
    """Create a stable, auditable UI contract from adapter facts plus model prose.

    The model text remains available as ``answer`` for compatibility, while all
    cards shown by the new renderer are sourced from the fixed read-only adapter.
    """
    tasks = _task_for_role(adapter, str(context.get("role", "factory")))
    metrics: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    evidence: list[str] = []
    statuses: list[str] = []
    confidence_values: list[float] = []
    for task in tasks:
        status = task.get("status")
        if isinstance(status, str):
            statuses.append(status)
        confidence = task.get("confidence")
        if isinstance(confidence, (int, float)):
            confidence_values.append(float(confidence))
        for metric in task.get("metrics", []) if isinstance(task.get("metrics"), list) else []:
            if isinstance(metric, dict):
                metrics.append({
                    "metric_id": metric.get("metric_id"),
                    "label": metric.get("label") or metric.get("semantic_field"),
                    "value": metric.get("value"),
                    "display_format": metric.get("display_format", "0.0%"),
                    "semantic_field": metric.get("semantic_field"),
                    "evidence_refs": _unique_strings(metric.get("evidence_refs")),
                })
                evidence.extend(_unique_strings(metric.get("evidence_refs")))
        for cause in task.get("causes", []) if isinstance(task.get("causes"), list) else []:
            if isinstance(cause, dict):
                refs = _unique_strings(cause.get("evidence_refs"))
                risks.append({
                    "title": str(cause.get("statement") or cause.get("category") or "已识别影响因素")[:180],
                    "severity": str(task.get("severity") or status or "unknown"),
                    "category": cause.get("category"),
                    "evidence_refs": refs,
                })
                evidence.extend(refs)
        for action in task.get("recommended_actions", []) if isinstance(task.get("recommended_actions"), list) else []:
            if isinstance(action, dict):
                actions.append({
                    "action_id": action.get("action_id"),
                    "title": action.get("action") or "待确认动作",
                    "priority": action.get("priority", "medium"),
                    "needs_human_confirmation": bool(action.get("needs_human_confirmation")),
                    "prohibited_auto_execute": bool(action.get("prohibited_auto_execute", True)),
                    "evidence_refs": _unique_strings(action.get("evidence_refs")),
                })
                evidence.extend(_unique_strings(action.get("evidence_refs")))
        for gap in task.get("data_gaps", []) if isinstance(task.get("data_gaps"), list) else []:
            if isinstance(gap, dict):
                gaps.append({
                    "field": gap.get("semantic_field") or gap.get("semantic_entity"),
                    "reason": gap.get("reason"),
                    "resolution": gap.get("required_resolution"),
                })
        evidence.extend(_unique_strings(task.get("evidence_refs")))

    if any(status in {"needs_confirmation", "待人工确认"} for status in statuses):
        overall_status = "needs_confirmation"
    elif any(status in {"warning", "预警"} for status in statuses):
        overall_status = "warning"
    elif statuses:
        overall_status = "completed"
    else:
        overall_status = "no_data"
    evidence = _unique_strings(evidence)
    unique_metrics: list[dict[str, Any]] = []
    metric_ids: set[str] = set()
    for metric in metrics:
        metric_id = str(metric.get("metric_id") or metric.get("semantic_field") or len(unique_metrics))
        if metric_id in metric_ids:
            continue
        metric_ids.add(metric_id)
        unique_metrics.append(metric)
    unique_risks = risks[:6]
    business_findings = adapter.get("business_findings") or []
    if not isinstance(business_findings, list):
        business_findings = []
    business_findings = [
        {
            "insight_id": item.get("insight_id"),
            "title_zh": item.get("title_zh") or "已核验分析",
            "summary": item.get("summary") or item.get("business_summary") or item.get("conclusion"),
            "metrics": item.get("metrics") if isinstance(item.get("metrics"), list) else [],
            "evidence_refs": _unique_strings(item.get("evidence_refs")),
            "requires_human_confirmation": bool(item.get("requires_human_confirmation")),
        }
        for item in business_findings
        if isinstance(item, dict)
    ]
    return {
        "contract_version": RESULT_CONTRACT_VERSION,
        "run_id": f"UI-{adapter.get('event', {}).get('event_id', 'UNKNOWN')}",
        "status": overall_status,
        "role": context.get("role", "factory"),
        "scope": context.get("scope", "ALL_LINES"),
        "time_window": context.get("time_window", "last_7_shifts"),
        # Preserve the event selected by the caller when present; otherwise
        # retain the adapter's canonical event id for backwards compatibility.
        "event_id": context.get("event_id") or adapter.get("event", {}).get("event_id"),
        "headline": _model_headline(answer),
        "kpis": unique_metrics,
        "risks": unique_risks,
        "evidence_refs": evidence,
        "recommended_actions": actions,
        "needs_human_confirmation": any(action["needs_human_confirmation"] for action in actions)
        or overall_status == "needs_confirmation",
        "data_gaps": gaps,
        "business_findings": business_findings,
        "view_request": infer_view_request(query, context),
        "confidence": round(sum(confidence_values) / len(confidence_values), 4) if confidence_values else None,
        "source": {
            "adapter": adapter.get("adapter"),
            "adapter_version": adapter.get("adapter_version"),
            "readonly": adapter.get("source_write_performed") is False,
            "source_write_performed": adapter.get("source_write_performed", False),
        },
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(RUNTIME), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        print("[bifrost-ui] " + (format % args))

    def end_headers(self) -> None:  # noqa: N802
        # Source modules and payloads are local development artifacts. Avoid
        # browser 304 responses keeping an older UI after a branch update.
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        route = self.path.split("?", 1)[0]
        if route == "/api/rule-defaults":
            try:
                defaults = json.loads(DEFAULT_RULE_SET.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                json_response(self, 500, {"status": "error", "error": "RULE_DEFAULTS_UNAVAILABLE", "detail": str(exc)})
                return
            json_response(self, 200, {
                "status": "ok",
                "rule_set": defaults,
                "input_schema": build_input_schema(defaults),
                "rule_binding": {
                    "source": "local_demo_rule_set",
                    "rule_set_id": defaults.get("rule_set_id"),
                    "rule_version": defaults.get("rule_version"),
                    "status": defaults.get("status"),
                    "message": "试算只针对当前本地规则草稿；若看板载荷未携带相同规则版本，不得视为正式规则变更。",
                },
                "contract_version": "BIFROST-RULE-DEFINITIONS-v1",
                "readonly": True,
                "source_write_performed": False,
            })
            return
        if route == "/api/health":
            configured = provider_config()
            json_response(
                self,
                200,
                {
                    "status": "ok",
                    "service": "bifrost-local-bridge",
                    "bridge_version": BRIDGE_VERSION,
                    "ai_provider": "custom-grok/grok-4.6",
                    "ai_backend": "omp-cli",
                    "ai_provider_configured": configured is not None,
                    "omp_available": OMP_EXE.is_file(),
                    "adapter_available": ADAPTER.is_file(),
                    "peer_adapter_available": PEER_ADAPTER.is_file(),
                    "readonly": True,
                    "source_write_performed": False,
                },
            )
            return
        if route == "/api/presentation-semantics":
            json_response(self, 200, {
                "status": "ok",
                "contract_version": "BIFROST-PRESENTATION-SEMANTICS-v1",
                "source_write_performed": False,
                "raw_fields_visible_in_business_view": False,
                "message": "业务页面显示中文语义，原始字段仅在证据详情中展示",
            })
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        route = self.path.split("?", 1)[0]
        if route not in {"/api/ai-command", "/api/rule-simulate", "/api/rule-submit-draft", "/api/governance-action-draft", "/api/data-adapt", "/api/peer-postprocess"}:
            json_response(self, 404, {"status": "error", "error": "NOT_FOUND"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY:
            json_response(self, 400, {"status": "error", "error": "INVALID_BODY_SIZE"})
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            json_response(self, 400, {"status": "error", "error": "INVALID_JSON"})
            return
        if route == "/api/rule-simulate":
            rows = body.get("rows") if isinstance(body, dict) else None
            candidate = body.get("candidate_rule_set") if isinstance(body, dict) else None
            if not isinstance(rows, list) or not rows or len(rows) > 1000:
                json_response(self, 400, {"status": "error", "error": "INVALID_ROWS", "readonly": True})
                return
            if not isinstance(candidate, dict):
                json_response(self, 400, {"status": "error", "error": "INVALID_CANDIDATE_RULE_SET", "readonly": True})
                return
            context = {
                key: body.get(key)
                for key in ("dataset_id", "time_window", "source_payload_sha256")
                if body.get(key) not in (None, "")
            }
            try:
                simulation = simulate_change(DEFAULT_RULE_SET, candidate, rows, context=context)
            except (RuleError, TypeError, KeyError) as exc:
                json_response(self, 400, {"status": "error", "error": "RULE_VALIDATION_FAILED", "detail": str(exc), "readonly": True})
                return
            json_response(self, 200, {
                "status": "ok",
                "simulation": simulation,
                "contract_version": "BIFROST-RULE-SIMULATION-v1",
                "readonly": True,
                "source_write_performed": False,
                "actor_can_execute": False,
            })
            return
        if route == "/api/rule-submit-draft":
            candidate = body.get("candidate_rule_set") if isinstance(body, dict) else None
            simulation = body.get("simulation") if isinstance(body, dict) else None
            try:
                draft = submit_rule_draft(candidate, simulation)
            except (OSError, RuleError, TypeError, ValueError) as exc:
                json_response(self, 400, {"status": "error", "error": "RULE_DRAFT_REJECTED", "detail": str(exc), "readonly": True, "source_write_performed": False})
                return
            json_response(self, 200, {"status": "ok", "draft": draft, "readonly": True, "source_write_performed": False, "actor_can_execute": False})
            return
        if route == "/api/governance-action-draft":
            issue = body.get("issue") if isinstance(body, dict) else None
            role = body.get("role", "factory") if isinstance(body, dict) else "factory"
            try:
                draft = submit_governance_action_draft(issue, role=role)
            except (ValueError, TypeError) as exc:
                json_response(self, 400, {"status": "error", "error": "GOVERNANCE_DRAFT_REJECTED", "detail": str(exc), "readonly": True, "source_write_performed": False})
                return
            json_response(self, 200, {"status": "ok", "draft": draft, "readonly": True, "source_write_performed": False, "actor_can_execute": False})
            return
        if route == "/api/data-adapt":
            source_path = body.get("source_path") if isinstance(body, dict) else None
            source_id = body.get("source_id", "SOURCE-LOCAL-001") if isinstance(body, dict) else "SOURCE-LOCAL-001"
            confirmations = body.get("confirmations", []) if isinstance(body, dict) else []
            drilldown_filters = body.get("drilldown_filters") if isinstance(body, dict) else None
            if not isinstance(source_path, str) or not source_path.strip():
                json_response(self, 400, {"status": "error", "error": "SOURCE_PATH_REQUIRED", "readonly": True})
                return
            try:
                candidate = Path(source_path).expanduser().resolve()
                allowed_roots = [ROOT.resolve(), Path(r"D:\Edgedownload").resolve(), Path(r"D:\UserData\Temp").resolve()]
                candidate_text = os.path.normcase(str(candidate)).rstrip("\\/")
                allowed_text = [os.path.normcase(str(root)).rstrip("\\/") for root in allowed_roots]
                if not any(candidate_text == root or candidate_text.startswith(root + os.sep) for root in allowed_text):
                    raise PermissionError("source_path_outside_allowed_roots")
                if not isinstance(confirmations, list) or not all(isinstance(item, str) for item in confirmations):
                    raise ValueError("confirmations_must_be_string_list")
                if drilldown_filters is not None and not isinstance(drilldown_filters, dict):
                    raise ValueError("drilldown_filters_must_be_object")
                result = AutoAdaptPipeline().run(candidate, str(source_id), confirmations, drilldown_filters)
                # Dynamic data can feed the peer Skill contract only through
                # an additive task bridge.  Pending mappings never produce a
                # peer input, and the bridge itself remains read-only.
                if result.get("mapping_status") == "approved":
                    result["peer_task_input"] = build_peer_task_payload(
                        result.get("generated_payloads") or {},
                        drilldown_result=result.get("drilldown_result"),
                        drilldown_filters=drilldown_filters,
                    )
                    # Run the peer executors immediately on the bridge output,
                    # but keep the result additive/read-only.  Formal insight
                    # promotion still requires explicit approval and physical
                    # evidence binding; this endpoint never publishes it.
                    result["peer_analysis"] = run_peer_postprocessors(result["peer_task_input"])
                    generated = result.get("generated_payloads") or {}
                    generated_event = generated.get("event") or {}
                    generated_overview = generated.get("overview") or {}
                    formal = build_formal_derived_insights(
                        result["peer_analysis"],
                        event_id=str(generated_event.get("event_id") or result["peer_task_input"].get("event_id")),
                        dataset_id=(
                            generated_overview.get("dataset_id")
                            or (generated_overview.get("source_profile") or {}).get("dataset_id")
                            or (generated_overview.get("source_profile") or {}).get("source_sha256")
                        ),
                    )
                    # Additive only: authoritative metrics and role KPI arrays
                    # remain byte-for-byte unchanged. Findings are projected
                    # into each matching role slice so business consumers see
                    # one coherent role result instead of a separate peer card.
                    generated_event["formal_derived_insights"] = formal
                    generated_event["formal_findings"] = formal.get("role_findings", {})
                    for role_slice in generated_event.get("roles") or []:
                        if not isinstance(role_slice, dict):
                            continue
                        role_name = role_slice.get("role")
                        findings = formal.get("role_findings", {}).get(role_name, [])
                        if findings:
                            role_slice["findings"] = findings
                            role_slice["decision_support"] = [
                                {
                                    "title": item.get("summary") or item.get("title_zh"),
                                    "evidence_refs": item.get("evidence_refs", []),
                                    "requires_human_confirmation": item.get("requires_human_confirmation", False),
                                }
                                for item in findings
                            ]
                    generated_overview["formal_derived_insights"] = formal
                    generated_overview["role_findings"] = formal.get("role_findings", {})
                    generated["event"] = generated_event
                    generated["overview"] = generated_overview
                else:
                    result["peer_task_input"] = None
                    result["peer_analysis"] = None
            except (OSError, ValueError, PermissionError) as exc:
                json_response(self, 400, {"status": "blocked", "error": "DATA_ADAPT_FAILED", "detail": str(exc), "readonly": True})
                return
            json_response(self, 200, {"status": "ok", "result": result, "readonly": True, "source_write_performed": False})
            return
        if route == "/api/peer-postprocess":
            payload = body.get("payload") if isinstance(body, dict) else None
            role = body.get("role") if isinstance(body, dict) else None
            if not isinstance(payload, dict):
                json_response(self, 400, {"status": "error", "error": "PEER_PAYLOAD_REQUIRED", "readonly": True})
                return
            if role not in VALID_ROLES:
                json_response(self, 400, {"status": "error", "error": "INVALID_ROLE", "readonly": True})
                return
            try:
                result = run_peer_postprocessors(payload, role)
            except (TypeError, ValueError) as exc:
                json_response(self, 400, {"status": "blocked", "error": "PEER_POSTPROCESS_FAILED", "detail": str(exc), "readonly": True})
                return
            json_response(self, 200, {"status": "ok", "result": result, "readonly": True, "source_write_performed": False})
            return
        query = body.get("query") if isinstance(body, dict) else None
        role = body.get("role", "factory") if isinstance(body, dict) else "factory"
        if not isinstance(query, str) or not query.strip() or len(query) > 2000:
            json_response(self, 400, {"status": "error", "error": "INVALID_QUERY"})
            return
        scope = body.get("scope", "ALL_LINES") if isinstance(body, dict) else "ALL_LINES"
        time_window = body.get("time_window", "last_7_shifts") if isinstance(body, dict) else "last_7_shifts"
        event_id = body.get("event_id") if isinstance(body, dict) else None
        workflow_snapshot = body.get("workflow_snapshot") if isinstance(body, dict) else None
        if workflow_snapshot is not None and not isinstance(workflow_snapshot, dict):
            json_response(self, 400, {"status": "error", "error": "INVALID_WORKFLOW_SNAPSHOT", "readonly": True})
            return
        try:
            validate_ai_context(role=role, scope=scope, time_window=time_window, event_id=event_id)
        except ValueError as exc:
            json_response(self, 400, {"status": "error", "error": str(exc), "readonly": True})
            return
        if not provider_config():
            json_response(self, 503, {"status": "blocked", "error": "AI_PROVIDER_NOT_CONFIGURED"})
            return
        try:
            runtime_mode = body.get("runtime_mode", "approved-payload")
            adapter = run_adapter(peer=runtime_mode == "adapter-test")
            scoped_adapter = adapter_for_context(adapter, role=role, scope=scope, event_id=event_id)
            context = {
                "role": role,
                "scope": scope,
                "time_window": time_window,
                "event_id": event_id,
                "runtime_mode": runtime_mode,
                "peer_integration": scoped_adapter.get("peer_integration", {}),
            }
            if isinstance(workflow_snapshot, dict):
                # Keep the client snapshot bounded and explanatory. It can
                # enrich the answer, but it is never treated as an authority
                # source or used to overwrite adapter KPIs.
                context["workflow_snapshot"] = {
                    "dataset_id": workflow_snapshot.get("dataset_id"),
                    "source_payload_sha256": workflow_snapshot.get("source_payload_sha256"),
                    "rule_version": workflow_snapshot.get("rule_version"),
                    "formal_findings": workflow_snapshot.get("formal_findings") if isinstance(workflow_snapshot.get("formal_findings"), list) else [],
                    "event_summary": workflow_snapshot.get("event_summary") if isinstance(workflow_snapshot.get("event_summary"), dict) else None,
                }
                if not scoped_adapter.get("business_findings") and context["workflow_snapshot"]["formal_findings"]:
                    scoped_adapter["business_findings"] = copy.deepcopy(context["workflow_snapshot"]["formal_findings"][:6])
            answer = call_model_via_omp(query.strip(), context, scoped_adapter)
            result_contract = build_result_contract(answer, context, scoped_adapter, query.strip())
        except RuntimeError as exc:
            code = str(exc)
            if code.startswith(("AI_PROVIDER", "OMP_PROVIDER")):
                # Keep the assistant usable for the demo even when the model
                # endpoint is temporarily unavailable.  This is a transparent
                # local, data-backed explanation—not a fabricated model reply.
                fallback = build_local_ai_fallback(query.strip(), context, scoped_adapter)
                fallback_contract = build_result_contract(fallback, context, scoped_adapter, query.strip())
                json_response(self, 200, {"status": "ok", "answer": fallback,
                    "result_contract": fallback_contract, "contract_version": RESULT_CONTRACT_VERSION,
                    "mode": "local-data-fallback", "provider_error": code.split(":", 1)[0],
                    "readonly": True, "source_write_performed": False, "actor_can_execute": False})
                return
            status = 502
            # Never expose OMP/provider stderr or stack traces through the API.
            # Keep only the stable machine-readable prefix; the UI maps it to
            # a user-facing Chinese message.
            safe_code = code.split(":", 1)[0].strip() or "AI_REQUEST_BLOCKED"
            json_response(self, status, {"status": "blocked", "error": safe_code, "readonly": True})
            return
        json_response(
            self,
            200,
            {
                "status": "ok",
                "answer": answer,
                "result_contract": result_contract,
                "contract_version": RESULT_CONTRACT_VERSION,
                "mode": "custom-grok-via-omp-cli",
                "provider": "custom-grok/grok-4.6",
                "event_id": result_contract.get("event_id"),
                "peer_integration": scoped_adapter.get("peer_integration", {}),
                "readonly": True,
                "source_write_performed": False,
                "actor_can_execute": False,
            },
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="BIFROST UI + local custom-grok bridge")
    parser.add_argument("--port", type=int, default=4173)
    args = parser.parse_args()
    if not RUNTIME.is_dir():
        raise SystemExit(f"runtime package missing: {RUNTIME}")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"BIFROST UI + API on http://127.0.0.1:{args.port}/")
    print(f"Bridge version: {BRIDGE_VERSION}")
    print("AI backend: OMP CLI -> custom-grok/grok-4.6 (server-side key only)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBIFROST bridge stopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
