/* ===== BIFROST 数据层 (Data Layer) v3.2 =====
   加载 Overview / Event 两个 JSON 载荷，
   封装视图查找、角色视图、产线筛选等工具函数。
   不改数据合同，不改原始字段。
*/

const BIFROST_DATA = {
  overview: null,
  event: null,
  peer_overlay: null,
  peer_enhancements: [],
  peer_overlay_error: null,
  peer_role_projections: {},
  formal_derived_insights: { promotion_status: "not_available", formal_integration_status: "not_attached", derived_insights: [] },
  governance: null,
  loaded: false,
  // Dynamic adapter output is always an in-memory, read-only preview. Keep a
  // copy of the approved payload so the UI can explicitly roll it back.
  preview_backup: null,
  preview_active: false,
};

function normalizeDynamicRatioMetric(metric) {
  if (metric?.value === null || metric?.value === undefined || metric?.value === "") return { ok: false, reason: "value_missing" };
  const raw = Number(metric?.value);
  if (!Number.isFinite(raw)) return { ok: false, reason: "value_not_numeric" };
  const mode = String(metric?.value_mode || metric?.value_type || "").toLowerCase();
  const isRatio = ["ratio", "ratio_0_to_1", "percentage_0_to_1", "fraction", "0_to_1"].includes(mode);
  const isPercent = ["percent", "percentage", "percentage_0_to_100", "percent_0_to_100", "0_to_100"].includes(mode);
  if (!isRatio && !isPercent) return { ok: false, reason: "value_mode_required" };
  if (isRatio && (raw < 0 || raw > 1)) return { ok: false, reason: "ratio_out_of_range" };
  if (isPercent && (raw < 0 || raw > 100)) return { ok: false, reason: "percentage_out_of_range" };
  return { ok: true, value: isPercent ? raw / 100 : raw, value_mode: isPercent ? "percentage_0_to_100" : "ratio_0_to_1" };
}

