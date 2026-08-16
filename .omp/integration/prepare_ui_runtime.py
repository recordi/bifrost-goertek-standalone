#!/usr/bin/env python3
"""构建 BIFROST UI 的只读运行包。

固定复制 UI 基线，并解压已批准的 Overview/Event 载荷到 UI 代码约定的
artifacts/目录。此阶段不把 OMP 适配器结果冒充成企业载荷。
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "artifacts" / "ui-baseline-v3.2.1"
RUNTIME = ROOT / "output" / "bifrost-ui-runtime"
ASSETS = ROOT / ".omp" / "skills" / "bifrost-decision-readonly" / "references" / "runtime_assets"

PAYLOADS = {
    "BIFROST_OVERVIEW_PAYLOAD_v2.1.json": ASSETS / "BIFROST_OVERVIEW_PAYLOAD_v2.1.json.gz",
    "BIFROST_EVENT_PAYLOAD_v1.4.json": ASSETS / "BIFROST_EVENT_PAYLOAD_v1.4.json.gz",
}


def patch_ai_drawer(path: Path) -> None:
    """Add the local read-only bridge to the generated UI copy only."""
    source = path.read_text(encoding="utf-8")
    ai_start = source.index("  // 检测是否存在真实 AilyAdapter")
    handle_start = source.index("  const handleSend", ai_start)
    onboarding_start = source.index("  const [showOnboarding", handle_start)

    logic = '''  // Local bridge health is checked server-side; no API key reaches the browser.
  const hasAilyAdapter = typeof window !== "undefined" && !!window.AilyAdapter;
  const [apiConnected, setApiConnected] = useState(false);
  useEffect(() => {
    fetch("/api/health", { cache: "no-store" })
      .then((response) => response.ok ? response.json() : null)
      .then((payload) => setApiConnected(payload?.status === "ok" && payload?.ai_provider_configured === true))
      .catch(() => setApiConnected(false));
  }, []);

  const aiConnected = apiConnected || ailyConnected;
  const aiUsable = apiConnected || (ailyConnected && hasAilyAdapter);
  const aiMisconfigured = !apiConnected && ailyConnected && !hasAilyAdapter;

  const dispatchCommand = useCallback(async (text) => {
    if (apiConnected) {
      const response = await fetch("/api/ai-command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: text,
          role: context?.role || role,
          scope: context?.scope || "ALL_LINES",
          time_window: context?.timeWindow || "last_7_shifts",
          event_id: context?.eventId || null,
          runtime_mode: BIFROST_DATA.runtime_mode || "approved-payload",
        }),
      });
      const payload = await response.json();
      if (!response.ok || payload.status !== "ok") {
        throw new Error(payload.error || "AI服务调用失败");
      }
      setMessages((prev) => [...prev, { type: "ai", text: payload.answer }]);
      setAiState("ready");
      return payload;
    }
    if (window.AilyAdapter && typeof window.AilyAdapter.sendCommand === "function") {
      const result = await window.AilyAdapter.sendCommand({
        role: context?.role || role,
        scope: context?.scope || "ALL_LINES",
        timeWindow: context?.timeWindow || "last_7_shifts",
        eventId: context?.eventId || null,
        query: text,
      });
      if (result?.runId) setAiState("analyzing");
      return result;
    }
    throw new Error("AI服务未连接");
  }, [apiConnected, role, context]);

'''
    source = source[:ai_start] + logic + source[handle_start:]
    handle_start = source.index("  const handleSend", ai_start)
    onboarding_start = source.index("  const [showOnboarding", handle_start)
    handlers = '''  const handleSend = useCallback(() => {
    if (!aiUsable) return;
    const text = input.trim();
    if (!text) return;
    setMessages((prev) => [...prev, { type: "user", text }]);
    setInput("");
    setAiState("thinking");
    dispatchCommand(text).catch((error) => {
      setMessages((prev) => [...prev, { type: "ai", text: `AI服务调用失败：${error?.message || "请检查本地桥接与网络连接"}` }]);
      setAiState("failed");
    });
  }, [input, aiUsable, dispatchCommand]);

  const handleQuickQuestion = (q) => {
    if (!aiUsable) return;
    setInput(q);
    requestAnimationFrame(() => {
      setMessages((prev) => [...prev, { type: "user", text: q }]);
      setInput("");
      setAiState("thinking");
      dispatchCommand(q).catch((error) => {
        setMessages((prev) => [...prev, { type: "ai", text: `AI服务调用失败：${error?.message || "请检查本地桥接与网络连接"}` }]);
        setAiState("failed");
      });
    });
  };

'''
    source = source[:handle_start] + handlers + source[onboarding_start:]
    # All user-facing connection checks below the state declaration use the
    # combined local-bridge/Aily status. Keep the internal ailyConnected logic.
    tail = source[onboarding_start:].replace("ailyConnected", "aiConnected")
    source = source[:onboarding_start] + tail
    # The header is part of the returned JSX but may precede the original
    # onboarding marker after handler replacement; patch its two explicit
    # expressions defensively so the badge cannot regress to Aily-only state.
    source = source.replace(
        '<Badge type={ailyConnected ? "success" : "default"} dot>',
        '<Badge type={aiConnected ? "success" : "default"} dot>',
    ).replace(
        '{t_aiStatus(ailyConnected ? "ready" : "disabled")}',
        '{apiConnected ? "本地桥接就绪" : t_aiStatus(aiConnected ? "ready" : "disabled")}',
    )
    source = source.replace(
        "AI 助手尚未连接，接入后可发送指令。",
        "AI 助手尚未连接，启动本地桥接服务后可发送指令。",
    )
    path.write_text(source, encoding="utf-8")


def patch_chart_readability(path: Path) -> None:
    """Make long date axes readable without changing chart data."""
    source = path.read_text(encoding="utf-8")
    old = 'axisLabel: { fontSize: 11, color: "#8a95a6", interval: Math.floor(dates.length / 8) },'
    new = '''axisLabel: {
        fontSize: 11,
        color: "#8a95a6",
        interval: dates.length > 8 ? Math.ceil(dates.length / 8) - 1 : 0,
        rotate: dates.length > 14 ? 30 : 0,
        hideOverlap: true,
        formatter: (value) => String(value).length >= 10 ? String(value).slice(5) : value,
      },'''
    if old not in source:
        raise SystemExit("trend x-axis contract changed; refusing readability patch")
    path.write_text(source.replace(old, new), encoding="utf-8")


def patch_ai_readability(path: Path) -> None:
    """Render model Markdown-like output as readable Chinese UI blocks."""
    source = path.read_text(encoding="utf-8")
    marker = "// ========== AI 助手抽屉 =========="
    helper = r'''// ========== AI 回答可读性渲染 ==========
const AI_FIELD_LABELS = {
  availability: "开动率",
  performance_rate: "性能率",
  quality_factor: "质量因子",
  unplanned_downtime_minutes: "非计划停机时长",
  blocked_gap_count: "阻塞缺口数",
  supply_insufficient: "供应不足",
  data_gaps: "数据缺口",
  evidence_refs: "证据引用",
  human_confirmation_required: "需要人工确认",
  spc_measurement_points: "SPC测量点",
  sample_rule: "抽样规则",
  mtbf_mttr: "MTBF/MTTR",
  shift_trend: "班次趋势",
  needs_confirmation: "待人工确认",
  warning: "预警",
  PASS: "通过",
};

function localizeAIText(value) {
  let text = String(value || "");
  Object.entries(AI_FIELD_LABELS).forEach(([key, label]) => {
    text = text.replace(new RegExp(`\\b${key}\\b`, "g"), label);
  });
  return text.replace(/\*\*/g, "").replace(/\s+;\s*/g, "；");
}

function AIMessage({ text }) {
  const normalized = localizeAIText(text)
    .replace(/\r/g, "")
    .replace(/\s+(?=\d+\.\s)/g, "\n")
    .replace(/\s+(?=(?:依据|下一步|本周最大三个风险)[：:])/g, "\n");
  const lines = normalized.split("\n").map((line) => line.trim()).filter(Boolean);
  return (
    <div className="ai-readable-content">
      {lines.map((line, index) => {
        const section = line.replace(/^[：:]\s*/, "");
        if (/^(本周最大三个风险|依据|下一步)/.test(section)) {
          return <div key={index} className="ai-readable-heading">{section}</div>;
        }
        const risk = section.match(/^(\d+)\.\s*(.*)$/);
        if (risk) {
          return <div key={index} className="ai-risk-item"><span className="ai-risk-index">{risk[1]}</span><span>{risk[2]}</span></div>;
        }
        if (/^[-•]\s*/.test(section)) {
          return <div key={index} className="ai-readable-bullet">{section.replace(/^[-•]\s*/, "")}</div>;
        }
        return <div key={index} className="ai-readable-paragraph">{section}</div>;
      })}
    </div>
  );
}

'''
    if marker not in source:
        raise SystemExit("AI drawer marker changed; refusing readability patch")
    source = source.replace(marker, helper + marker, 1)
    old_map = '<div key={i} className={`ai-msg ${m.type}`}>{m.text}</div>'
    new_map = '<div key={i} className={`ai-msg ${m.type}`}>{m.type === "ai" ? <AIMessage text={m.text} /> : m.text}</div>'
    if old_map not in source:
        raise SystemExit("AI message renderer changed; refusing readability patch")
    path.write_text(source.replace(old_map, new_map), encoding="utf-8")


def patch_ai_styles(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    marker = ".ai-msg.user {"
    styles = '''.ai-readable-content {
  display: flex;
  flex-direction: column;
  gap: 9px;
  white-space: normal;
}
.ai-readable-heading {
  font-size: 14px;
  font-weight: 700;
  color: var(--c-gray-900);
  padding-bottom: 2px;
  border-bottom: 1px solid var(--c-gray-200);
}
.ai-risk-item {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 9px 10px;
  background: #fff;
  border: 1px solid var(--c-gray-200);
  border-left: 3px solid var(--c-warning);
  border-radius: 6px;
  line-height: 1.6;
}
.ai-risk-index {
  flex: 0 0 20px;
  height: 20px;
  line-height: 20px;
  text-align: center;
  border-radius: 50%;
  background: var(--c-warning-light);
  color: var(--c-warning);
  font-size: 11px;
  font-weight: 700;
}
.ai-readable-bullet { padding-left: 10px; line-height: 1.6; }
.ai-readable-bullet::before { content: "•"; color: var(--c-primary-500); margin-right: 6px; }
.ai-readable-paragraph { line-height: 1.65; }
'''
    if marker not in source:
        raise SystemExit("AI style marker changed; refusing readability patch")
    path.write_text(source.replace(marker, styles + marker, 1), encoding="utf-8")


def patch_peer_overlay_data(path: Path) -> None:
    """Load the additive peer overlay only in generated adapter-test runtime."""
    source = path.read_text(encoding="utf-8")
    source = source.replace(
        "  event: null,\n  loaded: false,",
        "  event: null,\n  peer_overlay: null,\n  peer_enhancements: [],\n  formal_derived_insights: { promotion_status: \"not_available\", formal_integration_status: \"not_attached\", derived_insights: [] },\n  loaded: false,",
        1,
    )
    marker = "  BIFROST_DATA.overview = await overviewRes.json();\n  BIFROST_DATA.event = await eventRes.json();"
    replacement = """  BIFROST_DATA.overview = await overviewRes.json();
  BIFROST_DATA.event = await eventRes.json();
  const formal = BIFROST_DATA.event?.formal_derived_insights;
  BIFROST_DATA.formal_derived_insights = [\"validated\", \"approved\"].includes(formal?.promotion_status) && formal?.formal_integration_status === \"attached_additive\"
    ? formal
    : { promotion_status: formal?.promotion_status || \"not_available\", formal_integration_status: \"not_attached\", derived_insights: [] };
  if (adapterTest) {
    try {
      const peerRes = await fetch("artifacts/BIFROST_PEER_OVERLAY_adapter-test.json");
      if (peerRes.ok) {
        const peerPayload = await peerRes.json();
        BIFROST_DATA.peer_overlay = peerPayload.peer_overlay || null;
        BIFROST_DATA.peer_enhancements = peerPayload.peer_skill_outputs || peerPayload.analysis_enhancements || [];
        BIFROST_DATA.peer_role_projections = peerPayload.role_projections || {};
      }
    } catch (error) {
      BIFROST_DATA.peer_overlay = null;
      BIFROST_DATA.peer_enhancements = [];
    }
  }"""
    if marker not in source:
        raise SystemExit("peer overlay data loader contract changed")
    path.write_text(source.replace(marker, replacement, 1), encoding="utf-8")


def patch_peer_overlay_page(path: Path) -> None:
    """Add a generated-runtime-only additive analysis panel."""
    source = path.read_text(encoding="utf-8")
    component_marker = "function EventsPage("
    component = r'''function PeerOverlayPanel() {
  if (BIFROST_DATA.runtime_mode !== "adapter-test" || !BIFROST_DATA.peer_overlay) return null;
  const overlay = BIFROST_DATA.peer_overlay;
  const enhancements = BIFROST_DATA.peer_enhancements || [];
  const label = {
    "a01-oee-loss-tree": "OEE损失树",
    "a02-pareto": "Pareto原因排序",
    "a07-yield-funnel": "良率漏斗",
    "a03-spc-rules": "SPC门禁",
    "a08-supply-chain-gap": "供应链缺口",
  };
  return (
    <section className="peer-overlay-panel" aria-label="同行能力测试附加分析">
      <div className="peer-overlay-header">
        <div><div className="peer-overlay-title">附加分析（同学能力测试）</div><div className="peer-overlay-subtitle">仅在适配器测试模式显示，不改变原始指标和正式载荷</div></div>
        <span className="peer-overlay-badge">只读</span>
      </div>
      <div className="peer-overlay-grid">
        {enhancements.map((item, index) => {
          const itemLabel = label[item.skill_id] || item.skill_id;
          const blocked = item.status === "blocked";
          const rows = item.branches || item.items || item.stages || [];
          return (
            <article className={`peer-overlay-card ${blocked ? "is-blocked" : ""}`} key={`${item.skill_id}-${index}`}>
              <div className="peer-overlay-card-title">{itemLabel}</div>
              <div className="peer-overlay-card-status">{blocked ? "暂不可判定" : item.status === "available" ? "已生成" : item.status === "not_observed" ? "未观测" : item.status}</div>
              {blocked ? <div className="peer-overlay-muted">缺少：{(item.missing_fields || []).join("、") || "必要输入"}。不计算 Cpk，不宣称过程失控。</div> : rows.length > 0 ? <ul className="peer-overlay-list">{rows.slice(0, 4).map((row, rowIndex) => <li key={rowIndex}><span>{row.category || row.label || row.field || "分析项"}</span><span>{row.statement || row.value || "已绑定证据"}</span></li>)}</ul> : <div className="peer-overlay-muted">当前证据不足，未生成可判定结果。</div>}
              {item.skill_id === "a08-supply-chain-gap" && <div className="peer-overlay-note">供应链缺口单独展示，不作为 OEE 原因。</div>}
              {item.evidence_refs?.length > 0 && <details className="peer-overlay-details"><summary>证据（{item.evidence_refs.length}）</summary><div>{item.evidence_refs.join("、")}</div></details>}
            </article>
          );
        })}
      </div>
      <details className="peer-overlay-details peer-overlay-gaps"><summary>数据治理状态</summary><div>当前运行包未接入原始行数据，治理前置状态：未运行。不会从诊断结果倒推治理结论。</div></details>
    </section>
  );
}

'''
    component += r'''function FormalDerivedInsightsPanel({ role }) {
  const insights = BIFROST_DATA.formal_derived_insights?.derived_insights || [];
  const allowed = { factory: ["a01-oee-loss-tree", "a02-pareto", "a07-yield-funnel", "a08-supply-chain-gap"], line: ["a01-oee-loss-tree", "a07-yield-funnel"], quality: ["a02-pareto", "a03-spc-rules", "a07-yield-funnel"], equipment: ["a01-oee-loss-tree", "a02-pareto"], process: ["a03-spc-rules"], supply: ["a08-supply-chain-gap"] }[role] || [];
  const scoped = insights.filter((item) => allowed.includes(item.skill_id));
  if (!scoped.length) return null;
  const labels = { "a01-oee-loss-tree": "生产损失分解", "a02-pareto": "主要缺陷/停机原因及累计影响", "a07-yield-funnel": "良率问题定位", "a03-spc-rules": "工艺稳定性数据检查", "a08-supply-chain-gap": "物料缺口与交付影响" };
  return <section className="formal-derived-panel" aria-label="已核验的专业分析"><div className="formal-derived-header"><strong>已核验的专业分析</strong><span>正式派生 · 不改主指标</span></div><div className="formal-derived-grid">{scoped.map((item) => <article className="formal-derived-card" key={item.insight_id}><strong>{labels[item.skill_id] || "专业分析"}</strong><div>已绑定 {(item.physical_evidence_refs || []).length} 条物理记录，可作为当前角色的补充判断。</div><details><summary>查看证据与审批信息</summary><div>{(item.physical_evidence_refs || []).map((ref) => \`\${ref.source_table}/\${ref.record_id || ref.record_key}\`).join("、")}</div></details></article>)}</div></section>;
}

'''
    if component_marker not in source:
        raise SystemExit("peer overlay page insertion marker changed")
    source = source.replace(component_marker, component + component_marker, 1)
    render_marker = "      {/* 2."
    if render_marker not in source:
        raise SystemExit("peer overlay render marker changed")
    source = source.replace(render_marker, "      <PeerOverlayPanel />\n      <FormalDerivedInsightsPanel role={role} />\n\n" + render_marker, 1)
    path.write_text(source, encoding="utf-8")


def patch_peer_overlay_styles(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    if ".peer-overlay-panel" in source:
        return
    css = r'''
.peer-overlay-panel{margin:0 0 16px;padding:16px;border:1px solid #d9e2ef;border-radius:10px;background:#f8fbff}
.formal-derived-panel{margin:0 0 16px;padding:16px;border:1px solid #cfe7d8;border-radius:10px;background:#f7fcf8}
.formal-derived-header{display:flex;justify-content:space-between;gap:12px;margin-bottom:12px;color:#1d5b39}
.formal-derived-header span{font-size:12px;color:#28734b}
.formal-derived-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.formal-derived-card{padding:12px;border:1px solid #dcefe2;border-radius:8px;background:#fff;color:#425466;font-size:12px;line-height:1.6}
.formal-derived-card strong{color:#1f5134;font-size:13px}
.formal-derived-card details{margin-top:6px}
.peer-overlay-header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:12px}
.peer-overlay-title{font-size:15px;font-weight:700;color:#16365c}
.peer-overlay-subtitle{margin-top:4px;font-size:12px;color:#65758a}
.peer-overlay-badge{padding:3px 8px;border-radius:999px;background:#e7f4ec;color:#28734b;font-size:11px;white-space:nowrap}
.peer-overlay-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.peer-overlay-card{min-width:0;padding:12px;border:1px solid #e3eaf3;border-radius:8px;background:#fff}
.peer-overlay-card.is-blocked{border-color:#f0c36d;background:#fffaf0}
.peer-overlay-card-title{font-weight:600;color:#263b55;font-size:13px}
.peer-overlay-card-status{margin-top:4px;color:#28734b;font-size:12px}
.is-blocked .peer-overlay-card-status{color:#a96900}
.peer-overlay-list{margin:8px 0 0;padding:0;list-style:none;font-size:12px;color:#516174}
.peer-overlay-list li{display:flex;justify-content:space-between;gap:10px;padding:5px 0;border-top:1px solid #eef2f7}
.peer-overlay-list li span:last-child{color:#1f334b;text-align:right}
.peer-overlay-muted,.peer-overlay-note{margin-top:8px;font-size:12px;line-height:1.6;color:#68788b}
.peer-overlay-note{color:#8a5b12}
.peer-overlay-details{margin-top:10px;font-size:11px;color:#66788d}
.peer-overlay-details summary{cursor:pointer;color:#3b628c}
.peer-overlay-details div{margin-top:5px;word-break:break-all;line-height:1.5}
@media(max-width:900px){.peer-overlay-grid{grid-template-columns:1fr}}
'''
    path.write_text(source + "\n" + css, encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if not BASELINE.is_dir():
        raise SystemExit(f"UI baseline missing: {BASELINE}")
    for target_name, source in PAYLOADS.items():
        if not source.is_file():
            raise SystemExit(f"approved payload asset missing: {source}")

    RUNTIME.mkdir(parents=True, exist_ok=True)
    shutil.copytree(BASELINE, RUNTIME, dirs_exist_ok=True)
    artifact_dir = RUNTIME / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "runtime_package": "BIFROST_UI_RUNTIME",
        "ui_baseline": "v3.2.1",
        "payload_mode": "approved_payload_smoke_test",
        "omp_adapter_connected": False,
        "warning": "此运行包验证 UI 与 Overview/Event 合同兼容；OMP 动态结果尚未替换企业载荷。",
        "payloads": {},
    }
    for target_name, source in PAYLOADS.items():
        target = artifact_dir / target_name
        target.write_bytes(gzip.decompress(source.read_bytes()))
        parsed = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict) or not parsed.get("payload_version"):
            raise SystemExit(f"invalid payload contract: {target_name}")
        manifest["payloads"][target_name] = {
            "sha256": sha256(target),
            "payload_version": parsed["payload_version"],
            "payload_type": parsed.get("payload_type"),
        }

    dynamic_builder = ROOT / ".omp" / "integration" / "build_adapter_test_payloads.py"
    built = subprocess.run(
        [str(Path(r"D:\anaconda3\envs\langchain\python.exe")), str(dynamic_builder)],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
    )
    if built.returncode != 0:
        raise SystemExit(f"adapter-test payload build failed: {built.stdout or built.stderr}")

    peer_runner = ROOT / ".omp" / "integration" / "run_peer_adapters.py"
    peer_run = subprocess.run(
        [str(Path(r"D:\anaconda3\envs\langchain\python.exe")), str(peer_runner)],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
    )
    if peer_run.returncode != 0:
        raise SystemExit(f"peer overlay build failed: {peer_run.stdout or peer_run.stderr}")
    try:
        peer_payload = json.loads(peer_run.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"peer overlay output invalid: {exc}") from exc
    if peer_payload.get("peer_integration", {}).get("status") != "PASS":
        raise SystemExit("peer overlay contract did not pass")
    peer_artifact = artifact_dir / "BIFROST_PEER_OVERLAY_adapter-test.json"
    adapter_event_path = artifact_dir / "BIFROST_EVENT_PAYLOAD_adapter-test.json"
    formal_projection = peer_payload.get("formal_derived_insights", {})
    if adapter_event_path.is_file() and formal_projection.get("formal_integration_status") == "attached_additive":
        adapter_event = json.loads(adapter_event_path.read_text(encoding="utf-8"))
        event_ids = {adapter_event.get("event_id"), adapter_event.get("adapter_event_id")}
        insight_ids = {item.get("event_id") for item in formal_projection.get("derived_insights", [])}
        if event_ids & insight_ids:
            adapter_event["formal_derived_insights"] = formal_projection
            adapter_event_path.write_text(json.dumps(adapter_event, ensure_ascii=False, indent=2), encoding="utf-8")
    peer_artifact.write_text(json.dumps({
        "payload_type": "peer_overlay",
        "payload_version": "PEER-OVERLAY-v1.0",
        "event": peer_payload.get("event", {}),
        "peer_overlay": peer_payload.get("peer_overlay", {}),
        "analysis_enhancements": peer_payload.get("analysis_enhancements", []),
        "peer_skill_outputs": peer_payload.get("peer_skill_outputs", []),
        "role_projections": peer_payload.get("role_projections", {}),
        "governance_findings": peer_payload.get("governance_findings", {}),
        "formal_derived_insights": peer_payload.get("formal_derived_insights", {
            "promotion_status": "not_available",
            "derived_insights": [],
        }),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest["peer_overlay"] = {
        "file": peer_artifact.name,
        "sha256": sha256(peer_artifact),
        "mode": "adapter-test-only",
    }
    # Bind the additive overlay to the stable hash of the exact adapter input.
    # This is distinct from the artifact file hash and lets the runtime reject
    # stale or cross-event peer output without touching authoritative payloads.
    manifest["source_payload_sha256"] = peer_payload.get("peer_overlay", {}).get("source_payload_sha256")

    # Patch only the generated runtime copy. The protected UI baseline remains unchanged.
    data_path = RUNTIME / "src" / "data.jsx"
    data_source = data_path.read_text(encoding="utf-8")
    old_loader = '''  const [overviewRes, eventRes] = await Promise.all([\n    fetch("artifacts/BIFROST_OVERVIEW_PAYLOAD_v2.1.json"),\n    fetch("artifacts/BIFROST_EVENT_PAYLOAD_v1.4.json"),\n  ]);'''
    new_loader = '''  const adapterTest = new URLSearchParams(window.location.search).get("mode") === "adapter-test";\n  const overviewFile = adapterTest ? "artifacts/BIFROST_OVERVIEW_PAYLOAD_adapter-test.json" : "artifacts/BIFROST_OVERVIEW_PAYLOAD_v2.1.json";\n  const eventFile = adapterTest ? "artifacts/BIFROST_EVENT_PAYLOAD_adapter-test.json" : "artifacts/BIFROST_EVENT_PAYLOAD_v1.4.json";\n  const [overviewRes, eventRes] = await Promise.all([\n    fetch(overviewFile),\n    fetch(eventFile),\n  ]);'''
    if old_loader not in data_source:
        raise SystemExit("UI data loader contract changed; refusing generated runtime patch")
    data_source = data_source.replace(old_loader, new_loader).replace(
        "  BIFROST_DATA.loaded = true;",
        "  BIFROST_DATA.runtime_mode = adapterTest ? \"adapter-test\" : \"approved-payload\";\n  BIFROST_DATA.loaded = true;",
    )
    data_path.write_text(data_source, encoding="utf-8")
    patch_peer_overlay_data(data_path)
    patch_chart_readability(data_path)
    patch_ai_drawer(RUNTIME / "src" / "components.jsx")
    patch_ai_readability(RUNTIME / "src" / "components.jsx")
    patch_ai_styles(RUNTIME / "styles.css")
    patch_peer_overlay_page(RUNTIME / "src" / "pages.jsx")
    patch_peer_overlay_styles(RUNTIME / "styles.css")

    app_path = RUNTIME / "src" / "app.jsx"
    app_source = app_path.read_text(encoding="utf-8")
    marker = "        </header>\n\n        {/* 二级导航 / 筛选栏 - 第二行 */}"
    banner = '''        </header>\n\n        {BIFROST_DATA.runtime_mode === "adapter-test" && (\n          <div style={{ padding: "8px 24px", background: "#fff7e6", color: "#ad6800", borderBottom: "1px solid #ffd591", fontSize: "12px" }}>\n            适配器测试模式：数据来自本地只读 Skill 编排，不代表企业生产数据；高风险动作不可执行。\n          </div>\n        )}\n\n        {/* 二级导航 / 筛选栏 - 第二行 */}'''
    if marker not in app_source:
        raise SystemExit("UI topbar contract changed; refusing generated runtime patch")
    app_path.write_text(app_source.replace(marker, banner), encoding="utf-8")
    manifest["adapter_test_mode"] = "?mode=adapter-test"
    manifest["payload_mode"] = "approved_payload_plus_adapter_test"

    (RUNTIME / "BIFROST_UI_RUNTIME_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"status": "PASS", "runtime": str(RUNTIME), "manifest": manifest}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
