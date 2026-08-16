/* ===== BIFROST 通用组件库 v3.2 =====
   所有组件均为中文界面，遵循可读性与响应式标准
*/

const { useState, useEffect, useMemo, useRef, useCallback } = React;

// Keep provider diagnostics out of the conversational UI. The local bridge
// may return stack traces or implementation details when an OMP call fails;
// users need an actionable status, not an internal runtime dump.
function formatAIError(error) {
  const raw = String(error?.message || error || "").trim();
  if (raw.includes("AI_PROVIDER_NOT_CONFIGURED")) return "AI 服务尚未配置，请联系管理员检查本地桥接服务。";
  if (raw.includes("OMP_PROVIDER_FAILED") || raw.includes("AI_PROVIDER_FAILED")) return "AI 服务暂时不可用，请检查本地桥接服务后重试。";
  if (raw.includes("INVALID_EVENT_ID") || raw.includes("INVALID_SCOPE") || raw.includes("INVALID_TIME_WINDOW")) return "当前角色、范围或事件上下文无效，请重新选择后重试。";
  return raw.length > 240 ? `${raw.slice(0, 240)}…` : raw || "AI 服务调用失败，请检查本地桥接服务与网络连接。";
}

// ========== SVG 图标组件 ==========
// 使用内联 SVG，语义贴切、风格统一（20x20 网格）
const Icon = {
  Dashboard: (props) => (
    <svg viewBox="0 0 20 20" fill="none" width="18" height="18" {...props}>
      <rect x="2" y="2" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.5"/>
      <rect x="11" y="2" width="7" height="5" rx="1.5" stroke="currentColor" strokeWidth="1.5"/>
      <rect x="2" y="11" width="5" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.5"/>
      <rect x="9" y="11" width="9" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.5"/>
    </svg>
  ),
  Event: (props) => (
    <svg viewBox="0 0 20 20" fill="none" width="18" height="18" {...props}>
      <circle cx="10" cy="10" r="7.5" stroke="currentColor" strokeWidth="1.5"/>
      <path d="M10 6v4l2.5 2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  ),
  Governance: (props) => (
    <svg viewBox="0 0 20 20" fill="none" width="18" height="18" {...props}>
      <path d="M4 6l6-3 6 3v5c0 3.5-2.8 6.2-6 7-3.2-.8-6-3.5-6-7V6z" stroke="currentColor" strokeWidth="1.5"/>
      <path d="M7 9.5l2 2 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  ),
  Config: (props) => (
    <svg viewBox="0 0 20 20" fill="none" width="18" height="18" {...props}>
      <circle cx="10" cy="10" r="2" stroke="currentColor" strokeWidth="1.5"/>
      <path d="M10 2.5v2M10 15.5v2M2.5 10h2M15.5 10h2M4.6 4.6l1.4 1.4M14 14l1.4 1.4M4.6 15.4L6 14M14 6l1.4-1.4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  ),
  AI: (props) => (
    <svg viewBox="0 0 20 20" fill="none" width="18" height="18" {...props}>
      <path d="M10 2.5l1.8 3.6 4 .6-2.9 2.8.7 4L10 11.5l-3.6 1.9.7-4L4.2 6.7l4-.6L10 2.5z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
      <path d="M6 15.5h8M8 17.5h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  ),
  Search: (props) => (
    <svg viewBox="0 0 20 20" fill="none" width="16" height="16" {...props}>
      <circle cx="8.5" cy="8.5" r="5" stroke="currentColor" strokeWidth="1.5"/>
      <path d="M12.5 12.5L16 16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  ),
  Bell: (props) => (
    <svg viewBox="0 0 20 20" fill="none" width="18" height="18" {...props}>
      <path d="M7 15V10a3 3 0 016 0v5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      <path d="M5 15h10l-1 2H6l-1-2z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
    </svg>
  ),
  Help: (props) => (
    <svg viewBox="0 0 20 20" fill="none" width="16" height="16" {...props}>
      <circle cx="10" cy="10" r="7.5" stroke="currentColor" strokeWidth="1.5"/>
      <path d="M10 6.5c1.2 0 2.2.8 2.2 2 0 1.1-.7 1.7-1.4 2-.7.3-.8.6-.8 1v.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      <circle cx="10" cy="14.5" r="1" fill="currentColor"/>
    </svg>
  ),
  Status: (props) => (
    <svg viewBox="0 0 20 20" fill="none" width="16" height="16" {...props}>
      <circle cx="10" cy="10" r="7.5" stroke="currentColor" strokeWidth="1.5"/>
      <circle cx="10" cy="10" r="3" fill="currentColor"/>
    </svg>
  ),
  Close: (props) => (
    <svg viewBox="0 0 20 20" fill="none" width="16" height="16" {...props}>
      <path d="M5 5l10 10M15 5L5 15" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  ),
  ChevronDown: (props) => (
    <svg viewBox="0 0 20 20" fill="none" width="14" height="14" {...props}>
      <path d="M5 7.5l5 5 5-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  ),
  ChevronRight: (props) => (
    <svg viewBox="0 0 20 20" fill="none" width="14" height="14" {...props}>
      <path d="M7.5 5l5 5-5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  ),
  ArrowUp: (props) => (
    <svg viewBox="0 0 20 20" fill="none" width="12" height="12" {...props}>
      <path d="M10 15V5M6 9l4-4 4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  ),
  ArrowDown: (props) => (
    <svg viewBox="0 0 20 20" fill="none" width="12" height="12" {...props}>
      <path d="M10 5v10M6 11l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  ),
  Check: (props) => (
    <svg viewBox="0 0 20 20" fill="none" width="14" height="14" {...props}>
      <path d="M4 10.5l4 4 8-9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  ),
  Warning: (props) => (
    <svg viewBox="0 0 20 20" fill="none" width="16" height="16" {...props}>
      <path d="M10 2.5l8 14H2l8-14z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
      <path d="M10 8v4M10 14.5v1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  ),
  Error: (props) => (
    <svg viewBox="0 0 20 20" fill="none" width="16" height="16" {...props}>
      <circle cx="10" cy="10" r="7.5" stroke="currentColor" strokeWidth="1.5"/>
      <path d="M7 7l6 6M13 7l-6 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  ),
  Info: (props) => (
    <svg viewBox="0 0 20 20" fill="none" width="16" height="16" {...props}>
      <circle cx="10" cy="10" r="7.5" stroke="currentColor" strokeWidth="1.5"/>
      <path d="M10 9v6M10 7v.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  ),
  Task: (props) => (
    <svg viewBox="0 0 20 20" fill="none" width="16" height="16" {...props}>
      <rect x="3" y="4" width="14" height="12" rx="2" stroke="currentColor" strokeWidth="1.5"/>
      <path d="M6 8h8M6 11h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  ),
  Send: (props) => (
    <svg viewBox="0 0 20 20" fill="none" width="16" height="16" {...props}>
      <path d="M3 10L17 3l-3 14-3-6-11-1z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
    </svg>
  ),
  Factory: (props) => (
    <svg viewBox="0 0 20 20" fill="none" width="16" height="16" {...props}>
      <path d="M3 16V8l4 3V8l4 3V8l6 3v5H3z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
    </svg>
  ),
  Line: (props) => (
    <svg viewBox="0 0 20 20" fill="none" width="16" height="16" {...props}>
      <path d="M2 10h3l2-5 6 10 2-5h3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  ),
  Clock: (props) => (
    <svg viewBox="0 0 20 20" fill="none" width="14" height="14" {...props}>
      <circle cx="10" cy="10" r="7.5" stroke="currentColor" strokeWidth="1.5"/>
      <path d="M10 6v4l3 2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  ),
  Database: (props) => (
    <svg viewBox="0 0 20 20" fill="none" width="16" height="16" {...props}>
      <ellipse cx="10" cy="5" rx="6" ry="2.5" stroke="currentColor" strokeWidth="1.5"/>
      <path d="M4 5v5c0 1.4 2.7 2.5 6 2.5s6-1.1 6-2.5V5" stroke="currentColor" strokeWidth="1.5"/>
      <path d="M4 10v5c0 1.4 2.7 2.5 6 2.5s6-1.1 6-2.5v-5" stroke="currentColor" strokeWidth="1.5"/>
    </svg>
  ),
  Refresh: (props) => (
    <svg viewBox="0 0 20 20" fill="none" width="16" height="16" {...props}>
      <path d="M16 7a6 6 0 00-10-3.5M4 13a6 6 0 0010 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      <path d="M13 3.5l3 3.5h-3M7 16.5l-3-3.5h3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  ),
};

// ========== 状态徽章 ==========
function Badge({ type = "default", children, dot = true }) {
  return (
    <span className={`badge badge-${type}`}>
      {dot && <span className="badge-dot"></span>}
      {children}
    </span>
  );
}

// ========== KPI 卡片 ==========
function KpiCard({ label, value, unit, target, delta, deltaType = "up", status = "default", subLabel, size = "normal" }) {
  const statusColor = {
    success: "var(--c-success)",
    warning: "var(--c-warning)",
    danger: "var(--c-danger)",
    default: "var(--c-gray-900)",
  }[status];

  return (
    <div className="kpi-card">
      <div className="kpi-label">
        {label}
        {unit && <span className="text-muted text-xs">（{unit}）</span>}
      </div>
      <div className={`kpi-value ${size === "sm" ? "sm" : ""}`} style={{ color: statusColor }}>
        {value}
      </div>
      <div className="kpi-sub">
        {target !== undefined && (
          <span>目标 {target}</span>
        )}
        {delta !== undefined && (
          <span className={`kpi-delta ${deltaType}`}>
            {deltaType === "up" ? <Icon.ArrowUp /> : <Icon.ArrowDown />}
            {delta}
          </span>
        )}
        {subLabel && <span>{subLabel}</span>}
      </div>
    </div>
  );
}

// ========== 分段控制器 ==========
function Segmented({ items, value, onChange, size = "md" }) {
  return (
    <div className="segmented">
      {items.map((item) => (
        <button
          key={item.value}
          className={`segmented-item ${value === item.value ? "active" : ""}`}
          onClick={() => onChange && onChange(item.value)}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}

// ========== 卡片 ==========
function Card({ title, extra, children, footer, bodyClassName = "" }) {
  return (
    <div className="card">
      {(title || extra) && (
        <div className="card-header">
          <div className="card-title">{title}</div>
          {extra && <div>{extra}</div>}
        </div>
      )}
      <div className={`card-body ${bodyClassName}`}>{children}</div>
      {footer && <div className="card-footer">{footer}</div>}
    </div>
  );
}

// ========== 折叠区 ==========
function Collapse({ title, defaultOpen = false, children, badge }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <div className="collapse-header" onClick={() => setOpen(!open)}>
        <div className="flex items-center gap-2">
          <Icon.ChevronDown style={{
            transform: open ? "rotate(0deg)" : "rotate(-90deg)",
            transition: "transform 0.2s",
          }} />
          <span>{title}</span>
          {badge}
        </div>
      </div>
      {open && <div className="collapse-body">{children}</div>}
    </div>
  );
}

// ========== ECharts 图表封装 ==========
function EChart({ option, className = "", style = {} }) {
  const chartRef = useRef(null);
  const chartInstRef = useRef(null);

  useEffect(() => {
    if (!chartRef.current || !window.echarts) return;
    chartInstRef.current = window.echarts.init(chartRef.current);
    return () => {
      chartInstRef.current && chartInstRef.current.dispose();
    };
  }, []);

  useEffect(() => {
    if (chartInstRef.current && option) {
      chartInstRef.current.setOption(option, true);
    }
  }, [option]);

  useEffect(() => {
    const handleResize = () => {
      chartInstRef.current && chartInstRef.current.resize();
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  return <div ref={chartRef} className={className} style={{ width: "100%", ...style }} />;
}

// ========== 系统状态面板 ==========
function SystemStatusPanel({ onClose }) {
  const sourceStatus = getSourceStatus();
  const overview = BIFROST_DATA.overview;
  const conn = sourceStatus?.connection_mode || {};

  return (
    <div className="sys-status-panel">
      <div className="sys-status-header">
        <Icon.Status />
        系统状态
      </div>
      <div className="sys-status-list">
        <div className="sys-status-item">
          <div className="sys-status-item-label">数据来源</div>
          <div>
            <div className="sys-status-item-value">
              {conn.data_mode === "snapshot" ? "本地演示数据" : "实时接入"}
            </div>
            <div className="sys-status-item-desc">
              {overview?.dataset_id || ""} · {overview?.data_nature || ""}
            </div>
          </div>
        </div>
        <div className="sys-status-item">
          <div className="sys-status-item-label">AI 连接</div>
          <div>
            <div className="sys-status-item-value">
              <Badge type={conn.aily_mode === "connected" ? "success" : "default"} dot>
                {conn.aily_mode === "disabled" ? "AI 尚未连接" : conn.aily_mode}
              </Badge>
            </div>
            <div className="sys-status-item-desc">接入后可发送自然语言指令</div>
          </div>
        </div>
        <div className="sys-status-item">
          <div className="sys-status-item-label">写回模式</div>
          <div>
            <div className="sys-status-item-value">
              {conn.writeback_mode === "readonly" ? "只读模式" : "可写回"}
            </div>
            <div className="sys-status-item-desc">AI 生成操作需人工确认后执行</div>
          </div>
        </div>
        <div className="sys-status-item">
          <div className="sys-status-item-label">规则版本</div>
          <div>
            <div className="sys-status-item-value">{overview?.rule_version || "-"}</div>
            <div className="sys-status-item-desc">知识版本 {overview?.knowledge_version || "-"}</div>
          </div>
        </div>
        <div className="sys-status-item">
          <div className="sys-status-item-label">数据截至</div>
          <div>
            <div className="sys-status-item-value">{overview?.data_as_of || "-"}</div>
            <div className="sys-status-item-desc">
              生成于 {overview?.payload_generated_at ? overview.payload_generated_at.slice(0, 19).replace("T", " ") : "-"}
            </div>
          </div>
        </div>
        <div className="sys-status-item">
          <div className="sys-status-item-label">多维表格</div>
          <div>
            <div className="sys-status-item-value">
              {conn.bitable_status === "loaded" ? "已连接" : "未连接"}
            </div>
            <div className="sys-status-item-desc">
              {sourceStatus?.sim_workbook || "-"} · {sourceStatus?.total_sheets || 0} 张表
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ========== AI 回答可读性渲染 ==========
const AI_FIELD_LABELS = {
  oee_source: "\u7efc\u5408\u8bbe\u5907\u6548\u7387（OEE）",
  total_output: "\u603b\u4ea7\u91cf",
  good_output: "\u826f\u54c1\u6570",
  defect_total: "\u7f3a\u9677\u603b\u6570",
  yield: "\u826f\u7387",
  unplanned_downtime_minutes: "\u975e\u8ba1\u5212\u505c\u673a\u65f6\u957f",
  blocked_gap_count: "\u963b\u585e\u7f3a\u53e3\u6570",
  spc_measurement_points: "SPC\u6d4b\u91cf\u70b9",
  sample_rule: "\u62bd\u6837\u89c4\u5219",
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

function formatAIValue(metric) {
  const value = metric?.value;
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value !== "number") return localizeAIText(value);
  const format = metric?.display_format || "0.0%";
  if (format.includes("%")) return `${(value * 100).toFixed(1)}%`;
  if (format === "0") return Math.round(value).toLocaleString("zh-CN");
  return value.toLocaleString("zh-CN", { maximumFractionDigits: 3 });
}

function AIViewPreview({ view }) {
  if (!view) return null;
  const key = `${view.role || "factory"}|${view.scope || "ALL_LINES"}|${view.time_window || "last_7_shifts"}`;
  const snapshot = getViewSnapshot(key) || getViewSnapshot(`factory|ALL_LINES|${view.time_window || "last_7_shifts"}`);
  const charts = Array.isArray(view.charts) ? view.charts : [];
  const chartOptions = charts.map((spec) => {
    const chart = getChartById(snapshot, spec.chart_id);
    if (!chart) return { ...spec, option: null };
    if (spec.chart_id === "ranking_bar") return { ...spec, option: buildRankingOption(chart.data || []) };
    if (spec.chart_id === "stop_pareto") return { ...spec, option: buildDowntimeOption(chart.data || []) };
    if (spec.chart_id === "defect_table") {
      const table = getTableById(snapshot, "defect_table");
      return { ...spec, option: table ? buildDefectParetoOption(table.rows || []) : null };
    }
    const option = chart.type === "line" ? buildSingleTrendOption(chart.data, view.scope) : buildTrendOption(chart.data, getAllLines());
    return { ...spec, option };
  });
  return (
    <div className="ai-view-preview">
      <div className="ai-result-section-title">已生成看板视图</div>
      <div className="text-sm">{view.title_zh || "按问题生成的临时看板"} · {t_timeWindow(view.time_window)} · {view.scope === "ALL_LINES" ? "全厂" : t_line(view.scope)}</div>
      <div className="ai-view-preview-grid">
        {chartOptions.map((item, index) => (
          <div className="ai-view-preview-card" key={`${item.chart_id}-${index}`}>
            <strong>{item.title_zh}</strong>
            {item.option ? <EChart option={item.option} style={{ height: "180px", width: "100%" }} /> : <div className="text-sm text-muted">当前范围没有可用于该图表的记录。</div>}
          </div>
        ))}
      </div>
      <div className="text-xs text-muted">只读预览：图表来自当前数据源，不修改正式看板或指标。</div>
    </div>
  );
}

function AIResultMessage({ result }) {
  const statusLabel = {
    needs_confirmation: "待人工确认",
    warning: "预警",
    completed: "已完成",
    no_data: "暂无数据",
  }[result?.status] || "已分析";
  const statusType = result?.status === "needs_confirmation" ? "warning" : result?.status === "warning" ? "warning" : "success";
  const metrics = Array.isArray(result?.kpis) ? result.kpis.slice(0, 8) : [];
  const risks = Array.isArray(result?.risks) ? result.risks.slice(0, 3) : [];
  const actions = Array.isArray(result?.recommended_actions) ? result.recommended_actions.slice(0, 4) : [];
  const gaps = Array.isArray(result?.data_gaps) ? result.data_gaps.slice(0, 4) : [];
  return (
    <div className="ai-readable-content ai-result-content">
      <div className="ai-result-headline">
        <div className="ai-readable-heading">核心结论</div>
        <Badge type={statusType} dot>{statusLabel}</Badge>
        <div className="ai-result-headline-text">{localizeAIText(result?.headline || "暂无可展示结论")}</div>
      </div>

      {metrics.length > 0 && (
        <div className="ai-result-section">
          <div className="ai-result-section-title">关键指标</div>
          <div className="ai-result-kpis">
            {metrics.map((metric, index) => (
              <div className="ai-result-kpi" key={metric.metric_id || index}>
                <div className="ai-result-kpi-label">{localizeAIText(metric.label || metric.semantic_field || "指标")}</div>
                <div className="ai-result-kpi-value">{formatAIValue(metric)}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {risks.length > 0 && (
        <div className="ai-result-section">
          <div className="ai-result-section-title">重点风险</div>
          {risks.map((risk, index) => (
            <div className="ai-risk-item" key={`${risk.title}-${index}`}>
              <span className="ai-risk-index">{index + 1}</span>
              <span>{localizeAIText(risk.title)}</span>
            </div>
          ))}
        </div>
      )}

      {actions.length > 0 && (
        <div className="ai-result-section">
          <div className="ai-result-section-title">建议动作</div>
          {actions.map((action, index) => (
            <div className="ai-action-item" key={action.action_id || index}>
              <div className="ai-action-title">{localizeAIText(action.title)}</div>
              <div className="ai-action-meta">
                <Badge type={action.needs_human_confirmation ? "warning" : "info"}>
                  {action.needs_human_confirmation ? "需人工确认" : "仅生成草稿"}
                </Badge>
                <span>{action.priority === "high" ? "高优先级" : action.priority === "low" ? "低优先级" : "中优先级"}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {gaps.length > 0 && (
        <div className="ai-result-section ai-result-gap-section">
          <div className="ai-result-section-title">数据缺口</div>
          {gaps.map((gap, index) => (
            <div className="ai-result-gap" key={`${gap.field}-${index}`}>
              <strong>{localizeAIText(gap.field || "未命名字段")}</strong>
              <span>{localizeAIText(gap.resolution || gap.reason || "需要补充数据")}</span>
            </div>
          ))}
        </div>
      )}

      {result?.view_request && <AIViewPreview view={result.view_request} />}

      <details className="ai-result-evidence">
        <summary>查看证据引用（{result?.evidence_refs?.length || 0}）</summary>
        <div>{(result?.evidence_refs || []).slice(0, 12).join("、") || "当前结果没有可展示的证据引用"}</div>
      </details>
    </div>
  );
}

function AIMessage({ text, result }) {
  if (result?.contract_version === "BIFROST-AI-RESULT-v1") {
    return <AIResultMessage result={result} />;
  }
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

// ========== AI 助手抽屉 ==========
function AIDrawer({ open, onClose, context, role = "factory", onViewIntent }) {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([]);
  const [aiState, setAiState] = useState("disabled"); // ready, thinking, analyzing, disabled
  const textareaRef = useRef(null);

  const conn = getSourceStatus()?.connection_mode || {};
  const ailyConnected = conn.aily_mode === "connected";

  const quickQuestions = BIFROST_I18N.quickQuestions[role] || [];

  // Local bridge health is checked server-side; no API key reaches the browser.
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
          workflow_snapshot: {
            dataset_id: BIFROST_DATA.overview?.dataset_id || null,
            source_payload_sha256: BIFROST_DATA.overview?.source_profile?.source_sha256 || null,
            rule_version: BIFROST_DATA.overview?.rule_version || BIFROST_DATA.event?.rule_version || null,
            formal_findings: BIFROST_DATA.event?.formal_findings?.[context?.role || role] || [],
            event_summary: BIFROST_DATA.event?.event_id === (context?.eventId || BIFROST_DATA.event?.event_id)
              ? { headline: BIFROST_DATA.event?.headline, conclusion: BIFROST_DATA.event?.conclusion }
              : null,
          },
        }),
      });
      const payload = await response.json();
      if (!response.ok || payload.status !== "ok") {
        throw new Error(payload.error || "AI服务调用失败");
      }
      setMessages((prev) => [...prev, {
        type: "ai",
        text: payload.answer,
        result: payload.result_contract || null,
      }]);
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

  const handleSend = useCallback(() => {
    if (!aiUsable) return;
    const text = input.trim();
    if (!text) return;
    onViewIntent?.(text);
    setMessages((prev) => [...prev, { type: "user", text }]);
    setInput("");
    setAiState("thinking");
    dispatchCommand(text).catch((error) => {
      setMessages((prev) => [...prev, { type: "ai", text: formatAIError(error) }]);
      setAiState("failed");
    });
  }, [input, aiUsable, dispatchCommand, onViewIntent]);

  const handleQuickQuestion = (q) => {
    if (!aiUsable) return;
    onViewIntent?.(q);
    setInput(q);
    requestAnimationFrame(() => {
      setMessages((prev) => [...prev, { type: "user", text: q }]);
      setInput("");
      setAiState("thinking");
      dispatchCommand(q).catch((error) => {
        setMessages((prev) => [...prev, { type: "ai", text: formatAIError(error) }]);
        setAiState("failed");
      });
    });
  };

  const [showOnboarding, setShowOnboarding] = useState(false);

  return (
    <>
      <div
        className={`ai-drawer-overlay ${open ? "open" : ""}`}
        onClick={onClose}
      />
      <div className={`ai-drawer ${open ? "open" : ""}`}>
        <div className="ai-drawer-header">
          <div className="ai-drawer-title">
            <div className="flex items-center gap-2">
              <Icon.AI />
              <span>AI 助手</span>
              <Badge type={aiConnected ? "success" : "default"} dot>
                {apiConnected ? "本地桥接就绪" : t_aiStatus(aiConnected ? "ready" : "disabled")}
              </Badge>
            </div>
            <button className="icon-btn" style={{ color: "#fff" }} onClick={onClose}>
              <Icon.Close />
            </button>
          </div>
          <dl className="ai-drawer-context">
            <dt>当前角色</dt>
            <dd>{t_roles(context?.role || role)}</dd>
            <dt>分析范围</dt>
            <dd>{t_scope(context?.scope || "ALL_LINES")}</dd>
            <dt>时间范围</dt>
            <dd>{t_timeWindow(context?.timeWindow || "last_7_shifts")}</dd>
            {context?.eventId && (
              <>
                <dt>当前事件</dt>
                <dd className="mono">{context.eventId}</dd>
              </>
            )}
          </dl>
        </div>

        <div className="ai-drawer-body">
          {messages.length === 0 && (
            <div className="ai-msg ai">
              您好，我是 BIFROST AI 助手。我可以帮您分析产线数据、解释异常原因、创建任务草稿。请输入您的问题，或从下方快捷问题中选择。
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`ai-msg ${m.type}`}>{m.type === "ai" ? <AIMessage text={m.text} result={m.result} /> : m.text}</div>
          ))}

          {messages.length === 0 && (
            <div className="ai-quick-questions">
              <div className="ai-quick-title">快捷问题</div>
              {quickQuestions.map((q, i) => (
                <button
                  key={i}
                  className="ai-quick-item"
                  onClick={() => handleQuickQuestion(q)}
                  disabled={!aiUsable}
                >
                  <span style={{
                    width: "20px",
                    height: "20px",
                    borderRadius: "50%",
                    background: "var(--c-primary-50)",
                    color: "var(--c-primary-500)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: "11px",
                    fontWeight: "600",
                    flexShrink: "0",
                  }}>
                    {i + 1}
                  </span>
                  <span>{q}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="ai-drawer-input-wrap">
          {aiMisconfigured && (
            <div className="ai-disabled-hint" style={{ background: "var(--c-danger-light)", color: "var(--c-danger)" }}>
              <Icon.Error />
              <div>
                AI 接入配置不完整：连接模式已启用但适配器未加载。请联系管理员检查配置。
              </div>
            </div>
          )}
          {!aiConnected && (
            <div className="ai-disabled-hint">
              <Icon.Warning />
              <div style={{ flex: 1 }}>
                AI 助手尚未连接，启动本地桥接服务后可发送指令。
                <button
                  onClick={(e) => { e.preventDefault(); setShowOnboarding(true); }}
                  style={{ color: "var(--c-warning)", textDecoration: "underline", marginLeft: "4px", background: "none", border: "none", padding: 0, cursor: "pointer", fontSize: "inherit" }}
                >
                  查看接入说明
                </button>
              </div>
            </div>
          )}
          {showOnboarding && (
            <div style={{
              position: "absolute", top: 0, left: 0, right: 0, bottom: 0,
              background: "rgba(255,255,255,0.98)",
              zIndex: 10,
              padding: "20px",
              overflowY: "auto",
            }}>
              <div className="flex items-center justify-between mb-3">
                <div style={{ fontSize: "14px", fontWeight: 600 }}>AI 助手接入说明</div>
                <button className="icon-btn" onClick={() => setShowOnboarding(false)}>
                  <Icon.Close />
                </button>
              </div>
              <div style={{ fontSize: "13px", lineHeight: 1.8, color: "var(--c-gray-700)" }}>
                <p style={{ marginBottom: "12px" }}>
                  <strong>当前状态：</strong>AI 尚未连接（<code className="mono">aily_mode = disabled</code>）。
                </p>
                <p style={{ marginBottom: "12px" }}>
                  <strong>接入步骤：</strong>
                </p>
                <ol style={{ paddingLeft: "20px", marginBottom: "12px" }}>
                  <li>在管理配置 → AI 适配器中配置 Aily 服务地址与认证信息</li>
                  <li>确保 <code className="mono">AilyAdapter</code> 脚本已加载到页面</li>
                  <li>配置成功后连接模式将变为「已连接」，即可发送指令</li>
                </ol>
                <p style={{ marginBottom: "12px" }}>
                  <strong>注意事项：</strong>
                </p>
                <ul style={{ paddingLeft: "20px" }}>
                  <li>当前为只读模式，AI 生成的操作需人工确认后才可执行</li>
                  <li>高风险动作（解除冻结、改规则、改交付承诺）仅生成草稿</li>
                  <li>所有 AI 操作均记录 RunID，可在审计日志中追溯</li>
                </ul>
              </div>
            </div>
          )}
          <div className={`ai-input-box ${!aiUsable ? "disabled" : ""}`}>
            <textarea
              ref={textareaRef}
              className="ai-input"
              placeholder={aiUsable ? "输入您的问题..." : "AI 尚未连接，接入后可发送指令"}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              disabled={!aiUsable}
              rows={1}
            />
            <button
              className="btn btn-accent btn-sm"
              onClick={handleSend}
              disabled={!aiUsable || !input.trim()}
              title={aiMisconfigured ? "AI 接入配置不完整" : (!aiConnected ? "AI 尚未连接" : "")}
            >
              <Icon.Send />
              发送
            </button>
          </div>
          <div className="ai-status-bar">
            <span className={`ai-status-dot ${
              aiState === "thinking" || aiState === "analyzing" ? "thinking" :
              aiUsable ? "ready" : "disabled"
            }`}></span>
            <span>
              {aiState === "thinking"
                ? t_aiStatus("thinking")
                : aiState === "analyzing"
                ? t_aiStatus("analyzing")
                : aiState === "failed"
                ? t_aiStatus("failed")
                : aiMisconfigured
                ? "AI 接入配置不完整"
                : aiUsable
                ? t_aiStatus("ready")
                : t_aiStatus("disabled")}
            </span>
            <span style={{ marginLeft: "auto" }} className="text-muted">
              高风险操作仅生成草稿，需人工确认
            </span>
          </div>
        </div>
      </div>
    </>
  );
}

// ========== 事件时间线 ==========
function EventTimeline({ items }) {
  return (
    <div className="timeline">
      {items.map((item, i) => (
        <div key={i} className={`timeline-item ${item.active ? "active" : ""}`}>
          <div className="timeline-title">{item.title}</div>
          <div className="timeline-meta">{item.meta}</div>
          {item.desc && <div className="timeline-desc">{item.desc}</div>}
        </div>
      ))}
    </div>
  );
}

// 导出到全局
Object.assign(window, {
  Icon,
  Badge,
  KpiCard,
  Segmented,
  Card,
  Collapse,
  EChart,
  SystemStatusPanel,
  AIDrawer,
  EventTimeline,
});