async function sha256Response(response) {
  if (!response?.clone || !globalThis.crypto?.subtle) return null;
  const digest = await globalThis.crypto.subtle.digest("SHA-256", await response.clone().arrayBuffer());
  return Array.from(new Uint8Array(digest)).map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function validatePeerOverlayPayload(peerPayload, manifest, overview, event) {
  const overlay = peerPayload?.peer_overlay;
  const reasons = [];
  if (!overlay || overlay.target !== "adapter-test-only" || overlay.status !== "active" || overlay.read_only !== true) {
    reasons.push("overlay_not_readonly_adapter_test");
  }
  const expectedEventId = event?.adapter_event_id || event?.event_id;
  if (peerPayload?.event?.event_id && expectedEventId && peerPayload.event.event_id !== expectedEventId) {
    reasons.push("event_id_mismatch");
  }
  if (overview?.dataset_id !== "OMP_LOCAL_ADAPTER_TEST") {
    reasons.push("dataset_id_not_adapter_test");
  }
  if (peerPayload?.dataset_id && overview?.dataset_id && peerPayload.dataset_id !== overview.dataset_id) {
    reasons.push("dataset_id_mismatch");
  }
  const sourceSha = overlay?.source_payload_sha256;
  const manifestSourceSha = manifest?.source_payload_sha256 || peerPayload?.source_payload_sha256;
  if (!/^[a-f0-9]{64}$/i.test(sourceSha || "")) reasons.push("source_sha_invalid");
  if (!manifestSourceSha) reasons.push("manifest_source_sha_missing");
  else if (sourceSha !== manifestSourceSha) reasons.push("source_sha_mismatch");
  if (!manifest || manifest.mode !== "adapter-test" || manifest.source_write_performed !== false || manifest.actor_can_execute !== false) {
    reasons.push("manifest_boundary_failed");
  }
  if (manifest?.payload_hashes_valid === false) reasons.push("manifest_payload_hash_mismatch");
  if (manifest?.payload_hashes_valid == null) reasons.push("manifest_payload_hash_unverified");
  return { valid: reasons.length === 0, reasons, expected_event_id: expectedEventId, expected_dataset_id: overview?.dataset_id || null };
}

// 加载两个数据载荷
async function loadBifrostData() {
  const adapterTest = new URLSearchParams(window.location.search).get("mode") === "adapter-test";
  const overviewFile = adapterTest ? "artifacts/BIFROST_OVERVIEW_PAYLOAD_adapter-test.json" : "artifacts/BIFROST_OVERVIEW_PAYLOAD_v2.1.json";
  const eventFile = adapterTest ? "artifacts/BIFROST_EVENT_PAYLOAD_adapter-test.json" : "artifacts/BIFROST_EVENT_PAYLOAD_v1.4.json";
  const [overviewRes, eventRes] = await Promise.all([
    fetch(overviewFile),
    fetch(eventFile),
  ]);
  BIFROST_DATA.overview = await overviewRes.json();
  BIFROST_DATA.event = await eventRes.json();
  const formal = BIFROST_DATA.event?.formal_derived_insights;
  if (["validated", "approved"].includes(formal?.promotion_status) && formal?.formal_integration_status === "attached_additive") {
    BIFROST_DATA.formal_derived_insights = formal;
  } else {
    BIFROST_DATA.formal_derived_insights = { promotion_status: formal?.promotion_status || "not_available", formal_integration_status: "not_attached", derived_insights: [] };
  }
  BIFROST_DATA.governance = BIFROST_DATA.overview?.data_quality_summary || null;
  if (adapterTest) {
    try {
      const peerRes = await fetch("artifacts/BIFROST_PEER_OVERLAY_adapter-test.json");
      const manifestRes = await fetch("artifacts/BIFROST_ADAPTER_TEST_MANIFEST.json");
      if (peerRes.ok && manifestRes.ok) {
        const peerPayload = await peerRes.json();
        const manifest = await manifestRes.json();
        const [overviewHashRes, eventHashRes] = await Promise.all([fetch(overviewFile), fetch(eventFile)]);
        const [overviewHash, eventHash] = await Promise.all([sha256Response(overviewHashRes), sha256Response(eventHashRes)]);
        manifest.payload_hashes_valid = Boolean(
          overviewHash && eventHash &&
          overviewHash === manifest.overview_test_sha256 &&
          eventHash === manifest.event_test_sha256
        );
        const validation = validatePeerOverlayPayload(peerPayload, manifest, BIFROST_DATA.overview, BIFROST_DATA.event);
        BIFROST_DATA.peer_overlay_error = validation.valid ? null : validation.reasons.join(", ");
        BIFROST_DATA.peer_overlay = validation.valid ? (peerPayload.peer_overlay || null) : null;
        BIFROST_DATA.peer_enhancements = validation.valid ? (peerPayload.peer_skill_outputs || peerPayload.analysis_enhancements || []) : [];
        BIFROST_DATA.peer_role_projections = validation.valid ? (peerPayload.role_projections || {}) : {};
      } else {
        BIFROST_DATA.peer_overlay = null;
        BIFROST_DATA.peer_enhancements = [];
        BIFROST_DATA.peer_role_projections = {};
        BIFROST_DATA.peer_overlay_error = "overlay_or_manifest_unavailable";
      }
    } catch (error) {
      BIFROST_DATA.peer_overlay = null;
      BIFROST_DATA.peer_enhancements = [];
      BIFROST_DATA.peer_role_projections = {};
      BIFROST_DATA.peer_overlay_error = error?.message || "overlay_validation_failed";
    }
  }
  BIFROST_DATA.runtime_mode = adapterTest ? "adapter-test" : "approved-payload";
  BIFROST_DATA.loaded = true;
  return BIFROST_DATA;
}

// 将动态编译器的最小 Payload 投影为看板可消费的安全视图。
// 仅投影已经计算出的指标，不补造趋势、产线或事件事实。
function projectDynamicPayloads(payloads) {
  const sourceOverview = payloads?.overview || {};
  const sourceEvent = payloads?.event || {};
  const coverage = sourceOverview.view_coverage || {};
  const sourceSnapshots = Array.isArray(sourceOverview.view_snapshots)
    ? sourceOverview.view_snapshots
    : [];
  const firstSnapshot = sourceSnapshots[0];
  const firstWindowId = firstSnapshot?.time_window?.window_id
    || coverage.time_windows?.[0]
    || "full_history";
  const firstWindowLabel = firstSnapshot?.time_window?.label
    || coverage.window_labels?.[firstWindowId]
    || "全历史";
  const oee = sourceOverview.metrics?.oee;
  const normalizedOee = normalizeDynamicRatioMetric(oee);
  const kpis = normalizedOee.ok ? [{
    metric_code: "OEE",
    label: "综合设备效率（OEE）",
    value: normalizedOee.value,
    value_type: "ratio",
    value_mode: normalizedOee.value_mode,
    display_format: "0.0%",
    status: "available",
  }] : [];
  const view = {
    view_key: `factory|ALL_LINES|${firstWindowId}`,
    role: "factory",
    scope: "ALL_LINES",
    time_window: { window_id: firstWindowId, label: firstWindowLabel },
    title: "动态适配数据",
    kpis,
    alerts: [],
    tasks: [],
    decisions_required: [],
    charts: [],
    tables: [],
  };
  const overview = {
    ...sourceOverview,
    metrics: {
      ...(sourceOverview.metrics || {}),
      oee: normalizedOee.ok
        ? { ...(sourceOverview.metrics?.oee || {}), value: normalizedOee.value, value_mode: normalizedOee.value_mode, value_type: "ratio" }
        : null,
    },
    payload_version: sourceOverview.contract_version || "BIFROST_OVERVIEW_DYNAMIC_v1",
    dataset_id: sourceOverview.source_profile?.file_name || "DYNAMIC_SOURCE",
    data_nature: "动态适配数据（只读）",
    view_snapshots: sourceSnapshots.length ? sourceSnapshots : [view],
    view_coverage: sourceOverview.view_coverage || {
      roles: ["factory"],
      lines: [],
      time_windows: [firstWindowId],
      window_labels: { [firstWindowId]: firstWindowLabel },
      source_dimensions_are_physical: true,
    },
    event_summaries: [],
    pending_confirmations: [],
    data_source_registry: [{
      dataset_id: sourceOverview.source_profile?.file_name || "DYNAMIC_SOURCE",
      label: "当前导入数据",
      status: "active",
      data_nature: "动态适配数据（只读）",
      note: "由统一适配链生成，原始文件未被修改",
    }],
    source_status: {
      connection_mode: {
        data_mode: "dynamic",
        aily_mode: "disabled",
        writeback_mode: "readonly",
        bitable_status: "not_connected",
      },
    },
    adaptation_warnings: normalizedOee.ok ? [] : ["OEE value_mode/value range rejected; metric withheld"],
    data_quality_summary: sourceOverview.data_quality_summary || null,
  };
  const event = {
    ...sourceEvent,
    event_id: sourceEvent.event_id || "DYNAMIC-EVENT-0001",
    event_status: sourceEvent.status || "待确认",
    roles: sourceEvent.roles || [],
  };
  return { overview, event };
}

function buildValidatedDerivedInsights(peerAnalysis, eventId, datasetId) {
  const results = Array.isArray(peerAnalysis?.peer_results) ? peerAnalysis.peer_results : [];
  const eligible = results.filter((item) =>
    item && item.status === "available" &&
    item.evidence_gate?.status === "passed" &&
    Array.isArray(item.evidence_refs) && item.evidence_refs.length > 0 &&
    item.source_task_status !== "partial" && item.source_task_status !== "blocked" &&
    item.source_task_status !== "failed" &&
    item.source_task_status !== "needs_confirmation" &&
    (item.event_id == null || item.event_id === eventId)
  );
  return {
    promotion_status: eligible.length ? "validated" : "not_available",
    formal_integration_status: eligible.length ? "attached_additive" : "not_attached",
    presentation_mode: eligible.length ? "first_class_business" : "none",
    authority: "bifrost_derived",
    source: "validated_dynamic_analysis",
    dataset_id: datasetId || null,
    event_id: eventId || null,
    derived_insights: eligible.map((item) => ({
      insight_id: `DERIVED-${eventId || "DYNAMIC"}-${item.skill_id}`,
      skill_id: item.skill_id,
      status: "validated",
      presentation_mode: "first_class_business",
      audience_roles: item.audience_roles || [],
      title: item.title_zh || item.display_descriptor?.title_zh || item.skill_id,
      business_summary: item.business_summary || item.conclusion || item.summary || null,
      conclusion: item.conclusion || item.summary || null,
      metrics: item.metrics || [],
      evidence_refs: item.evidence_refs,
      evidence_gate: item.evidence_gate,
      source_task_status: item.source_task_status || "ready",
      does_not_replace_authoritative_metrics: true,
      requires_human_confirmation: false,
    })),
  };
}

function applyDynamicPayloads(payloads, peerAnalysis = null) {
  if (!payloads || !payloads.overview || !payloads.event) {
    throw new Error("动态适配载荷不完整，无法应用只读预览");
  }
  if (!BIFROST_DATA.preview_backup) {
    BIFROST_DATA.preview_backup = {
      overview: BIFROST_DATA.overview,
      event: BIFROST_DATA.event,
      runtime_mode: BIFROST_DATA.runtime_mode,
    };
  }
  const projected = projectDynamicPayloads(payloads);
  const supplied = payloads.event?.formal_derived_insights;
  const suppliedMatches = supplied &&
    ["validated", "approved"].includes(supplied.promotion_status) &&
    supplied.formal_integration_status === "attached_additive" &&
    (!supplied.event_id || supplied.event_id === projected.event?.event_id) &&
    (!supplied.dataset_id || supplied.dataset_id === projected.overview?.dataset_id || supplied.dataset_id === projected.overview?.source_profile?.source_sha256);
  const derived = suppliedMatches
    ? supplied
    : buildValidatedDerivedInsights(
      peerAnalysis,
      projected.event?.event_id,
      projected.overview?.dataset_id || projected.overview?.source_profile?.source_sha256,
    );
  projected.event.formal_derived_insights = derived;
  projected.overview.formal_derived_insights = derived;
  BIFROST_DATA.overview = projected.overview;
  BIFROST_DATA.event = projected.event;
  BIFROST_DATA.formal_derived_insights = derived;
  BIFROST_DATA.governance = projected.overview?.data_quality_summary || null;
  BIFROST_DATA.runtime_mode = "dynamic-adapted";
  BIFROST_DATA.preview_active = true;
  BIFROST_DATA.loaded = true;
  window.dispatchEvent(new CustomEvent("bifrost:data-updated"));
  return projected;
}

function rollbackDynamicPayloads() {
  const backup = BIFROST_DATA.preview_backup;
  if (!backup) return false;
  BIFROST_DATA.overview = backup.overview;
  BIFROST_DATA.event = backup.event;
  BIFROST_DATA.runtime_mode = backup.runtime_mode || "approved-payload";
  BIFROST_DATA.preview_backup = null;
  BIFROST_DATA.preview_active = false;
  window.dispatchEvent(new CustomEvent("bifrost:data-updated"));
  return true;
}

function isDynamicPreviewActive() {
  return BIFROST_DATA.preview_active === true;
}

// ========== Overview 工具函数 ==========

// 查找特定视图快照（按 view_key 精确匹配）
// Business interpretation is derived from the current view only. It never
// overwrites KPI values and keeps source nature and limitations visible.
function buildBusinessViewBrief(view, role = "factory", scope = "ALL_LINES", timeWindow = "") {
  if (!view) return null;
  const kpi = (codes) => (view.kpis || []).find((item) => codes.includes(item.metric_code));
  const oee = kpi(["OEE"]);
  const quality = kpi(["QUALITY", "YIELD"]);
  const source = BIFROST_DATA.overview || {};
  const labels = { appearance: "外观不良", appearance_defect: "外观不良", size: "尺寸超差", size_exceed: "尺寸超差", function: "功能失效", functional: "功能失效", electrical: "电气不良", other: "其他不良" };
  const defects = [];
  (view.tables || []).forEach((table) => {
    const id = String(table.table_id || table.id || "").toLowerCase();
    if (!id.includes("defect")) return;
    (table.rows || []).forEach((row) => {
      const value = Number(row.count ?? row.quantity ?? row.value);
      if (!Number.isFinite(value)) return;
      const raw = String(row.type || row.defect_type || row.category || row.label || "未标注类别");
      const key = raw.toLowerCase().replaceAll(" ", "_").replaceAll("-", "_");
      defects.push({ label: labels[key] || raw, count: value, evidence_refs: row.evidence_refs || [] });
    });
  });
  const defectTotal = defects.reduce((sum, item) => sum + item.count, 0);
  const ranked = defects.sort((a, b) => b.count - a.count).slice(0, 5).map((item) => ({ ...item, share: defectTotal ? item.count / defectTotal : null }));
  const evidenceCount = new Set([...(view.evidence_refs || []), ...ranked.flatMap((item) => item.evidence_refs || [])]).size;
  const sourceNature = source.data_nature || source.data_source_registry?.[0]?.data_nature || "来源性质未提供";
  const reliability = evidenceCount ? "已核验范围" : "已生成快照，行级证据未随视图提供";
  const finding = [];
  if (oee && Number.isFinite(Number(oee.value))) {
    const value = Number(oee.value);
    const target = Number.isFinite(Number(oee.target)) ? Number(oee.target) : null;
    finding.push({
      title: "当前生产状态怎么理解",
      text: `当前综合设备效率（OEE）为 ${(value * 100).toFixed(1)}%${target !== null && value < target ? `，低于目标 ${((target - value) * 100).toFixed(1)} 个百分点` : ""}。OEE 反映设备开动、运行速度和产出质量的综合表现，下一步应结合停机、不良和换产记录定位影响环节。`,
      action: "优先按产线→班次→停机/不良记录下钻，确认损失发生在哪个环节。",
    });
  }
  if (ranked.length) {
    const top = ranked[0];
    finding.push({
      title: "不良类型代表什么",
      text: `当前范围共统计 ${defectTotal.toLocaleString("zh-CN")} 件不良，最多的是“${top.label}”（${top.count.toLocaleString("zh-CN")} 件，占 ${(top.share * 100).toFixed(1)}%）。不良类型是检测结果分类，不等于已经确认的根因；累计占比达到100%是因为所有分类都被纳入统计。`,
      action: "点击类别继续查看班次、工单、工序和证据记录，再决定改善动作。",
      defects: ranked,
    });
  }
  return { role, scope, timeWindow, sourceNature, reliability, evidenceCount, findings: finding, limitations: ["当前结论只解释已提供的统计事实", "没有批次/工序证据时不自动归因"], metrics: { oee, quality }, defects: ranked };
}

function getViewSnapshot(viewKey) {
  if (!BIFROST_DATA.overview) return null;
  return (
    BIFROST_DATA.overview.view_snapshots.find((v) => v.view_key === viewKey) ||
    null
  );
}

// 按角色 + 范围 + 时间窗构造 view_key 并查找
function findViewSnapshot(role, scope, timeWindow) {
  // scope 可能是 ALL_LINES 或具体 line_id
  const viewKey = `${role}|${scope}|${timeWindow}`;
  return getViewSnapshot(viewKey);
}

// 获取某角色的所有视图（按时间窗排序）
function getRoleViews(role) {
  if (!BIFROST_DATA.overview) return [];
  return BIFROST_DATA.overview.view_snapshots.filter((v) => v.role === role);
}

// 获取角色在某时间窗下所有产线视图（用于对比）
function getRoleLineViews(role, timeWindow) {
  if (!BIFROST_DATA.overview) return [];
  return BIFROST_DATA.overview.view_snapshots.filter(
    (v) =>
      v.role === role &&
      v.time_window &&
      v.time_window.window_id === timeWindow &&
      v.scope &&
      v.scope.mode === "single_line"
  );
}

// 提取视图 headline 中的核心数值（仅展示用，不改源数据）
function parseHeadline(headline) {
  return headline || "";
}

// ===== KPI 展示格式化（P0-1 修复） =====
// display_format 只是格式模板，永远不直接显示给用户。
// - ratio: value × 100，保留 1 位小数 + %
// - integer / count: 中文千分位，不带小数
// - decimal / number: 按模板推断 0 或 1 位小数
// - 空值：显示「暂无数据」
function formatKpiValue(kpi) {
  if (!kpi || kpi.value === undefined || kpi.value === null || kpi.value === "") {
    return "暂无数据";
  }
  const v = kpi.value;
  const vt = kpi.value_type || inferKpiValueType(kpi.metric_code, v, kpi.display_format);
  if (typeof v !== "number") {
    const num = parseFloat(v);
    if (isNaN(num)) return v || "暂无数据";
    return _formatByType(num, vt, kpi.display_format);
  }
  return _formatByType(v, vt, kpi.display_format);
}

function _formatByType(val, valueType, displayFormat) {
  // 比例型：value × 100 保留 1 位小数加 %
  if (valueType === "ratio" || valueType === "percentage_0_to_1") {
    return (val * 100).toFixed(1) + "%";
  }
  if (valueType === "percentage_0_to_100") {
    return val.toFixed(1) + "%";
  }
  // 整数型 / 计数型：千分位
  if (valueType === "integer" || valueType === "count") {
    return Math.round(val).toLocaleString("zh-CN");
  }
  // 小数 / 数字 / 时长：按模板推断
  if (valueType === "decimal" || valueType === "number" || valueType === "duration_min") {
    // 模板里 0.0 → 1 位；0 → 0 位
    if (displayFormat && displayFormat.includes("0.0")) {
      return val.toFixed(1);
    }
    if (displayFormat === "0" || displayFormat === "#,##0") {
      return Math.round(val).toLocaleString("zh-CN");
    }
    return val.toFixed(1);
  }
  // 默认：有小数位就 1 位，否则千分位
  if (Math.round(val) === val) {
    return val.toLocaleString("zh-CN");
  }
  return val.toFixed(1);
}

// 目标值使用相同口径
function formatKpiTarget(kpi) {
  if (!kpi || kpi.target === undefined || kpi.target === null) return null;
  return _formatByType(kpi.target, kpi.value_type || inferKpiValueType(kpi.metric_code, kpi.target, kpi.display_format), kpi.display_format);
}

// 目标差值（百分点 / 绝对值）
function getKpiGapPct(kpi) {
  if (!kpi || kpi.value === undefined || kpi.target === undefined) return null;
  const vt = kpi.value_type;
  if (vt === "ratio" || vt === "percentage_0_to_1") {
    return ((kpi.value - kpi.target) * 100).toFixed(1);
  }
  if (vt === "percentage_0_to_100") {
    return (kpi.value - kpi.target).toFixed(1);
  }
  return null;
}

// 计算 KPI 与目标的差距（用于状态着色）
function getKpiStatus(kpi) {
  if (!kpi || kpi.target === undefined || kpi.target === null) return "default";
  const val = typeof kpi.value === "number" ? kpi.value : parseFloat(kpi.value);
  const tgt =
    typeof kpi.target === "number" ? kpi.target : parseFloat(kpi.target);
  if (isNaN(val) || isNaN(tgt)) return "default";

  // 越高越好的指标（如良率、OEE、开动率）
  const higherIsBetter = ["QUALITY", "AVAILABILITY", "PERFORMANCE", "OEE"];
  if (higherIsBetter.includes(kpi.metric_code)) {
    if (val >= tgt) return "success";
    if (val >= tgt * 0.9) return "warning";
    return "danger";
  }
  // 越低越好的指标
  const lowerIsBetter = ["DOWNTIME", "MTTR", "DEFECT_RATE"];
  if (lowerIsBetter.includes(kpi.metric_code)) {
    if (val <= tgt) return "success";
    if (val <= tgt * 1.1) return "warning";
    return "danger";
  }
  return "default";
}

// 获取数据治理摘要
function getDataQuality() {
  if (!BIFROST_DATA.overview) return null;
  return BIFROST_DATA.governance || BIFROST_DATA.overview.data_quality_summary;
}

function inferKpiValueType(metricCode, value, displayFormat) {
  if (displayFormat && String(displayFormat).includes("%")) {
    return Number(value) <= 1 ? "percentage_0_to_1" : "percentage_0_to_100";
  }
  if (["OEE", "QUALITY", "YIELD", "AVAILABILITY", "PERFORMANCE", "DEFECT_RATE"].includes(metricCode)) {
    return Number(value) <= 1 ? "percentage_0_to_1" : "percentage_0_to_100";
  }
  if (["TOTAL_OUTPUT", "MATERIAL_GAP_COUNT", "MATERIAL_GAP_QTY", "FREEZE_COUNT", "UPH"].includes(metricCode)) return "count";
  if (["DOWNTIME_MIN", "CHANGEOVER_OVERTIME"].includes(metricCode)) return "duration_min";
  return undefined;
}

// 获取数据源状态
function getSourceStatus() {
  if (!BIFROST_DATA.overview) return null;
  return BIFROST_DATA.overview.source_status;
}

// 获取事件摘要列表
function getEventSummaries() {
  if (!BIFROST_DATA.overview) return [];
  return BIFROST_DATA.overview.event_summaries || [];
}

// 获取待确认事项
function getPendingConfirmations() {
  if (!BIFROST_DATA.overview) return [];
  return BIFROST_DATA.overview.pending_confirmations || [];
}

// 获取数据源注册
function getDataSourceRegistry() {
  if (!BIFROST_DATA.overview) return [];
  return BIFROST_DATA.overview.data_source_registry || [];
}

// ========== Event 工具函数 ==========

// 获取黄金事件详情
function getGoldenEvent() {
  return BIFROST_DATA.event || null;
}

// 获取事件的某角色切片
function getEventRoleSlice(role) {
  const evt = getGoldenEvent();
  if (!evt || !evt.roles) return null;
  return evt.roles.find((r) => r.role === role) || null;
}

// 获取验证契约
function getValidationContract() {
  const evt = getGoldenEvent();
  if (!evt) return null;
  return evt.validation_contract || null;
}

// 获取验证结果
function getValidationResults() {
  const evt = getGoldenEvent();
  if (!evt) return null;
  return evt.validation_results || null;
}

// 获取控制表引用
function getControlTableRefs() {
  const evt = getGoldenEvent();
  if (!evt) return null;
  return evt.control_table_refs || null;
}

// 获取物化结果
function getMaterialization() {
  const evt = getGoldenEvent();
  if (!evt) return null;
  return evt.materialization || null;
}

// ========== 真实图表 ECharts option 构建 ==========
// 直接消费 payload 中 charts/tables，不做任何模拟或补值

// 产线编号是稳定维度；团队模拟数据中的“设备瓶颈线/质量波动线”等只是情景描述，
// 不能把情景名称当成产线名称展示。
function displayLineLabel(lineId, rawLabel) {
  const datasetId = BIFROST_DATA.overview?.dataset_id || "";
  // LINE-Sxx is the stable physical identity in the team-simulation package;
  // its descriptive labels (stable/equipment/quality) are scenario tags, not
  // production-line names. Never let those tags replace the line identity.
  if (datasetId === "TEAM_ENGINEERED_SIMULATION" || /^LINE-S\d+$/i.test(String(lineId || ""))) {
    return t_scope(lineId);
  }
  return rawLabel || t_scope(lineId) || lineId;
}

// 趋势对比图（trend_comparison / oee_trend / quality_trend / perf_trend）
function buildTrendOption(chartData, selectedLines) {
  if (!chartData || typeof chartData !== "object") return null;
  const lineKeys = Object.keys(chartData);
  if (lineKeys.length === 0) return null;

  const filtered = selectedLines && selectedLines.length > 0
    ? lineKeys.filter((k) => selectedLines.includes(k))
    : lineKeys;
  if (filtered.length === 0) return null;

  // 用第一条线的 dates 作为 x 轴
  const first = chartData[filtered[0]];
  const dates = first.dates || [];

  const colorPalette = ["#2d5b93", "#d89000", "#2e7d52", "#c0392b", "#8e44ad"];

  const series = filtered.map((key, i) => {
    const line = chartData[key];
    const values = (line.oee_values || line.values || []).map((v) =>
      typeof v === "number" && v <= 1 ? +(v * 100).toFixed(1) : v
    );
    return {
      name: key === "__single_line__" ? (line.label || "当前产线") : displayLineLabel(key, line.label),
      type: "line",
      data: values,
      smooth: true,
      symbol: "circle",
      symbolSize: 5,
      lineStyle: { color: colorPalette[i % colorPalette.length], width: 2 },
      itemStyle: { color: colorPalette[i % colorPalette.length] },
    };
  });

  return {
    grid: { top: 30, right: 16, bottom: 28, left: 44 },
    tooltip: { trigger: "axis", valueFormatter: (v) => v + "%" },
    legend: {
      right: 0, top: 0,
      itemWidth: 10, itemHeight: 10,
      textStyle: { fontSize: 11, color: "#6b7684" },
    },
    xAxis: {
      type: "category",
      data: dates,
      axisLabel: {
        fontSize: 11,
        color: "#8a95a6",
        interval: dates.length > 8 ? Math.ceil(dates.length / 8) - 1 : 0,
        rotate: dates.length > 14 ? 30 : 0,
        hideOverlap: true,
        formatter: (value) => String(value).length >= 10 ? String(value).slice(5) : value,
      },
      axisLine: { lineStyle: { color: "#e5e9ef" } },
    },
    yAxis: {
      type: "value",
      axisLabel: { fontSize: 11, color: "#8a95a6", formatter: "{value}%" },
      splitLine: { lineStyle: { color: "#eef4fb" } },
    },
    series,
  };
}

// 排行柱状图（ranking_bar）
function buildRankingOption(rankingData) {
  if (!rankingData || !Array.isArray(rankingData) || rankingData.length === 0) return null;
  const sorted = [...rankingData].sort((a, b) => (b.oee || 0) - (a.oee || 0));
  return {
    grid: { top: 10, right: 24, bottom: 28, left: 90 },
    tooltip: {
      trigger: "axis",
      valueFormatter: (v) => (typeof v === "number" && v <= 1 ? (v * 100).toFixed(1) + "%" : v),
    },
    xAxis: {
      type: "value",
      max: 100,
      axisLabel: { fontSize: 11, color: "#8a95a6", formatter: "{value}%" },
      splitLine: { lineStyle: { color: "#eef4fb" } },
    },
    yAxis: {
      type: "category",
      data: sorted.map((r) => displayLineLabel(r.line_id, r.label)),
      axisLabel: { fontSize: 12, color: "#4a5568" },
      axisLine: { lineStyle: { color: "#e5e9ef" } },
    },
    series: [{
      type: "bar",
      data: sorted.map((r) => (typeof r.oee === "number" && r.oee <= 1 ? +(r.oee * 100).toFixed(1) : r.oee || 0)),
      barWidth: 20,
      itemStyle: {
        color: {
          type: "linear", x: 0, y: 0, x2: 1, y2: 0,
          colorStops: [
            { offset: 0, color: "#2d5b93" },
            { offset: 1, color: "#3a73b8" },
          ],
        },
        borderRadius: [0, 3, 3, 0],
      },
      label: {
        show: true,
        position: "right",
        fontSize: 11,
        color: "#4a5568",
        formatter: "{c}%",
      },
    }],
  };
}

// 从 defect_table 构建 Pareto 图
const BUSINESS_REASON_LABELS = {
  HANGOVERS: "换产与切换",
  SETUPS: "换产与调试",
  "SETUPS-CHANGEOVERS": "换产与调试",
  MATERIALS: "物料等待",
  FAILURE: "设备故障",
  OPERATIONAL: "操作与组织",
  OTHER: "其他停机",
  OTHER_CALIBRATION: "校准与调试",
};

const BUSINESS_DEFECT_LABELS = {
  appearance_defect: "外观不良",
  functional_failure: "功能失效",
  electrical_defect: "电气功能问题",
  dimensional_deviation: "尺寸超差",
  assembly_issue: "装配问题",
  packaging_defect: "包装缺陷",
  other_defect: "其他不良",
};

function displayBusinessReason(value) {
  const key = String(value || "").trim();
  return BUSINESS_REASON_LABELS[key] || BUSINESS_DEFECT_LABELS[key] || key || "未分类";
}

function buildDefectParetoOption(rows) {
  if (!rows || !Array.isArray(rows) || rows.length === 0) return null;
  const sorted = [...rows].sort((a, b) => (b.count || 0) - (a.count || 0));
  const total = sorted.reduce((s, r) => s + (r.count || 0), 0);
  if (total === 0) return null;
  let cum = 0;
  const cumPct = sorted.map((r) => {
    cum += r.count || 0;
    return +(cum / total * 100).toFixed(1);
  });

  return {
    grid: { top: 20, right: 50, bottom: 40, left: 50 },
    tooltip: { trigger: "axis" },
    xAxis: {
      type: "category",
      data: sorted.map((r) => displayBusinessReason(r.label || r.type || r.defect_type)),
      axisLabel: { fontSize: 11, color: "#6b7684" },
      axisLine: { lineStyle: { color: "#e5e9ef" } },
    },
    yAxis: [
      {
        type: "value",
        axisLabel: { fontSize: 11, color: "#8a95a6" },
        splitLine: { lineStyle: { color: "#eef4fb" } },
      },
      {
        type: "value",
        max: 100,
        axisLabel: { fontSize: 11, color: "#8a95a6", formatter: "{value}%" },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: "缺陷数",
        type: "bar",
        data: sorted.map((r) => r.count || 0),
        barWidth: 28,
        itemStyle: { color: "#c0392b" },
      },
      {
        name: "累计占比",
        type: "line",
        yAxisIndex: 1,
        data: cumPct,
        smooth: true,
        symbol: "circle",
        symbolSize: 5,
        lineStyle: { color: "#d89000", width: 2 },
        itemStyle: { color: "#d89000" },
      },
    ],
  };
}

// 停机分布柱状图
function buildDowntimeOption(rows) {
  if (!rows || !Array.isArray(rows) || rows.length === 0) return null;
  const sorted = [...rows].sort((a, b) => (b.minutes || 0) - (a.minutes || 0));
  return {
    grid: { top: 10, right: 24, bottom: 28, left: 90 },
    tooltip: { trigger: "axis", valueFormatter: (v) => v + " 分钟" },
    xAxis: {
      type: "value",
      axisLabel: { fontSize: 11, color: "#8a95a6" },
      splitLine: { lineStyle: { color: "#eef4fb" } },
    },
    yAxis: {
      type: "category",
      data: sorted.map((r) => displayBusinessReason(r.label || r.group || r.reason_code)),
      axisLabel: { fontSize: 12, color: "#4a5568" },
      axisLine: { lineStyle: { color: "#e5e9ef" } },
    },
    series: [{
      type: "bar",
      data: sorted.map((r) => r.minutes || 0),
      barWidth: 18,
      itemStyle: {
        color: {
          type: "linear", x: 0, y: 0, x2: 1, y2: 0,
          colorStops: [
            { offset: 0, color: "#2d5b93" },
            { offset: 1, color: "#3a73b8" },
          ],
        },
        borderRadius: [0, 3, 3, 0],
      },
      label: {
        show: true,
        position: "right",
        fontSize: 11,
        color: "#4a5568",
        formatter: "{c} min",
      },
    }],
  };
}

// 从视图中按 chart_id 查找
function getChartById(view, chartId) {
  if (!view || !view.charts) return null;
  return view.charts.find((c) => c.chart_id === chartId) || null;
}

// 从视图中按 table_id 查找
function getTableById(view, tableId) {
  if (!view || !view.tables) return null;
  return view.tables.find((t) => t.table_id === tableId) || null;
}

// 获取产线标签
function getLineLabel(lineId, view) {
  // 优先从 ranking_bar 数据中取 label
  const ranking = getChartById(view, "ranking_bar");
  if (ranking && Array.isArray(ranking.data)) {
    const found = ranking.data.find((r) => r.line_id === lineId);
    if (found && found.label) return displayLineLabel(lineId, found.label);
  }
  // 从 line_kpi_table 取
  const table = getTableById(view, "line_kpi_table");
  if (table && Array.isArray(table.rows)) {
    const found = table.rows.find((r) => r.line_id === lineId);
    if (found && found.line_label) return displayLineLabel(lineId, found.line_label);
  }
  return displayLineLabel(lineId, null);
}

// ========== 事件事实只读 helper（P0-2 修复）==========
// 从 Event v1.4 载荷统一提取业务事实，页面不得再出现硬编码字面量
function getEventFacts() {
  const evt = BIFROST_DATA.event;
  if (!evt || !evt.roles) return null;

  const roles = {};
  evt.roles.forEach((r) => { roles[r.role] = r; });

  // 从 equipment 角色 KPI 提取停机事实
  const eqKpis = roles.equipment?.kpis || [];
  const downtimeCount = eqKpis.find((k) => k.metric_code === "DOWNTIME_EVENT_COUNT")?.value ?? null;
  const downtimeTotalMin = eqKpis.find((k) => k.metric_code === "DOWNTIME_TOTAL_MINUTES")?.value ?? null;
  const unplannedDowntimeMin = eqKpis.find((k) => k.metric_code === "UNPLANNED_DOWNTIME_MINUTES")?.value ?? null;

  // 从 supply 角色 KPI 提取物料/冻结事实
  const supKpis = roles.supply?.kpis || [];
  const materialShortage = supKpis.find((k) => k.metric_code === "MATERIAL_SHORTAGE")?.value ?? null;
  const materialFreeze = supKpis.find((k) => k.metric_code === "MATERIAL_FREEZE")?.value ?? null;

  // 从 supply 角色告警提取冻结单号与状态
  const freezeAlert = (roles.supply?.alerts || []).find((a) => a.alert_id === "ALERT-SUPPLY-002");
  const freezeId = (() => {
    const refs = freezeAlert?.evidence_refs || [];
    for (const r of refs) {
      if (r.record_id && r.semantic_table === "quality_freeze") return r.record_id;
    }
    return null;
  })();
  const freezeStatus = "待复检"; // 与 alert 文案一致

  // OEE 差距（使用 Math.abs，便于业务可读表达）
  const mat = evt.materialization || {};
  const oeeGapPct = mat.oee_gap != null
    ? +(Math.abs(mat.oee_gap) * 100).toFixed(2)
    : null;

  return {
    // 停机
    downtime_count: downtimeCount,
    downtime_total_minutes: downtimeTotalMin,
    unplanned_downtime_minutes: unplannedDowntimeMin,
    // 物料与冻结
    material_shortage: materialShortage,
    material_freeze_qty: materialFreeze,
    freeze_id: freezeId,
    freeze_status: freezeStatus,
    // OEE 差距（正值，便于"低于目标X个百分点"表达）
    oee_gap_pct_abs: oeeGapPct,
  };
}

// ========== 视图统计 ==========

// 统计视图总数（验证100个）
function getViewCount() {
  if (!BIFROST_DATA.overview) return 0;
  return BIFROST_DATA.overview.view_snapshots.length;
}

// 获取所有角色列表
function getAllRoles() {
  return ["factory", "line", "quality", "equipment", "process", "supply"];
}

// 获取所有产线
function getAllLines() {
  const coverageLines = BIFROST_DATA.overview?.view_coverage?.lines;
  if (Array.isArray(coverageLines) && coverageLines.length) {
    return coverageLines.map((line) => typeof line === "string" ? line : line.line_id || line.id).filter(Boolean);
  }
  const dimensionLines = BIFROST_DATA.overview?.dimensions?.lines;
  if (Array.isArray(dimensionLines) && dimensionLines.length) {
    return dimensionLines.map((line) => typeof line === "string" ? line : line.line_id || line.id).filter(Boolean);
  }
  const snapshotLines = (BIFROST_DATA.overview?.view_snapshots || [])
    .flatMap((view) => {
      if (typeof view.scope === "string") return view.scope !== "ALL_LINES" ? [view.scope] : [];
      if (Array.isArray(view.scope?.line_ids)) return view.scope.line_ids;
      return view.scope?.line_id ? [view.scope.line_id] : [];
    })
    .filter(Boolean);
  return [...new Set(snapshotLines)];
}

function getDefaultScopeForRole(role) {
  const roleConfig = (BIFROST_DATA.overview?.dimensions?.roles || []).find((item) => item.role === role);
  if (roleConfig?.default_scope) return roleConfig.default_scope;
  if (role === "factory" || ["quality", "equipment", "process", "supply"].includes(role)) return "ALL_LINES";
  return getAllLines()[0] || "ALL_LINES";
}

function getAllowedLinesForRole(role) {
  const roleConfig = (BIFROST_DATA.overview?.dimensions?.roles || []).find((item) => item.role === role);
  const allowed = Array.isArray(roleConfig?.allowed_line_ids) ? roleConfig.allowed_line_ids : [];
  return allowed.length ? allowed.filter((line) => getAllLines().includes(line)) : getAllLines();
}

function resolveScopeForRole(role, requestedScope) {
  if (role === "factory") return "ALL_LINES";
  const allowed = getAllowedLinesForRole(role);
  if (requestedScope && requestedScope !== "ALL_LINES" && allowed.includes(requestedScope)) return requestedScope;
  const defaultScope = getDefaultScopeForRole(role);
  if (defaultScope === "ALL_LINES" || allowed.includes(defaultScope)) return defaultScope;
  return allowed[0] || "ALL_LINES";
}

// 单产线趋势图使用 {label, dates, oee_values/values} 结构；不能要求
// 它必须先伪装成多产线数据，否则线长页面会因类型不匹配而显示空状态。
function buildSingleTrendOption(chartData, lineId = null) {
  if (!chartData || typeof chartData !== "object") return null;
  const dates = Array.isArray(chartData.dates) ? chartData.dates : [];
  const values = (chartData.oee_values || chartData.values || []).map((value) =>
    typeof value === "number" && value <= 1 ? +(value * 100).toFixed(1) : value
  );
  if (!dates.length || !values.length) return null;
  return buildTrendOption({
    __single_line__: {
      label: lineId ? displayLineLabel(lineId, chartData.label) : "当前产线",
      dates,
      values,
    },
  }, ["__single_line__"]);
}

function getDataSourceLabel(overview = BIFROST_DATA.overview) {
  const source = String(overview?.source_profile?.file_name || overview?.dataset_id || "");
  if (/歌尔|GOERTEK|OFFICIAL/i.test(source)) return "歌尔官方脱敏测试数据";
  if (/BIFROST|SIM|TEAM/i.test(source)) return "团队工程化模拟数据";
  return source ? "当前导入数据" : "本地演示数据";
}

// 获取所有时间窗口ID
function getAllTimeWindows() {
  const coverageWindows = BIFROST_DATA.overview?.view_coverage?.time_windows;
  if (Array.isArray(coverageWindows) && coverageWindows.length) return coverageWindows;
  const snapshotWindows = (BIFROST_DATA.overview?.view_snapshots || [])
    .map((view) => view.time_window?.window_id)
    .filter(Boolean);
  if (snapshotWindows.length) return [...new Set(snapshotWindows)];
  return ["last_7_shifts", "last_30_shifts", "pre_improvement", "post_improvement", "full_history"];
}

// 导出到全局
Object.assign(window, {
  BIFROST_DATA,
  loadBifrostData,
  projectDynamicPayloads,
  applyDynamicPayloads,
  rollbackDynamicPayloads,
  isDynamicPreviewActive,
  getViewSnapshot,
  findViewSnapshot,
  getRoleViews,
  getRoleLineViews,
  parseHeadline,
  formatKpiValue,
  formatKpiTarget,
  getKpiGapPct,
  getKpiStatus,
  buildTrendOption,
  buildRankingOption,
  buildDefectParetoOption,
  buildDowntimeOption,
  getChartById,
  getTableById,
  getLineLabel,
  getDataQuality,
  getSourceStatus,
  getEventSummaries,
  getPendingConfirmations,
  getDataSourceRegistry,
  getDataSourceLabel,
  getGoldenEvent,
  getEventRoleSlice,
  getValidationContract,
  getValidationResults,
  getControlTableRefs,
  getMaterialization,
  getViewCount,
  getEventFacts,
  getAllRoles,
  getAllLines,
  getDefaultScopeForRole,
  getAllowedLinesForRole,
  resolveScopeForRole,
  getAllTimeWindows,
  normalizeDynamicRatioMetric,
  validatePeerOverlayPayload,
});
