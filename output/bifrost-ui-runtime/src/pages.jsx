/* ===== BIFROST 页面组件 v3.2 =====
   看板中心 / 事件中心 / 数据治理 / 管理配置
   全部中文标签，信息架构重排
*/

const { useState, useEffect, useMemo, useRef } = React;

// ========== 看板中心 ==========
function DashboardPage({ role, setRole, timeWindow, setTimeWindow, scope, setScope, onAskAI, onNavigate }) {
  const [selectedLines, setSelectedLines] = useState(() => getAllLines());
  const [selectedDrilldownLine, setSelectedDrilldownLine] = useState(null);

  useEffect(() => {
    const available = getAllLines();
    setSelectedLines((current) => {
      const kept = current.filter((line) => available.includes(line));
      return kept.length ? kept : available;
    });
  }, [role, timeWindow]);

  const effectiveScope = resolveScopeForRole(role, scope);

  // 当前视图数据
  const currentViewKey = useMemo(() => {
    if (role === "factory") {
      return `factory|ALL_LINES|${timeWindow}`;
    } else {
      return `${role}|${effectiveScope}|${timeWindow}`;
    }
  }, [role, timeWindow, effectiveScope]);

  const currentView = useMemo(() => getViewSnapshot(currentViewKey), [currentViewKey]);

  const factoryDecisionSummary = useMemo(() => {
    if (role !== "factory") return null;
    const rows = getAllLines().map((line) => {
      const view = getViewSnapshot(`line|${line}|${timeWindow}`);
      const kpis = view?.kpis || [];
      const value = (code) => kpis.find((k) => k.metric_code === code)?.value;
      return { line, label: getLineLabel(line, view), oee: value("OEE"), quality: value("QUALITY"), availability: value("AVAILABILITY") };
    }).filter((row) => typeof row.oee === "number");
    if (!rows.length) return null;
    const lowest = (field) => rows.reduce((a, b) => (typeof b[field] === "number" && b[field] < a[field] ? b : a), rows[0]);
    return { lowestOee: lowest("oee"), lowestQuality: lowest("quality"), lowestAvailability: lowest("availability") };
  }, [role, timeWindow]);

  // 单产线视图（线长视角的对比）
  const lineViews = useMemo(() => {
    if (role !== "factory") return [];
    return getAllLines().map((line) => ({
      line,
      view: getViewSnapshot(`line|${line}|${timeWindow}`),
    }));
  }, [role, timeWindow]);

  useEffect(() => {
    if (role !== "factory") {
      setSelectedDrilldownLine(null);
      return;
    }
    const available = lineViews.map(({ line }) => line);
    setSelectedDrilldownLine((current) => current && available.includes(current) ? current : null);
  }, [role, lineViews]);

  const selectedLineView = useMemo(() => {
    if (!selectedDrilldownLine) return null;
    return getViewSnapshot(`line|${selectedDrilldownLine}|${timeWindow}`);
  }, [selectedDrilldownLine, timeWindow]);

  const selectedLineTrend = useMemo(() => {
    if (!selectedLineView) return null;
    const chart = getChartById(selectedLineView, "oee_trend") || getChartById(selectedLineView, "trend_comparison");
    if (!chart) return null;
    return chart.type === "line" ? buildSingleTrendOption(chart.data, selectedDrilldownLine) : buildTrendOption(chart.data, [selectedDrilldownLine]);
  }, [selectedLineView, selectedDrilldownLine]);

  const selectedLineDefects = useMemo(() => {
    if (!selectedLineView || !selectedDrilldownLine) return null;
    return getTableById(selectedLineView, `defect_${selectedDrilldownLine}`) || getTableById(selectedLineView, "defect_table");
  }, [selectedLineView, selectedDrilldownLine]);

  const selectedLineStops = useMemo(() => {
    if (!selectedLineView || !selectedDrilldownLine) return null;
    const table = getTableById(selectedLineView, `stops_${selectedDrilldownLine}`) || getTableById(selectedLineView, "stops_table");
    if (table) return table;
    const chart = getChartById(selectedLineView, "stop_pareto");
    return chart?.data ? { table_id: "stop_pareto", rows: chart.data } : null;
  }, [selectedLineView, selectedDrilldownLine]);

  // KPI 列表
  const kpis = currentView?.kpis || [];
  const alerts = currentView?.alerts || [];
  const tasks = currentView?.tasks || [];
  const decisions = currentView?.decisions_required || [];

  // ===== 只读模式判断 =====
  const isReadonly = useMemo(() => {
    const s = getSourceStatus();
    return s?.connection_mode?.writeback_mode === "readonly";
  }, []);

  // ===== 趋势图：直接消费当前视图的 trend_comparison / oee_trend / quality_trend / perf_trend =====
  const trendChart = useMemo(() => {
    if (!currentView) return null;
    // 按优先级选择第一张趋势图
    const ids = ["trend_comparison", "oee_trend", "quality_trend", "perf_trend", "stop_comparison"];
    for (const id of ids) {
      const c = getChartById(currentView, id);
      if (c) return c;
    }
    return null;
  }, [currentView]);

  const trendOption = useMemo(() => {
    if (!trendChart) return null;
    const data = trendChart.data;
    // line_multi 类型：data 是 { lineId: {label, dates, values} }
    if (trendChart.type === "line_multi" && typeof data === "object") {
      return buildTrendOption(data, selectedLines);
    }
    if (trendChart.type === "line" && typeof data === "object") {
      return buildSingleTrendOption(data, effectiveScope);
    }
    return null;
  }, [trendChart, selectedLines]);

  const trendTitle = useMemo(() => {
    if (!trendChart) return "趋势分析";
    return trendChart.title || "趋势分析";
  }, [trendChart]);

  // ===== 排行 / 对比图：ranking_bar =====
  const rankingChart = useMemo(() => {
    if (!currentView) return null;
    return getChartById(currentView, "ranking_bar");
  }, [currentView]);

  const rankingOption = useMemo(() => {
    if (!rankingChart || !Array.isArray(rankingChart.data)) return null;
    // 按 selectedLines 过滤
    const filtered = selectedLines && selectedLines.length > 0
      ? rankingChart.data.filter((r) => selectedLines.includes(r.line_id))
      : rankingChart.data;
    return buildRankingOption(filtered);
  }, [rankingChart, selectedLines]);

  // ===== 缺陷 Pareto（质量角色）：从 defect_table 读取 =====
  const defectTable = useMemo(() => {
    if (!currentView) return null;
    // 优先找 defect_table，再按当前产线找 defect_LINE-Sxx
    let t = getTableById(currentView, "defect_table");
    if (!t && role === "line" && effectiveScope) {
      t = getTableById(currentView, `defect_${effectiveScope}`);
    }
    // quality 角色 ALL_LINES 视图可能有3条产线各一个表，取第一个有数据的
    if (!t && currentView.tables) {
      const tables = currentView.tables.filter((tbl) =>
        tbl.table_id && tbl.table_id.startsWith("defect_") && Array.isArray(tbl.rows)
      );
      if (tables.length === 1) t = tables[0];
      if (tables.length > 1) {
        t = { table_id: "defect_ALL_LINES", rows: tables.flatMap((tbl) => tbl.rows || []) };
      }
    }
    return t;
  }, [currentView, role, effectiveScope]);

  const defectParetoOption = useMemo(() => {
    if (!defectTable || !defectTable.rows) return null;
    return buildDefectParetoOption(defectTable.rows);
  }, [defectTable]);

  // ===== 停机分布（设备角色）：从 stops_ 表读取 =====
  const downtimeTable = useMemo(() => {
    if (!currentView) return null;
    let t = null;
    if (role === "line" && effectiveScope) {
      t = getTableById(currentView, `stops_${effectiveScope}`);
    }
    if (!t && currentView.tables) {
      const tables = currentView.tables.filter((tbl) =>
        tbl.table_id && tbl.table_id.startsWith("stops_") && Array.isArray(tbl.rows)
      );
      if (tables.length === 1) t = tables[0];
      if (tables.length > 1) {
        t = { table_id: "stops_ALL_LINES", rows: tables.flatMap((tbl) => tbl.rows || []) };
      }
    }
    return t;
  }, [currentView, role, effectiveScope]);

  const downtimeOption = useMemo(() => {
    if (!downtimeTable || !downtimeTable.rows) return null;
    return buildDowntimeOption(downtimeTable.rows);
  }, [downtimeTable]);

  // ===== 异常列表：直接使用 alerts，空则空态 =====
  const alertItems = useMemo(() => {
    return (alerts || []).slice(0, 3).map((a) => ({
      alert_id: a.alert_id,
      severity: a.severity,
      title: a.message,
      line: a.line_id || (currentView?.scope?.line_ids?.[0]) || "",
      metric: a.metric_code || a.metric || "",
    }));
  }, [alerts, currentView]);

  // ===== 待确认事项：使用 decisions_required + tasks，空则空态 =====
  const todoItems = useMemo(() => {
    const items = [];
    (decisions || []).forEach((d) => {
      items.push({
        type: "decision",
        id: d.decision_id,
        title: d.action || d.title || d.decision_id,
        severity: d.risk_level || d.severity || "medium",
        status: d.status,
        desc: d.description || `决策编号 ${d.decision_id}，确认编号 ${d.confirmation_id || "待生成"}`,
      });
    });
    (tasks || []).forEach((t) => {
      items.push({
        type: "task",
        id: t.task_id,
        title: t.description || t.title || t.task_id,
        severity: "low",
        status: t.status,
        desc: `任务编号 ${t.task_id}`,
      });
    });
    return items.slice(0, 3);
  }, [decisions, tasks]);

  // ===== 多产线选择：最少保留一条 =====
  const handleToggleLine = (line) => {
    setSelectedLines((prev) => {
      if (prev.includes(line)) {
        if (prev.length <= 1) return prev; // 至少保留一条
        return prev.filter((l) => l !== line);
      }
      return [...prev, line];
    });
  };

  // 渲染 KPI 卡片
  const renderKpis = () => {
    if (kpis.length === 0) {
      return (
        <div className="grid grid-kpi">
          {[1, 2, 3, 4].map((i) => (
            <KpiCard key={i} label="暂无数据" value="-" status="default" />
          ))}
        </div>
      );
    }
    return (
      <div className="grid grid-kpi">
        {kpis.slice(0, 8).map((kpi, kIndex) => {
          const val = formatKpiValue(kpi);
          const target = formatKpiTarget(kpi);
          const status = getKpiStatus(kpi);
          const fullLabel = t_metric(kpi.metric_code, true);

          return (
            <KpiCard
              key={`${kpi.metric_code || "metric"}-${kpi.line_id || kIndex}`}
              label={
                <span>
                  {t_metric(kpi.metric_code)}{kpi.line_id ? ` · ${t_line(kpi.line_id)}` : ""}
                  <span className="tooltip-wrapper" title={fullLabel}>
                    <Icon.Info className="tooltip-icon" style={{ width: 12, height: 12 }} />
                  </span>
                </span>
              }
              value={val}
              target={target}
              status={status}
            />
          );
        })}
      </div>
    );
  };

  const severityType = (s) => ({
    critical: "danger", high: "danger", medium: "warning", low: "info",
  }[s] || "default");

  const severityLabel = (s) => ({
    critical: "严重", high: "高", medium: "中", low: "低",
  }[s] || s);

  return (
    <div className="page-content">
      {/* 1. 当前状态：核心 KPI */}
      <div className="mb-4">
        <div className="flex items-center justify-between mb-3">
          <h2 style={{ fontSize: "15px", fontWeight: 600, color: "var(--c-gray-900)" }}>
            当前状态
          </h2>
          <span className="text-sm text-muted">
            数据更新于 {currentView?.last_updated_at
              ? currentView.last_updated_at.slice(0, 19).replace("T", " ")
              : "-"}
          </span>
        </div>
        {renderKpis()}
        {currentView?.headline && (
          <div style={{
            marginTop: "12px",
            padding: "10px 14px",
            background: "var(--c-primary-50)",
            borderRadius: "var(--radius-sm)",
            fontSize: "13px",
            color: "var(--c-primary)",
            borderLeft: "3px solid var(--c-primary-500)",
          }}>
            <strong>核心结论：</strong>{currentView.headline}
          </div>
        )}
      </div>

      {role === "factory" && lineViews.length > 0 && (
        <Card title="各产线运行明细" extra={<span className="text-sm text-muted">可点击产线名称查看对应视角</span>}>
          <div className="data-table-wrap">
            <table className="data-table">
              <thead><tr><th>产线</th><th>综合设备效率</th><th>开动率</th><th>质量率</th><th>当前状态</th></tr></thead>
              <tbody>
                {lineViews.map(({ line, view }) => {
                  const value = (code) => view?.kpis?.find((kpi) => kpi.metric_code === code)?.value;
                  const oee = value("OEE");
                  const availability = value("AVAILABILITY");
                  const quality = value("QUALITY");
                  const status = typeof oee === "number" && oee < 0.76 ? "需要关注" : "正常";
                  return <tr key={line} onClick={() => setSelectedDrilldownLine(line)} style={{ cursor: "pointer", background: selectedDrilldownLine === line ? "var(--c-primary-50)" : undefined }} title="点击查看该产线的班次、停机和质量明细">
                    <td><button className="btn btn-link btn-sm" onClick={(event) => { event.stopPropagation(); setSelectedDrilldownLine(line); }}>{getLineLabel(line, view)} · 查看详情</button></td>
                    <td>{typeof oee === "number" ? `${(oee * 100).toFixed(1)}%` : "-"}</td>
                    <td>{typeof availability === "number" ? `${(availability * 100).toFixed(1)}%` : "-"}</td>
                    <td>{typeof quality === "number" ? `${(quality * 100).toFixed(1)}%` : "-"}</td>
                    <td><Badge type={status === "正常" ? "success" : "warning"}>{status}</Badge></td>
                  </tr>;
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {role === "factory" && selectedDrilldownLine && selectedLineView && (
        <Card
          title={<span>产线详情 · {getLineLabel(selectedDrilldownLine, selectedLineView)}</span>}
          extra={<button className="btn btn-ghost btn-sm" onClick={() => setSelectedDrilldownLine(null)}>返回全厂总览</button>}
        >
          <div className="text-sm text-muted" style={{ marginBottom: "12px" }}>
            当前时间范围：{selectedLineView.time_window?.label || timeWindow}。下面按“产线表现 → 主要问题 → 处理入口”展示，帮助你从指标继续定位到具体班次和记录。
          </div>
          <div className="grid grid-kpi" style={{ marginBottom: "12px" }}>
            {(selectedLineView.kpis || []).filter((k) => ["OEE", "AVAILABILITY", "PERFORMANCE", "QUALITY", "TOTAL_OUTPUT", "GOOD_OUTPUT"].includes(k.metric_code)).slice(0, 6).map((kpi, index) => (
              <KpiCard key={`${kpi.metric_code}-${index}`} label={t_metric(kpi.metric_code)} value={formatKpiValue(kpi)} target={formatKpiTarget(kpi)} status={getKpiStatus(kpi)} />
            ))}
          </div>
          <div className="grid grid-2 gap-3">
            <div>
              <h4 style={{ margin: "0 0 8px", fontSize: "14px" }}>OEE趋势</h4>
              {selectedLineTrend ? <EChart option={selectedLineTrend} className="chart-wrap" /> : <div className="empty-state">该时间范围暂无趋势记录</div>}
            </div>
            <div>
              <h4 style={{ margin: "0 0 8px", fontSize: "14px" }}>主要问题与影响</h4>
              <div className="text-sm" style={{ lineHeight: 1.8 }}>
                <div>停机问题：{selectedLineStops?.rows?.length ?? 0} 类（按影响时长排序）</div>
                <div>质量问题分类：{selectedLineDefects?.rows?.length ?? 0} 类（按不良数量排序）</div>
                <button className="btn btn-link btn-sm" onClick={() => onNavigate?.("events")}>查看班次、问题记录和处理进度 →</button>
              </div>
              <div className="text-xs text-muted" style={{ margin: "8px 0", lineHeight: 1.6 }}>
                质量问题分类回答“检测发现了什么”：外观不良=外观检查异常，尺寸超差=尺寸超出规格，功能失效=功能测试未通过，电气功能问题=通电、连接或信号测试异常。它们是问题分类，根因需要结合班次、工序、设备和物料记录继续确认。
              </div>
              {selectedLineStops?.rows?.slice(0, 5).map((row, index) => <div className="list-item" key={`stop-${index}`}><span>{displayBusinessReason(row.label || row.group || row.reason || row.stop_reason || row.category || "停机事件")}</span><span>{row.minutes ?? row.duration_minutes ?? row.duration ?? "-"} 分钟</span></div>)}
              {(() => {
                const rows = selectedLineDefects?.rows || [];
                const total = rows.reduce((sum, row) => sum + (Number(row.count ?? row.quantity ?? row.value) || 0), 0);
                return rows.slice(0, 5).map((row, index) => {
                  const count = Number(row.count ?? row.quantity ?? row.value) || 0;
                  const rawLabel = row.type || row.defect_type || row.category || row.label || "未分类质量问题";
                  const label = displayBusinessReason(rawLabel);
                  const explanation = ({
                    "外观不良": "外观检查发现异常",
                    "尺寸超差": "尺寸超出规格范围",
                    "功能失效": "功能测试未通过",
                    "电气功能问题": "通电、连接或信号测试异常",
                    "其他不良": "暂未归入以上分类",
                  })[label] || "质量检测发现的问题分类";
                  return <button className="list-item" key={`defect-${index}`} onClick={() => onNavigate?.("events")} title={`${explanation}。点击查看班次、工单和证据`} style={{ width: "100%", border: 0, borderTop: "1px solid var(--c-gray-200)", background: "transparent", textAlign: "left", cursor: "pointer", display: "flex", alignItems: "center", gap: "12px" }}><span style={{ flex: 1 }}><strong style={{ display: "block" }}>{label}</strong><small className="text-xs text-muted">{explanation}</small></span><span>{count.toLocaleString("zh-CN")} 件{total ? ` · ${(count / total * 100).toFixed(1)}%` : ""} →</span></button>;
                });
              })()}
            </div>
          </div>
        </Card>
      )}

      <ReadableBusinessInterpretationCard view={currentView} role={role} scope={effectiveScope} timeWindow={timeWindow} onNavigate={onNavigate} />
      <PeerOverlayPanel role={role} />
      <FormalDerivedInsightsPanel role={role} />

      {/* 2. 重点异常 + 建议动作 */}
      <div className="grid grid-2 mb-4">
        <Card
          title={
            <span className="flex items-center gap-2">
              <Icon.Warning style={{ color: "var(--c-danger)" }} />
              重点异常
            </span>
          }
          extra={<Badge type="danger" dot>{alertItems.length} 项</Badge>}
        >
          <div>
            {alertItems.length === 0 ? (
              <div className="empty-state">当前数据合同未提供异常记录</div>
            ) : (
              alertItems.map((a, i) => (
                <div key={a.alert_id || i} className="list-item">
                  <Badge type={severityType(a.severity)}>{severityLabel(a.severity)}</Badge>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: "13px", fontWeight: 500, color: "var(--c-gray-900)" }}>
                      {a.title}
                    </div>
                    <div style={{ fontSize: "11px", color: "var(--c-gray-500)", marginTop: "2px" }}>
                      {a.line && t_line(a.line)} · {t_metric(a.metric) || a.metric}
                    </div>
                  </div>
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={() => {
                      // 跳转到事件中心并展示对应事件
                    }}
                    disabled={!a.alert_id}
                    title={!a.alert_id ? "无事件详情" : "查看异常详情"}
                  >
                    查看
                  </button>
                </div>
              ))
            )}
          </div>
        </Card>

        <Card
          title={
            <span className="flex items-center gap-2">
              <Icon.Task style={{ color: "var(--c-accent)" }} />
              待确认事项
            </span>
          }
          extra={<Badge type="warning" dot>{todoItems.length} 项</Badge>}
        >
          <div>
            {todoItems.length === 0 ? (
              <div className="empty-state">当前数据合同未提供待办事项</div>
            ) : (
              todoItems.map((t, i) => (
                <div key={t.id || i} className="list-item">
                  <Badge type="warning">
                    {t.status === "已完成" ? "已完成" : t.status || "待确认"}
                  </Badge>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: "13px", fontWeight: 500, color: "var(--c-gray-900)" }}>
                      {t.title}
                    </div>
                    <div style={{ fontSize: "12px", color: "var(--c-gray-500)", marginTop: "4px", lineHeight: 1.5 }}>
                      {t.desc}
                    </div>
                  </div>
                  <button
                    className="btn btn-accent btn-sm"
                    disabled={isReadonly || t.status === "已完成"}
                    title={isReadonly ? "当前为只读模式，暂不能提交" : ""}
                  >
                    处理
                  </button>
                </div>
              ))
            )}
          </div>
        </Card>
      </div>

       {/* 3. 趋势 & 专业分析 */}
      <div className="grid grid-2 mb-4">
        <Card title={trendTitle}>
          {trendOption ? (
            <EChart option={trendOption} className="chart-wrap" />
          ) : (
            <div className="empty-state">当前数据合同未提供该分析</div>
          )}
        </Card>

        {role === "factory" ? (
          <Card
            title="OEE 排行"
            extra={
              <div className="flex gap-2">
                {getAllLines().map((line) => {
                  const lineLabel = getLineLabel(line, getViewSnapshot(`line|${line}|${timeWindow}`));
                  return (
                    <button
                      key={line}
                      className={`line-checkbox-card ${selectedLines.includes(line) ? "checked" : ""}`}
                      onClick={() => handleToggleLine(line)}
                      disabled={selectedLines.includes(line) && selectedLines.length <= 1}
                      title={selectedLines.includes(line) && selectedLines.length <= 1 ? "至少保留一条产线" : ""}
                    >
                      <span style={{
                        width: "12px", height: "12px",
                        borderRadius: "2px",
                        border: "1.5px solid var(--c-primary-400)",
                        background: selectedLines.includes(line) ? "var(--c-primary-500)" : "#fff",
                        display: "flex", alignItems: "center", justifyContent: "center",
                      }}>
                        {selectedLines.includes(line) && <Icon.Check style={{ color: "#fff", width: 10, height: 10 }} />}
                      </span>
                      {lineLabel}
                    </button>
                  );
                })}
              </div>
            }
          >
            {rankingOption ? (
              <EChart option={rankingOption} className="chart-wrap" />
            ) : (
              <div className="empty-state">当前数据合同未提供该分析</div>
            )}
          </Card>
        ) : role === "quality" ? (
          <Card title="主要缺陷及累计影响">
            <div className="text-xs text-muted" style={{ marginBottom: "8px" }}>柱形表示各类不良数量，折线表示累计占比；最后达到100%是累计统计的正常结果，不代表单一原因占100%。</div>
            {defectParetoOption ? (
              <EChart option={defectParetoOption} className="chart-wrap" />
            ) : (
              <div className="empty-state">当前数据合同未提供该分析</div>
            )}
          </Card>
        ) : role === "equipment" ? (
          <Card title="主要停机原因及累计影响">
            <div className="text-xs text-muted" style={{ marginBottom: "8px" }}>按停机次数或时长排序，用于确定优先排查项；排序结果是关联线索，不等同于已确认根因。</div>
            {downtimeOption ? (
              <EChart option={downtimeOption} className="chart-wrap" />
            ) : (
              <div className="empty-state">当前数据合同未提供该分析</div>
            )}
          </Card>
        ) : (
          <Card title="详细指标分析">
            <table className="data-table">
              <thead>
                <tr>
                  <th>指标</th>
                  <th>当前值</th>
                  <th>目标</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                {kpis.map((k) => (
                  <tr key={k.metric_code}>
                    <td>{t_metric(k.metric_code, true)}</td>
                    <td className="font-medium">{formatKpiValue(k)}</td>
                    <td>
                      {k.target != null
                        ? (k.value_type === "ratio" ? (k.target * 100).toFixed(0) + "%" : k.target)
                        : "-"}
                    </td>
                    <td>
                      <Badge type={getKpiStatus(k)}>
                        {getKpiStatus(k) === "success" ? "达标" :
                          getKpiStatus(k) === "warning" ? "接近" :
                          getKpiStatus(k) === "danger" ? "未达标" : "无目标"}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </div>

      {role === "factory" && factoryDecisionSummary && (
        <Card title="经营决策摘要" extra={<span className="text-xs text-muted">按当前时间范围识别最需要关注的产线</span>}>
          <div className="grid grid-3 gap-3">
            {[
              ["OEE最低", factoryDecisionSummary.lowestOee, "oee", "优先查看综合效率损失"],
              ["质量率最低", factoryDecisionSummary.lowestQuality, "quality", "优先查看缺陷与冻结批次"],
              ["开动率最低", factoryDecisionSummary.lowestAvailability, "availability", "优先查看停机与维修记录"],
            ].map(([title, row, metric, action]) => (
              <div key={metric} style={{ padding: "12px", border: "1px solid var(--c-gray-200)", borderRadius: "var(--radius-sm)", background: "var(--c-gray-50)" }}>
                <div className="text-xs text-muted">{title}</div>
                <div style={{ fontSize: "20px", fontWeight: 700, marginTop: "4px" }}>{row.label}</div>
                <div style={{ color: "var(--c-danger)", fontWeight: 600 }}>{typeof row[metric] === "number" ? `${(row[metric] * 100).toFixed(1)}%` : "暂无数据"}</div>
                <div className="text-xs text-muted" style={{ marginTop: "5px" }}>{action}</div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* 4. 证据与技术信息（折叠） */}
      <Collapse
        title={
          <span className="flex items-center gap-2">
            <Icon.Database />
            证据与技术信息
          </span>
        }
        badge={<Badge type="default" dot>技术详情</Badge>}
      >
        <div className="grid grid-2 gap-3">
          <div>
            <div style={{ fontSize: "12px", fontWeight: 600, color: "var(--c-gray-600)", marginBottom: "8px" }}>
              视图元数据
            </div>
            <div className="detail-row">
              <div className="detail-label">视图编号</div>
              <div className="detail-value mono text-sm">{currentView?.view_key || "-"}</div>
            </div>
            <div className="detail-row">
              <div className="detail-label">规则版本</div>
              <div className="detail-value mono text-sm">{currentView?.rule_version || "-"}</div>
            </div>
            <div className="detail-row">
              <div className="detail-label">知识版本</div>
              <div className="detail-value mono text-sm">{currentView?.knowledge_version || "-"}</div>
            </div>
            <div className="detail-row">
              <div className="detail-label">数据时间</div>
              <div className="detail-value mono text-sm">{currentView?.time_window?.start || "-"} ~ {currentView?.time_window?.end || "-"}</div>
            </div>
          </div>
          <div>
            <div style={{ fontSize: "12px", fontWeight: 600, color: "var(--c-gray-600)", marginBottom: "8px" }}>
              证据引用
            </div>
            {(currentView?.evidence_refs || []).length > 0 ? (
              (currentView.evidence_refs || []).map((ref, i) => (
                <div key={i} className="detail-row">
                  <div className="detail-label">{`证据 ${i + 1}`}</div>
                  <div className="detail-value mono text-sm">
                    {ref.semantic_table || ref.source_table} · {ref.record_id || ref.record_key}
                  </div>
                </div>
              ))
            ) : (
              <div className="text-muted text-sm">当前视图无直接证据引用</div>
            )}
          </div>
        </div>
      </Collapse>
    </div>
  );
}

// ========== 事件中心 ==========
function businessEvidenceLabel(ref, skillId = "") {
  const tableLabels = {
    "03_工单映射_模拟": "工单映射",
    "04_订单物料_模拟": "订单与物料",
    "12_多产线班次_模拟": "产线班次",
    "13_多产线停机_模拟": "停机记录",
    "16_不良类型_模拟": "不良类型",
    "17_质量冻结明细_模拟": "质量冻结",
  };
  const evidenceIndex = BIFROST_DATA.event?.evidence_index || [];
  const item = typeof ref === "object" ? ref : evidenceIndex.find((entry) => entry.evidence_ref === ref || entry.ref === ref || entry.id === ref);
  if (!item) {
    const fallback = {
      "a01-oee-loss-tree": "生产班次与停机记录（已核验）",
      "a07-yield-funnel": "质量检测与不良记录（已核验）",
      "a08-supply-chain-gap": "采购、到货与物料记录（已核验）",
      "a02-pareto": "缺陷/停机分类记录（已核验）",
    }[skillId];
    return fallback || "当前事件已核验记录（来源已绑定）";
  }
  const table = tableLabels[item.semantic_table || item.source_table || item.source_type] || "业务记录";
  const record = item.record_id || item.record_key || item.source_object_id;
  const date = item.data_time || item.date || item.shift_date;
  return [table, record ? `记录 ${record}` : "", date ? `时间 ${date}` : ""].filter(Boolean).join(" · ");
}

function businessMetricLabel(field) {
  const labels = {
    availability: "开动率",
    availability_loss: "非计划停机影响",
    performance_rate: "性能率",
    quality_factor: "质量因子",
    defect_total: "不良数量",
    yield: "良品率",
    purchase_qty: "采购数量",
    arrived_qty: "到货数量",
  };
  return labels[field] || t_metric(field, true) || "业务指标";
}

function businessMetricValue(metric) {
  const value = metric?.value;
  if (typeof value !== "number") return value ?? "-";
  const field = String(metric.semantic_field || metric.metric_id || "");
  const ratio = metric.unit === "ratio" || metric.value_mode === "ratio" || ["availability", "performance_rate", "quality_factor", "yield"].includes(field);
  return ratio ? `${(value * 100).toFixed(1)}%` : value.toLocaleString("zh-CN");
}

function BusinessInterpretationCard({ view, role, scope, timeWindow, onNavigate }) {
  const brief = buildBusinessViewBrief(view, role, scope, timeWindow);
  if (!brief) return null;
  return (
    <Card title="业务解读与下一步" extra={<Badge type={brief.evidenceCount ? "success" : "warning"}>{brief.reliability}</Badge>}>
      <div className="text-sm text-muted" style={{ lineHeight: 1.6, marginBottom: "10px" }}>
        数据来源：{brief.sourceNature} · 当前范围：{scope === "ALL_LINES" ? "全部产线" : getLineLabel(scope, view)} · 结论只解释已核验事实，不自动认定根因。
      </div>
      <div className="grid grid-2 gap-3">
        {brief.findings.map((item) => (
          <article key={item.title} style={{ padding: "12px", border: "1px solid var(--c-gray-200)", borderRadius: "var(--radius-sm)", background: "var(--c-gray-50)" }}>
            <div style={{ fontWeight: 700, marginBottom: "6px" }}>{item.title}</div>
            <div className="text-sm" style={{ lineHeight: 1.7 }}>{item.text}</div>
            <div className="text-sm" style={{ marginTop: "8px", color: "var(--c-primary-700)" }}><strong>建议：</strong>{item.action}</div>
            {item.defects?.length > 0 && (
              <div style={{ marginTop: "8px" }}>
                {item.defects.map((defect) => (
                  <button key={defect.label} className="list-item" onClick={() => onNavigate?.("events")} style={{ width: "100%", border: 0, borderTop: "1px solid var(--c-gray-200)", background: "transparent", textAlign: "left", cursor: "pointer" }} title="进入事件中心查看班次、工单和证据">
                    <span>{defect.label}</span><span>{defect.count.toLocaleString("zh-CN")} 件 · {(defect.share * 100).toFixed(1)}%</span>
                  </button>
                ))}
              </div>
            )}
          </article>
        ))}
      </div>
      <details style={{ marginTop: "10px" }}><summary className="text-sm">数据可靠性与限制</summary><div className="text-sm text-muted" style={{ marginTop: "6px", lineHeight: 1.6 }}>{brief.limitations.join("；")}。证据引用 {brief.evidenceCount} 条。</div></details>
    </Card>
  );
}

function ReadableBusinessInterpretationCard({ view, role, scope, timeWindow, onNavigate }) {
  const brief = buildBusinessViewBrief(view, role, scope, timeWindow);
  if (!brief) return null;
  const lineText = scope === "ALL_LINES" ? "全部产线" : (getLineLabel(scope, view) || scope);
  return (
    <Card title="业务解读与下一步" extra={<Badge type={brief.evidenceCount ? "success" : "warning"}>{brief.reliability}</Badge>}>
      <div className="text-sm text-muted" style={{ lineHeight: 1.6, marginBottom: "10px" }}>
        数据来源：{brief.sourceNature} · 范围：{lineText} · 结论只解释已核验事实，不自动认定根因。
      </div>
      <div className="grid grid-2 gap-3">
        {brief.findings.map((item) => (
          <article key={item.title} style={{ padding: "12px", border: "1px solid var(--c-gray-200)", borderRadius: "var(--radius-sm)", background: "var(--c-gray-50)" }}>
            <div style={{ fontWeight: 700, marginBottom: "6px" }}>{item.title}</div>
            <div className="text-sm" style={{ lineHeight: 1.7 }}>{item.text}</div>
            {item.action && <div className="text-sm" style={{ marginTop: "8px", color: "var(--c-primary-700)" }}><strong>建议：</strong>{item.action}</div>}
            {item.defects?.length > 0 && <div style={{ marginTop: "8px" }}>{item.defects.map((defect) => (
              <button key={defect.label} className="list-item" onClick={() => onNavigate?.("events")} style={{ width: "100%", border: 0, borderTop: "1px solid var(--c-gray-200)", background: "transparent", textAlign: "left", cursor: "pointer" }} title="进入事件中心查看班次、工单和证据">
                <span>{defect.label}</span><span>{defect.count.toLocaleString("zh-CN")} 件 · {(defect.share * 100).toFixed(1)}% →</span>
              </button>
            ))}</div>}
          </article>
        ))}
      </div>
      <details style={{ marginTop: "10px" }}><summary className="text-sm">数据可靠性与限制</summary><div className="text-sm text-muted" style={{ marginTop: "6px", lineHeight: 1.6 }}>{brief.limitations.join("；")}。证据引用 {brief.evidenceCount} 条。</div></details>
    </Card>
  );
}

function FormalDerivedInsightsPanel({ role }) {
  const all = BIFROST_DATA.formal_derived_insights?.derived_insights || [];
  const allowed = {
    factory: ["a01-oee-loss-tree", "a02-pareto", "a07-yield-funnel", "a08-supply-chain-gap"],
    line: ["a01-oee-loss-tree", "a07-yield-funnel"],
    quality: ["a02-pareto", "a03-spc-rules", "a07-yield-funnel"],
    equipment: ["a01-oee-loss-tree", "a02-pareto"],
    process: ["a03-spc-rules"],
    supply: ["a08-supply-chain-gap"],
  }[role] || [];
  const insights = all.filter((item) => allowed.includes(item.skill_id) && (item.presentation_mode || "first_class_business") === "first_class_business");
  if (!insights.length) return null;
  const labels = {
    "a01-oee-loss-tree": "生产损失分解",
    "a02-pareto": "主要缺陷/停机原因及累计影响",
    "a07-yield-funnel": "良率问题定位",
    "a03-spc-rules": "工艺稳定性数据检查",
    "a08-supply-chain-gap": "物料缺口与交付影响",
  };
  return (
    <Card title="本角色分析结论" extra={<Badge type="success">已核验</Badge>}>
      <div className="grid grid-2 gap-3">
        {insights.map((item) => (
          <div key={item.insight_id} className="list-item" style={{ alignItems: "flex-start" }}>
          <div style={{ flex: 1 }}>
            {(() => {
              const detail = item.payload || item;
              const summary = item.business_summary || item.conclusion || detail.business_summary || detail.conclusion;
              const metrics = item.metrics?.length ? item.metrics : (detail.metrics || detail.supply_gap?.metrics || detail.yield_funnel?.stages || []);
              const rows = detail.oee_loss_tree ? Object.values(detail.oee_loss_tree).flat() : (detail.pareto?.items || detail.yield_funnel?.stages || detail.supply_gap?.metrics || []);
              return <>
                <strong>{labels[item.skill_id] || item.title_zh || "专业分析"}</strong>
            <div className="text-sm text-muted" style={{ marginTop: "4px" }}>基于当前数据范围和可追溯证据生成，作为本角色的正式分析结论。</div>
            {summary && <div style={{ marginTop: "8px", color: "var(--c-gray-800)", lineHeight: 1.6 }}><strong>结论：</strong>{summary}</div>}
            {Array.isArray(metrics) && metrics.length > 0 && <div style={{ marginTop: "8px" }}><strong className="text-sm">关键指标</strong>{metrics.slice(0, 4).map((metric, index) => <div className="list-item" key={`metric-${index}`}><span>{metric.category || metric.label || businessMetricLabel(metric.semantic_field || metric.metric_id)}</span><span>{businessMetricValue(metric)}</span></div>)}</div>}
            {Array.isArray(rows) && rows.length > 0 && <div style={{ marginTop: "8px" }}><strong className="text-sm">分析明细</strong>{rows.slice(0, 5).map((row, index) => <div className="list-item" key={`detail-${index}`}><span>{row.category || row.label || businessMetricLabel(row.semantic_field) || "关联项"}</span><span>{row.statement || businessMetricValue(row)}</span></div>)}</div>}
            {(item.evidence_refs || []).length > 0 && <div style={{ marginTop: "8px" }}><strong className="text-sm">依据（{item.evidence_refs.length} 条业务记录）</strong><ul className="text-sm" style={{ margin: "6px 0", paddingLeft: "18px" }}>{item.evidence_refs.slice(0, 3).map((ref, index) => <li key={index}>{businessEvidenceLabel(ref, item.skill_id)}</li>)}</ul></div>}
            <details className="text-xs" style={{ marginTop: "6px" }}><summary>查看技术证据索引</summary><div className="mono" style={{ marginTop: "4px", wordBreak: "break-all" }}>{(item.evidence_refs || []).join("\n")}</div></details>
              </>;
            })()}
          </div>
            <Badge type="success">正式结论</Badge>
          </div>
        ))}
      </div>
    </Card>
  );
}

function PeerOverlayPanel({ role }) {
  if (BIFROST_DATA.runtime_mode !== "adapter-test") return null;
  // Once validated derived insights are attached to the main payload, do not
  // show the lower-level adapter overlay as a competing business result.
  if (BIFROST_DATA.formal_derived_insights?.formal_integration_status === "attached_additive") return null;
  if (!BIFROST_DATA.peer_overlay) {
    const technicalReason = BIFROST_DATA.peer_overlay_error || "overlay_validation_failed";
    const readableReason = {
      manifest_source_sha_missing: "辅助分析的来源校验信息尚未配置，当前结果已安全隐藏。",
      manifest_payload_hash_unverified: "辅助分析载荷尚未完成完整性校验，当前结果已安全隐藏。",
      manifest_payload_hash_mismatch: "辅助分析载荷完整性校验未通过，当前结果已安全隐藏。",
      event_id_mismatch: "辅助分析与当前事件不一致，当前结果已安全隐藏。",
      dataset_id_not_adapter_test: "辅助分析不属于当前演示数据，当前结果已安全隐藏。",
    }[technicalReason] || "辅助分析暂不可用，正式指标不受影响。";
    return (
      <section className="peer-overlay-panel is-blocked" aria-label="Peer overlay isolated">
        <div className="peer-overlay-title">辅助分析暂不可用</div>
        <div className="peer-overlay-muted">只读兼容分析未通过当前事件、数据源、源哈希或载荷边界校验，已安全隐藏，不影响主看板。</div>
        <div className="peer-overlay-muted">{readableReason}正式看板、主指标和决策不受影响。</div>
        <details className="peer-overlay-details"><summary>查看技术校验说明</summary><div className="mono text-xs text-muted">{technicalReason}</div></details>
      </section>
    );
  }
  const overlay = BIFROST_DATA.peer_overlay;
  const enhancements = BIFROST_DATA.peer_enhancements || [];
  const label = {
    "a01-oee-loss-tree": "\u004f\u0045\u0045\u635f\u5931\u5206\u89e3",
    "a02-pareto": "\u4e3b\u8981\u539f\u56e0\u6392\u5e8f\uff08Pareto\uff09",
    "a07-yield-funnel": "\u826f\u7387\u95ee\u9898\u5b9a\u4f4d",
    "a03-spc-rules": "\u5de5\u827a\u7a33\u5b9a\u6027\u6570\u636e\u68c0\u67e5\uff08SPC\uff09",
    "a08-supply-chain-gap": "\u7269\u6599\u7f3a\u53e3\u5f71\u54cd",
  };
  const roleLabels = { factory: "厂长", line: "线长", quality: "质量", equipment: "设备", process: "工艺", supply: "供应链" };
  const roleAliases = { factory: ["factory", "\u5382\u957f"], line: ["line", "\u7ebf\u957f"], quality: ["quality", "\u8d28\u91cf"], equipment: ["equipment", "\u8bbe\u5907"], process: ["process", "\u5de5\u827a"], supply: ["supply", "\u4f9b\u5e94\u94fe"] };
  const projection = (roleAliases[role] || [role]).map((key) => BIFROST_DATA.peer_role_projections?.[key]).find(Boolean);
  const projectedSkills = projection?.allowed_skill_ids || [];
  const projectedStatus = Object.fromEntries((projection?.skill_outputs || []).map((item) => [item.skill_id, item.status]));
  const visibleEnhancements = enhancements
    .filter((item) => projectedSkills.includes(item.skill_id))
    .map((item) => ({ ...item, status: projectedStatus[item.skill_id] || item.status }));
  const statusText = { available: "可用", not_observed: "未观察到", blocked: "暂不可判定" };
  const missingLabels = {
    sample_rule: "抽样规则",
    spc_measurement_points: "SPC测量点",
    usl: "规格上限（USL）",
    lsl: "规格下限（LSL）",
    mtbf_mttr: "设备故障与维修记录",
    shift_trend: "班次趋势",
  };
  const formatMissing = (fields) => (fields || []).map((field) => missingLabels[field] || field).join("、");
  return (
    <section className="peer-overlay-panel" aria-label="辅助分析只读预览">
      <div className="peer-overlay-header">
        <div><div className="peer-overlay-title">{roleLabels[role] || "当前角色"} · 辅助分析</div><div className="peer-overlay-subtitle">仅用于兼容性验证，补充只读诊断，不改变原始指标和正式载荷，也不替代正式决策</div></div>
        <span className="peer-overlay-badge">只读预览</span>
      </div>
      <div className="peer-overlay-grid">
        {visibleEnhancements.map((item, index) => {
          const itemLabel = label[item.skill_id] || item.skill_id;
          const blocked = item.status === "blocked";
          const hasPhysicalEvidence = (item.physical_evidence_refs || []).length > 0 || item.evidence_provenance === "physical_record";
          const rows = item.branches || item.items || item.stages || [];
          return (
            <article className={`peer-overlay-card ${blocked ? "is-blocked" : ""}`} key={`${item.skill_id}-${index}`}>
              <div className="flex items-center justify-between"><div className="peer-overlay-card-title">{itemLabel}</div><span className={`peer-skill-status ${blocked ? "blocked" : hasPhysicalEvidence ? (item.status || "default") : "not_observed"}`}>{blocked ? "暂不可判定" : hasPhysicalEvidence ? (statusText[item.status] || item.status || "未知") : "建议，待绑定证据"}</span></div>
              <div className="peer-overlay-card-status">分析范围：当前事件 · 当前角色</div>
              {blocked ? <div className="peer-overlay-muted">缺少：{formatMissing(item.missing_fields || item.data_gaps) || "必要输入"}。暂不判断工艺稳定性；不计算 Cpk，不宣称过程失控。</div> : rows.length > 0 ? <ul className="peer-overlay-list">{rows.slice(0, 4).map((row, rowIndex) => <li key={rowIndex}><span>{row.category || row.label || row.field || "分析项"}</span><span>{row.statement || row.value || "已绑定证据"}</span></li>)}</ul> : <div className="peer-overlay-muted">当前输入中没有足够的分类字段，未生成可判定结果。</div>}
              {!blocked && !hasPhysicalEvidence && <div className="peer-overlay-muted">当前结果来自辅助分析输入，尚未绑定到本项目的物理表、班次或停机记录；只能作为排查建议，不能作为正式结论。</div>}
              {item.skill_id === "a08-supply-chain-gap" && <div className="peer-overlay-note">供应链缺口单独展示，不作为 OEE 原因。</div>}
              {item.evidence_refs?.length > 0 && <details className="peer-overlay-details"><summary>辅助分析引用（{item.evidence_refs.length}）</summary><div className="peer-evidence-warning">这些引用仅用于兼容性验证，尚未绑定本项目物理表记录，不进入正式结论。</div><div className="mono peer-evidence-list">{item.evidence_refs.slice(0, 3).join("\n")}{item.evidence_refs.length > 3 ? `\n…其余 ${item.evidence_refs.length - 3} 条` : ""}</div></details>}
            </article>
          );
        })}
      </div>
      <details className="peer-overlay-details peer-overlay-gaps"><summary>辅助分析模块说明</summary><div>这些辅助分析用于损失分解、主要原因排序、良率问题定位、工艺稳定性数据检查和供应缺口分析。它们只补充正式指标，不替代 OEE、良率或正式决策；只有绑定到当前数据源的物理记录后，结果才可进入正式结论。</div></details>
    </section>
  );
}

function EventsPage({ role, setRole, timeWindow, setTimeWindow, scope, setScope, selectedEventId, onEventChange, onAskAI }) {
  const [searchQuery, setSearchQuery] = useState("");
  const goldenEvent = getGoldenEvent();
  const eventSummaries = getEventSummaries();

  // Keep the selected event in App state so the AI drawer receives exactly
  // the event currently shown, without a second hardcoded context id.
  useEffect(() => {
    if (selectedEventId) return;
    const initialEventId = goldenEvent?.event_id || eventSummaries[0]?.event_id;
    if (initialEventId) onEventChange(initialEventId);
  }, [selectedEventId, goldenEvent?.event_id, eventSummaries, onEventChange]);

  const isReadonly = useMemo(() => {
    const s = getSourceStatus();
    return s?.connection_mode?.writeback_mode === "readonly";
  }, []);

  const scopedEvents = useMemo(() => {
    if (role === "factory") return eventSummaries;
    const allowedLines = getAllowedLinesForRole(role);
    const effectiveScope = resolveScopeForRole(role, scope);
    return eventSummaries.filter((event) => {
      if (event.line_id && !allowedLines.includes(event.line_id)) return false;
      return effectiveScope === "ALL_LINES" || !event.line_id || event.line_id === effectiveScope;
    });
  }, [eventSummaries, role, scope]);

  // P0-4 搜索过滤：按事件编号、产线、标题
  const filteredEvents = useMemo(() => {
    if (!searchQuery.trim()) return scopedEvents;
    const q = searchQuery.toLowerCase();
    return scopedEvents.filter((e) =>
      e.event_id?.toLowerCase().includes(q) ||
      e.line_id?.toLowerCase().includes(q) ||
      e.headline?.toLowerCase().includes(q) ||
      e.alert_type?.toLowerCase().includes(q) ||
      (t_line(e.line_id) || "").toLowerCase().includes(q)
    );
  }, [scopedEvents, searchQuery]);

  // 当前选中事件的摘要
  const selectedSummary = useMemo(() => {
    return filteredEvents.find((e) => e.event_id === selectedEventId) || null;
  }, [selectedEventId, filteredEvents]);

  useEffect(() => {
    if (selectedEventId && filteredEvents.some((event) => event.event_id === selectedEventId)) return;
    const nextEvent = filteredEvents[0]?.event_id || null;
    if (nextEvent !== selectedEventId) onEventChange(nextEvent);
  }, [filteredEvents, selectedEventId, onEventChange]);

  // 是否黄金事件（有完整 payload）
  const isGoldenEvent = selectedEventId === goldenEvent?.event_id;

  // 黄金事件的角色切片
  const eventLineIds = goldenEvent?.line_ids || goldenEvent?.roles?.flatMap((r) => r.line_ids || r.scope?.line_ids || []) || [];
  const scopeMatchesEvent = scope === "ALL_LINES" || eventLineIds.length === 0 || eventLineIds.includes(scope);
  const currentRoleSlice = isGoldenEvent && goldenEvent && scopeMatchesEvent
    ? goldenEvent.roles?.find((r) => {
        if (r.role !== role) return false;
        const sliceLines = r.line_ids || r.scope?.line_ids || [];
        return scope === "ALL_LINES" || sliceLines.length === 0 || sliceLines.includes(scope);
      }) || null
    : null;

  // 黄金事件物化数据
  const mat = isGoldenEvent ? getMaterialization() : null;
  const validation = isGoldenEvent ? getValidationResults() : null;
  const ctrlRefs = isGoldenEvent ? getControlTableRefs() : null;
  const eventFacts = isGoldenEvent ? getEventFacts() : null;
  const formatEventGap = (gap) => {
    const key = typeof gap === "string" ? gap : gap?.metric || gap?.field || gap?.code || "";
    const labels = {
      missing_equipment_fault_repair_evidence: "设备故障与维修记录",
      insufficient_temporal_evidence: "连续班次趋势证据",
      mtbf_mttr: "设备故障与维修记录",
      shift_trend: "连续班次趋势",
      sample_rule: "抽样规则",
      spc_measurement_points: "SPC测量点",
      categorical_cause_values: "不良/停机原因分类",
    };
    return gap?.label || gap?.description || labels[key] || key || "待补充数据";
  };

  // OEE 三因子分解（基于真实 OEE / AVAILABILITY / PERFORMANCE / QUALITY）
  const oeeFactorOption = useMemo(() => {
    if (!isGoldenEvent || !currentRoleSlice) return null;
    const kpis = currentRoleSlice.kpis || [];
    const oee = kpis.find((k) => k.metric_code === "OEE");
    const avail = kpis.find((k) => k.metric_code === "AVAILABILITY");
    const perf = kpis.find((k) => k.metric_code === "PERFORMANCE");
    const qual = kpis.find((k) => k.metric_code === "QUALITY");
    if (!oee) return null;

    const factors = [
      { name: "开动率", value: avail ? avail.value : null },
      { name: "性能率", value: perf ? perf.value : null },
      { name: "良品率", value: qual ? qual.value : null },
    ].filter((f) => f.value !== null);

    if (factors.length === 0) return null;

    return {
      grid: { top: 20, right: 24, bottom: 28, left: 60 },
      tooltip: {
        trigger: "axis",
        valueFormatter: (v) => (v * 100).toFixed(1) + "%",
      },
      xAxis: {
        type: "value",
        max: 100,
        axisLabel: { fontSize: 11, color: "#8a95a6", formatter: "{value}%" },
        splitLine: { lineStyle: { color: "#eef4fb" } },
      },
      yAxis: {
        type: "category",
        data: factors.map((f) => f.name),
        axisLabel: { fontSize: 12, color: "#4a5568" },
        axisLine: { lineStyle: { color: "#e5e9ef" } },
      },
      series: [{
        type: "bar",
        data: factors.map((f) => +(f.value * 100).toFixed(1)),
        barWidth: 22,
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
  }, [isGoldenEvent, currentRoleSlice]);

  // 审计轨迹时间线（来自真实 audit_trail）
  const timelineItems = useMemo(() => {
    if (!isGoldenEvent || !goldenEvent?.audit_trail) return [];
    const at = goldenEvent.audit_trail;
    const items = [];
    if (at.correction_run) {
      items.push({
        title: `纠偏运行 ${at.correction_run.run_id || ""}`,
        meta: at.correction_run.timestamp || "",
        desc: at.correction_run.description || "",
        active: true,
      });
    }
    if (at.previous_analysis) {
      const err = at.previous_analysis.errors_corrected || [];
      items.push({
        title: `上一版分析（${at.previous_analysis.status || ""}）`,
        meta: `被 ${at.previous_analysis.superseded_by_run_id || ""} 替代`,
        desc: err.length > 0
          ? `纠偏项：${err.slice(0, 2).join("；")}${err.length > 2 ? "等 " + err.length + " 项" : ""}`
          : "",
      });
    }
    return items;
  }, [isGoldenEvent, goldenEvent]);

  return (
    <div className="page-content">
      <div className="grid" style={{ gridTemplateColumns: "280px 1fr", gap: "16px" }}>
        {/* 左侧事件列表 */}
        <Card title="事件列表" bodyClassName="p-0">
          <div style={{ padding: "12px" }}>
            <div style={{
              position: "relative",
              marginBottom: "10px",
            }}>
              <Icon.Search style={{ position: "absolute", left: "8px", top: "50%", transform: "translateY(-50%)", color: "var(--c-gray-400)" }} />
              <input
                placeholder="搜索事件..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{
                  width: "100%",
                  padding: "7px 10px 7px 30px",
                  border: "1px solid var(--c-gray-300)",
                  borderRadius: "var(--radius-sm)",
                  fontSize: "12px",
                  outline: "none",
                }}
              />
            </div>
          </div>
          <div style={{ maxHeight: "calc(100vh - 280px)", overflowY: "auto" }}>
            {filteredEvents.length === 0 ? (
              <div className="empty-state">未找到匹配的事件</div>
            ) : (
              filteredEvents.map((evt) => (
              <div
                key={evt.event_id}
                onClick={() => onEventChange(evt.event_id)}
                style={{
                  padding: "12px 16px",
                  cursor: "pointer",
                  borderBottom: "1px solid var(--c-gray-100)",
                  background: selectedEventId === evt.event_id ? "var(--c-primary-50)" : "#fff",
                  borderLeft: selectedEventId === evt.event_id ? "3px solid var(--c-primary-500)" : "3px solid transparent",
                  transition: "all 0.15s",
                }}
              >
                <div className="flex items-center gap-2 mb-2">
                  <Badge type={evt.severity === "critical" || evt.severity === "high" ? "danger" : "warning"}>
                    {t_severity(evt.severity)}
                  </Badge>
                  <span className="mono text-xs text-muted">{evt.event_id}</span>
                </div>
                <div style={{ fontSize: "13px", fontWeight: 500, color: "var(--c-gray-900)", lineHeight: 1.4 }}>
                  {evt.headline || t_alertType(evt.alert_type)}
                </div>
                <div style={{ fontSize: "11px", color: "var(--c-gray-500)", marginTop: "6px" }}>
                  {t_line(evt.line_id)} · {evt.date}
                </div>
                <div style={{ marginTop: "6px" }}>
                  <Badge type={evt.status === "待确认" ? "warning" : "info"} dot>
                    {evt.status}
                  </Badge>
                  {evt.confirmations_pending > 0 && (
                    <span style={{ marginLeft: "8px", fontSize: "11px", color: "var(--c-warning)" }}>
                      {evt.confirmations_pending} 项待确认
                    </span>
                  )}
                </div>
              </div>
            ))
            )}
          </div>
        </Card>

        {/* 右侧事件详情 */}
        <div className="flex flex-col gap-4">
          {/* 事件头部 */}
          <Card
            title={
              <div>
                <div className="flex items-center gap-3">
                  <Badge type={selectedSummary?.severity === "critical" || selectedSummary?.severity === "high" ? "danger" : "warning"}>
                    {t_severity(selectedSummary?.severity)}
                  </Badge>
                  <span style={{ fontSize: "16px", fontWeight: 600 }}>
                    {selectedEventId} · {selectedSummary?.headline || t_alertType(selectedSummary?.alert_type) || "事件详情"}
                  </span>
                  {!isGoldenEvent && (
                    <Badge type="default" dot>仅有摘要，尚无详情载荷</Badge>
                  )}
                </div>
                <div style={{ fontSize: "12px", color: "var(--c-gray-500)", marginTop: "4px" }}>
                  {selectedSummary?.date || goldenEvent?.data_time || "-"} · 
                  {t_line(selectedSummary?.line_id || (goldenEvent?.line_ids?.[0]))} · 
                  {isGoldenEvent ? `分析版本 ${goldenEvent?.analysis_version}` : "摘要视图"}
                </div>
              </div>
            }
            extra={
              <div className="flex gap-2">
                <button className="btn btn-default btn-sm" onClick={onAskAI}>
                  <Icon.AI /> 问 AI
                </button>
                <button
                  className="btn btn-accent btn-sm"
                  disabled={isReadonly || !isGoldenEvent}
                  title={isReadonly ? "当前为只读模式，暂不能提交" : (!isGoldenEvent ? "无详情载荷，无法处置" : "")}
                >
                  确认处置
                </button>
              </div>
            }
          >
            <div className="grid grid-kpi">
              <KpiCard
                label="事件状态"
                value={selectedSummary?.status || goldenEvent?.event_status || "-"}
                status="warning"
                size="sm"
              />
              <KpiCard
                label="OEE"
                value={isGoldenEvent && mat?.oee_recompute != null ? (mat.oee_recompute * 100).toFixed(1) + "%" : "-"}
                status="danger"
                size="sm"
                subLabel={isGoldenEvent && eventFacts?.oee_gap_pct_abs != null
                  ? `低于目标 ${eventFacts.oee_gap_pct_abs} 个百分点`
                  : ""}
              />
              <KpiCard
                label="不良数"
                value={isGoldenEvent && mat?.defect_total != null
                  ? mat.defect_total.toLocaleString("zh-CN") + " 件"
                  : "-"}
                status="danger"
                size="sm"
              />
              <KpiCard
                label="待确认项"
                value={validation?.pending_confirmation_count ?? (selectedSummary?.confirmations_pending || 0)}
                status="warning"
                size="sm"
              />
            </div>
            {isGoldenEvent && (
              <div className="grid grid-kpi mt-3" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
                <KpiCard
                  label="停机事件"
                  value={eventFacts?.downtime_count != null
                    ? eventFacts.downtime_count + " 条"
                    : "-"}
                  status="danger"
                  size="sm"
                  subLabel={eventFacts?.downtime_total_minutes != null
                    ? `累计 ${eventFacts.downtime_total_minutes} min`
                    : ""}
                />
                <KpiCard
                  label="非计划停机"
                  value={eventFacts?.unplanned_downtime_minutes != null
                    ? eventFacts.unplanned_downtime_minutes + " 分钟"
                    : "-"}
                  status="danger"
                  size="sm"
                  subLabel="含 10 条非计划停"
                />
                <KpiCard
                  label="质量冻结"
                  value={eventFacts?.freeze_id || "-"}
                  status="warning"
                  size="sm"
                  subLabel={eventFacts?.material_freeze_qty != null
                    ? `冻结 ${eventFacts.material_freeze_qty} 件 ${eventFacts.freeze_status || ""}`
                    : ""}
                />
              </div>
            )}
          </Card>

          {/* 角色切换 Tabs */}
          <Card
            title="各角色视角"
            extra={
              <div className="segmented">
                {getAllRoles().map((r) => (
                  <button
                    key={r}
                    className={`segmented-item ${role === r ? "active" : ""}`}
                    onClick={() => setRole(r)}
                  >
                    {t_roles(r)}
                  </button>
                ))}
              </div>
            }
          >
            <div style={{ fontSize: "13px", lineHeight: 1.7 }}>
              {currentRoleSlice ? (
                <>
                  <div style={{ marginBottom: "10px", fontSize: "14px", fontWeight: 600 }}>
                    {currentRoleSlice.headline}
                  </div>
                  <div className="grid grid-2 gap-3" style={{ marginTop: "14px" }}>
                    {(currentRoleSlice.kpis || []).slice(0, 8).map((k, kIndex) => (
                      <KpiCard
                        key={`${k.metric_code || "metric"}-${k.line_id || kIndex}`}
                        label={`${t_metric(k.metric_code)}${k.line_id ? ` · ${t_line(k.line_id)}` : ""}`}
                        value={formatKpiValue(k)}
                        status={getKpiStatus(k)}
                        size="sm"
                      />
                    ))}
                  </div>
                  {(currentRoleSlice.findings || []).length > 0 && (
                    <div style={{ marginTop: "16px", padding: "12px 14px", borderRadius: "var(--radius-sm)", background: "var(--c-success-50)", border: "1px solid var(--c-success-200)" }}>
                      <div style={{ fontWeight: 700, marginBottom: "8px" }}>本角色已核验结论</div>
                      {(currentRoleSlice.findings || []).slice(0, 6).map((finding, i) => (
                        <div key={finding.insight_id || i} className="list-item" style={{ alignItems: "flex-start" }}>
                          <Badge type="success">已核验</Badge>
                          <div style={{ flex: 1 }}>
                            <div style={{ fontWeight: 600 }}>{finding.title_zh || "分析结论"}</div>
                            <div className="text-sm" style={{ marginTop: "4px" }}>{finding.summary || "已形成可供当前角色参考的分析结论"}</div>
                            {finding.requires_human_confirmation && <div className="text-xs text-muted" style={{ marginTop: "4px" }}>后续动作仍需人工确认</div>}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                  {(currentRoleSlice.tasks || []).length > 0 && (
                    <div style={{ marginTop: "14px" }}>
                      <div style={{ fontWeight: 600, marginBottom: "8px" }}>关联任务</div>
                      {(currentRoleSlice.tasks || []).map((t, i) => (
                        <div key={i} className="list-item">
                          <Badge type="warning">{t.status || "待处理"}</Badge>
                          <div style={{ flex: 1 }}>{t.title || `任务 ${i + 1}`}</div>
                        </div>
                      ))}
                    </div>
                  )}
                  {(currentRoleSlice.alerts || []).length > 0 && (
                    <div style={{ marginTop: "14px" }}>
                      <div style={{ fontWeight: 600, marginBottom: "8px" }}>当前异常与影响</div>
                      {(currentRoleSlice.alerts || []).slice(0, 5).map((alert, i) => (
                        <div key={i} className="list-item">
                          <Badge type={alert.severity === "critical" || alert.severity === "high" ? "danger" : "warning"}>
                            {t_severity(alert.severity || "medium")}
                          </Badge>
                          <div style={{ flex: 1 }}>
                            <div>{alert.title || alert.headline || alert.message || "发现一项异常"}</div>
                            {(alert.impact || alert.affected_objects) && <div className="text-xs text-muted">影响：{alert.impact || (Array.isArray(alert.affected_objects) ? alert.affected_objects.join("、") : alert.affected_objects)}</div>}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                  {(currentRoleSlice.decisions_required || []).length > 0 && (
                    <div style={{ marginTop: "14px" }}>
                      <div style={{ fontWeight: 600, marginBottom: "8px" }}>待确认决策</div>
                      {(currentRoleSlice.decisions_required || []).map((decision, i) => (
                        <div key={i} className="list-item">
                          <Badge type="warning">需人工确认</Badge>
                          <div style={{ flex: 1 }}>{decision.title || decision.action || decision.description || `决策事项 ${i + 1}`}</div>
                        </div>
                      ))}
                    </div>
                  )}
                  {(currentRoleSlice.data_gaps || []).length > 0 && (
                    <div style={{ marginTop: "14px", padding: "10px 12px", borderRadius: "var(--radius-sm)", background: "var(--c-warning-50)", color: "var(--c-warning-800)" }}>
                      <strong>数据缺口：</strong>
                      {(currentRoleSlice.data_gaps || []).slice(0, 4).map(formatEventGap).join("；")}
                      <div className="text-xs" style={{ marginTop: "4px" }}>数据缺口会限制归因或判定，不代表该项已经异常。</div>
                    </div>
                  )}
                </>
              ) : (
                <div className="text-muted">无该角色的事件切片数据</div>
              )}
            </div>
          </Card>

          {/* 审计轨迹 + 验证契约 */}
          <div className="grid grid-2">
            <Card title="审计轨迹">
              {timelineItems.length > 0 ? (
                <EventTimeline items={timelineItems} />
              ) : (
                <div className="empty-state">
                  {isGoldenEvent ? "当前数据合同未提供因果链详情" : "仅有摘要，尚无详情载荷"}
                </div>
              )}
            </Card>

            <Card
              title="验证契约"
              extra={
                validation ? (
                  <Badge type={validation.all_passed ? "success" : "warning"} dot>
                    {validation.all_passed ? "全部通过" : `${validation.rules?.length || 0} 条规则`}
                  </Badge>
                ) : (
                  <Badge type="default" dot>暂无</Badge>
                )
              }
            >
              <div style={{ fontSize: "12px" }}>
                {validation?.rules ? (
                  validation.rules.slice(0, 5).map((rule, i) => (
                    <div key={rule.rule_id || i} className="list-item">
                      <Badge type={rule.passed ? "success" : "danger"} dot>
                        {rule.passed ? "通过" : "未通过"}
                      </Badge>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: "12px", fontWeight: 500 }}>
                          {rule.rule_id || `规则 ${i + 1}`}
                        </div>
                        <div style={{ fontSize: "11px", color: "var(--c-gray-500)", marginTop: "2px" }}>
                          {rule.detail || rule.description || ""}
                        </div>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="empty-state">
                    {isGoldenEvent ? "当前数据合同未提供验证契约" : "仅有摘要，尚无详情载荷"}
                  </div>
                )}
              </div>
            </Card>
          </div>

          {/* OEE 三因子分解 */}
          <Card title="OEE 三因子分解">
            {oeeFactorOption ? (
              <EChart option={oeeFactorOption} className="chart-wrap" />
            ) : (
              <div className="empty-state">
                {isGoldenEvent
                  ? "当前数据合同未提供完整三因子数据"
                  : "仅有摘要，尚无详情载荷"}
              </div>
            )}
          </Card>

          {/* 物料缺口（仅黄金事件 & 有数据时显示） */}
          {isGoldenEvent && mat?.material_results && mat.material_results.length > 0 && (
            <Card
              title="物料缺口"
              extra={<Badge type="danger" dot>{mat.material_results.filter((m) => (m["缺口"] || 0) > 0).length} 项缺料</Badge>}
            >
              <table className="data-table">
                <thead>
                  <tr>
                    <th>物料/业务键</th>
                    <th>需求量</th>
                    <th>可用量</th>
                    <th>缺口</th>
                    <th>冻结</th>
                  </tr>
                </thead>
                <tbody>
                  {mat.material_results.map((m, i) => (
                    <tr key={i}>
                      <td className="mono text-sm">{m.business_key || "-"}</td>
                      <td>{m["需求量"]?.toLocaleString("zh-CN") || "-"}</td>
                      <td>{m["可用量"]?.toLocaleString("zh-CN") || "-"}</td>
                      <td>
                        {(m["缺口"] || 0) > 0 && (
                          <Badge type="danger">缺 {(m["缺口"] || 0).toLocaleString("zh-CN")} 件</Badge>
                        )}
                        {(m["缺口"] || 0) === 0 && <Badge type="success">齐套</Badge>}
                      </td>
                      <td>{m["冻结"]?.toLocaleString("zh-CN") || 0}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}

          {/* 技术详情（折叠）— 仅黄金事件显示 */}
          {isGoldenEvent && (
            <Collapse
              title={
                <span className="flex items-center gap-2">
                  <Icon.Database />
                  技术详情
                </span>
              }
              badge={<Badge type="default" dot>EvidenceRef · 控制表</Badge>}
            >
              <div className="grid grid-2 gap-3">
                <div>
                  <div style={{ fontSize: "12px", fontWeight: 600, color: "var(--c-gray-600)", marginBottom: "8px" }}>
                    控制表引用
                  </div>
                  {ctrlRefs && Object.entries(ctrlRefs).map(([key, val]) => (
                    <div key={key} className="detail-row">
                      <div className="detail-label">{key}</div>
                      <div className="detail-value mono text-sm">
                        {typeof val === "object"
                          ? (val.table_id ? val.table_id + " · " : "") + (val.record_id || Object.keys(val).length + " 项")
                          : String(val)}
                      </div>
                    </div>
                  ))}
                </div>
                <div>
                  <div style={{ fontSize: "12px", fontWeight: 600, color: "var(--c-gray-600)", marginBottom: "8px" }}>
                    物化结果
                  </div>
                  {mat && Object.entries(mat).slice(0, 6).map(([key, val]) => (
                    <div key={key} className="detail-row">
                      <div className="detail-label">
                        {{ oee_recompute: "OEE 复算", good_output: "合格品", yield_recompute: "良率复算",
                          defect_total: "不良总数", oee_gap: "OEE 差距", risk_level: "风险等级" }[key] || key}
                      </div>
                      <div className="detail-value mono text-sm">
                        {typeof val === "object"
                          ? JSON.stringify(val).slice(0, 40)
                          : key.includes("oee") || key === "yield_recompute"
                            ? (val * 100).toFixed(1) + "%"
                            : typeof val === "number" ? val.toLocaleString("zh-CN") : String(val)}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </Collapse>
          )}
        </div>
      </div>
    </div>
  );
}

// ========== 数据治理页 ==========
function GovernancePage() {
  const dq = getDataQuality();
  const [activeDefect, setActiveDefect] = useState(null);
  const [activeIssue, setActiveIssue] = useState(null);
  const [governanceDraft, setGovernanceDraft] = useState(null);
  const [governanceDraftError, setGovernanceDraftError] = useState("");

  const isReadonly = useMemo(() => {
    const s = getSourceStatus();
    return s?.connection_mode?.writeback_mode === "readonly";
  }, []);

  const defectTypes = dq?.enterprise_defect_types || [];
  const compatibilityIssues = dq?.issues || [];
  const normalizeIssueStatus = (issue) => String(issue?.status || issue?.state || "").trim().toLowerCase();
  const isResolvedIssue = (issue) => {
    const status = normalizeIssueStatus(issue);
    return /^(resolved|completed|passed|fixed|closed)$/.test(status) || /已(完成|解决|通过|标注|修复)/.test(status);
  };
  const unresolvedIssues = compatibilityIssues.filter((issue) => {
    return !isResolvedIssue(issue);
  });
  const activeDatasetId = BIFROST_DATA.overview?.dataset_id || "";
  const isOfficialDataset = activeDatasetId === "GOERTEK_OFFICIAL_SIMULATION";
  const issueCategoryLabel = (category) => t_defect(category) || category || "未分类";
  const issueRuleLabel = (category) => BIFROST_I18N.defectRuleDescriptions?.[category] || "尚未配置检测规则";
  const issueStatusType = (issue) => {
    if (isResolvedIssue(issue)) return "success";
    const status = normalizeIssueStatus(issue);
    return /^(open|待处理|pending|needs_confirmation)$/.test(status) ? "danger" : "warning";
  };
  const issueStatusLabel = (issue) => {
    if (isResolvedIssue(issue)) return "已完成";
    const status = normalizeIssueStatus(issue);
    if (/^(open|待处理|pending|needs_confirmation)$/.test(status)) return "待处理";
    return issue?.status || issue?.state || "待确认";
  };
  const healthScore = dq?.health_score || 0;
  const healthDisplay = dq?.health_score_display || "-";
  const testedDefectCount = defectTypes.filter((item) => item.status && item.status !== "not_tested").length;
  const healthComplete = defectTypes.length >= 6 && testedDefectCount >= 6;
  const healthStatus = !healthComplete ? "检测不完整" : healthScore >= 90 ? "正常" : healthScore >= 70 ? "需要关注" : "需要处理";
  const healthStatusType = !healthComplete ? "warning" : healthScore >= 90 ? "success" : healthScore >= 70 ? "warning" : "danger";
  const lastCheckedAt = dq?.last_checked_at || dq?.checked_at || dq?.metadata?.last_checked_at || "时间未提供";

  const getDefectStatus = (status) => {
    if (status === "not_tested") return "default";
    if (status === "detected") return "warning";
    if (status === "tested_no_anomaly") return "success";
    if (status === "open") return "danger";
    if (status === "resolved") return "success";
    return "default";
  };

  const getDefectStatusLabel = (status) => {
    if (status === "not_tested") return "未检测";
    if (status === "open") return "未解决";
    if (status === "resolved") return "已修复";
    return status || "-";
  };

  // 健康度环形图
  const healthOption = useMemo(() => ({
    series: [{
      type: "gauge",
      startAngle: 210,
      endAngle: -30,
      min: 0,
      max: 100,
      radius: "85%",
      center: ["50%", "60%"],
      progress: { show: true, width: 14, itemStyle: { color: healthScore >= 90 ? "#2e7d52" : healthScore >= 70 ? "#d89000" : "#c0392b" } },
      axisLine: { lineStyle: { width: 14, color: [[1, "#eef4fb"]] } },
      pointer: { show: false },
      axisTick: { show: false },
      splitLine: { show: false },
      axisLabel: { show: false },
      anchor: { show: false },
      title: { show: false },
      detail: {
        valueAnimation: true,
        fontSize: 32,
        fontWeight: 700,
        offsetCenter: [0, "5%"],
        color: "var(--c-gray-900)",
        formatter: `{value}`,
      },
      data: [{ value: healthScore }],
    }],
  }), [healthScore]);

  return (
    <div className="page-content">
      {/* 首屏数据健康度 */}
      <div className="grid grid-3 mb-4">
        <Card>
          <div className="flex items-center gap-4">
            <div style={{ width: "130px", height: "110px", flexShrink: 0 }}>
              <EChart option={healthOption} style={{ height: "110px" }} />
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: "13px", color: "var(--c-gray-500)", marginBottom: "4px" }}>数据接入健康度（兼容性评分）</div>
              <div style={{ fontSize: "28px", fontWeight: 700, color: "var(--c-gray-900)" }}>{healthDisplay}</div>
              <div style={{ fontSize: "12px", color: "var(--c-gray-500)", marginTop: "4px" }}>
                官方六类缺陷检测 · 已检测 {testedDefectCount}/6
              </div>
              <div style={{ marginTop: "8px" }}>
                <Badge type={healthStatusType}>{healthStatus}</Badge>
              </div>
            </div>
          </div>
        </Card>

        <Card>
          <div style={{ fontSize: "13px", color: "var(--c-gray-500)", marginBottom: "8px" }}>最近检测时间</div>
          <div style={{ fontSize: "18px", fontWeight: 600, color: "var(--c-gray-900)" }}>
            {lastCheckedAt}
          </div>
          <div style={{ fontSize: "12px", color: "var(--c-gray-500)", marginTop: "2px" }}>
            每日自动检测
          </div>

          <div style={{ marginTop: "18px" }}>
            <div style={{ fontSize: "13px", color: "var(--c-gray-500)", marginBottom: "8px" }}>待处理问题总数</div>
            <div style={{ fontSize: "22px", fontWeight: 700, color: "var(--c-danger)" }}>
              {unresolvedIssues.length} 项
            </div>
            <div style={{ fontSize: "12px", color: "var(--c-gray-500)", marginTop: "2px" }}>
              {compatibilityIssues.length - unresolvedIssues.length} 项已完成或已标注
            </div>
          </div>
        </Card>

        <Card>
          <div style={{ fontSize: "13px", color: "var(--c-gray-500)", marginBottom: "8px" }}>已修复问题</div>
          <div style={{ fontSize: "22px", fontWeight: 700, color: "var(--c-success)" }}>
            {defectTypes.filter((d) => d.status === "resolved").length} 类
          </div>
          <div style={{ fontSize: "12px", color: "var(--c-gray-500)", marginTop: "2px" }}>
            官方六类检测中的已修复项
          </div>

          <div style={{ marginTop: "18px" }}>
            <div style={{ fontSize: "13px", color: "var(--c-gray-500)", marginBottom: "8px" }}>产线完整度</div>
            <div className="flex flex-col gap-1">
              {dq?.line_completeness && Object.entries(dq.line_completeness).map(([line, val]) => {
                const overall = typeof val === "object" ? val?.overall : val;
                const detail = typeof val === "object"
                  ? `班次 ${Math.round((val?.shift || 0) * 100)}% · 停机 ${Math.round((val?.downtime || 0) * 100)}%`
                  : "";
                return (
                <div key={line} className="flex items-center gap-2" title={detail}>
                  <span className="text-xs" style={{ width: "60px", color: "var(--c-gray-600)" }}>
                    {t_line(line).split("（")[0]}
                  </span>
                  <div style={{ flex: 1, height: "6px", background: "var(--c-gray-100)", borderRadius: "3px" }}>
                    <div style={{
                      width: `${(overall || 0) * 100}%`,
                      height: "100%",
                      borderRadius: "3px",
                      background: overall >= 0.95 ? "var(--c-success)" : overall >= 0.8 ? "var(--c-warning)" : "var(--c-danger)",
                    }}></div>
                  </div>
                  <span className="text-xs mono" style={{ width: "36px", textAlign: "right", color: "var(--c-gray-600)" }}>
                    {Math.round((overall || 0) * 100)}%
                  </span>
                </div>
                );
              })}
            </div>
          </div>
        </Card>
      </div>

      {/* 六类缺陷卡片 */}
      <Card
        title={
          <span className="flex items-center gap-2">
            <Icon.Governance style={{ color: "var(--c-primary-500)" }} />
              官方六类缺陷检测
          </span>
        }
        extra={
          <span className="text-sm text-muted">
            {isOfficialDataset ? "官方脱敏数据检测结果" : "团队工程化数据未运行官方六类缺陷检测；请看下方兼容性检查"}
          </span>
        }
      >
        <div className="grid" style={{ gridTemplateColumns: "repeat(3, 1fr)", gap: "12px" }}>
          {defectTypes.map((d) => {
            const name = t_defect(d.defect_type);
            const desc = BIFROST_I18N.defectTypeDescriptions[d.defect_type] || d.label || "";
            const statusType = getDefectStatus(d.status);
            const statusLabel = d.status_label || getDefectStatusLabel(d.status);
            const notTested = d.status === "not_tested";

            return (
              <div
                key={d.defect_type}
                onClick={() => setActiveDefect(activeDefect === d.defect_type ? null : d.defect_type)}
                style={{
                  border: "1px solid var(--c-gray-200)",
                  borderRadius: "var(--radius-md)",
                  padding: "14px 16px",
                  cursor: "pointer",
                  transition: "all 0.15s",
                  background: activeDefect === d.defect_type ? "var(--c-primary-50)" : "#fff",
                  borderColor: activeDefect === d.defect_type ? "var(--c-primary-400)" : undefined,
                }}
              >
                <div className="flex items-center justify-between mb-2">
                  <div style={{ fontSize: "14px", fontWeight: 600, color: "var(--c-gray-900)" }}>
                    {name}
                  </div>
                  <Badge type={statusType}>{statusLabel}</Badge>
                </div>
                <div style={{ fontSize: "12px", color: "var(--c-gray-500)", lineHeight: 1.5, marginBottom: "10px" }}>
                  {notTested
                    ? "当前尚未接入官方含缺陷数据，不能宣称已识别或已修复。"
                    : desc}
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span style={{ color: "var(--c-gray-500)" }}>
                    影响记录：<span style={{ color: "var(--c-gray-800)", fontWeight: 500 }}>
                      {Array.isArray(d.affected_records) ? d.affected_records.length : (d.affected_records || 0)}
                    </span>
                  </span>
                  <span style={{ color: "var(--c-gray-500)" }}>
                    问题数：<span style={{ color: "var(--c-gray-800)", fontWeight: 500 }}>
                      {d.issue_count || 0}
                    </span>
                  </span>
                </div>

                {activeDefect === d.defect_type && (
                  <div style={{ marginTop: "12px", paddingTop: "12px", borderTop: "1px dashed var(--c-gray-200)" }}>
                    <div style={{ fontSize: "12px", fontWeight: 600, marginBottom: "8px", color: "var(--c-gray-700)" }}>
                      四段式信息
                    </div>
                    <div style={{ fontSize: "12px", lineHeight: 1.8 }}>
                      <div>
                        <strong>问题记录：</strong>
                        {notTested ? "暂无检测结果" : `${d.issue_count || 0} 条问题待处理`}
                      </div>
                      <div>
                        <strong>建议清洗方式：</strong>
                        {d.proposed_action || "暂无建议"}
                      </div>
                      <div>
                        <strong>是否需人工确认：</strong>
                        {notTested ? "检测后自动判定" : "是（高风险变更）"}
                      </div>
                      <div>
                        <strong>处理状态：</strong>{statusLabel}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </Card>

      {/* 当前数据源兼容性检查 */}
      <div style={{ marginTop: "16px" }}>
        <Card
          title={
            <span className="flex items-center gap-2">
              <Icon.Task style={{ color: "var(--c-warning)" }} />
              当前数据源兼容性检查
            </span>
          }
          extra={<span className="text-sm text-muted">字段映射、数据缺口、版本与关联绑定</span>}
        >
          <div className="text-sm text-muted" style={{ marginBottom: "12px", lineHeight: 1.6 }}>
            这里展示的是当前载荷进入统一语义模型前后的兼容性检查，不等同于官方六类数据缺陷检测。每条记录都应能展开查看检查规则、处理建议和证据绑定状态。
          </div>
          <table className="data-table">
            <thead>
              <tr>
                <th style={{ width: "60px" }}>编号</th>
                <th>问题描述</th>
                <th style={{ width: "100px" }}>检查类别</th>
                <th style={{ width: "220px" }}>检测规则</th>
                <th style={{ width: "80px" }}>严重度</th>
                <th style={{ width: "120px" }}>影响产线</th>
                <th style={{ width: "90px" }}>状态</th>
                <th style={{ width: "100px" }}>操作</th>
              </tr>
            </thead>
            <tbody>
               {compatibilityIssues.map((issue, i) => {
                const id = issue.id || i;
                const expanded = activeIssue === id;
                return (
                  <React.Fragment key={id}>
                    <tr>
                      <td className="text-sm text-muted">问题 {i + 1}</td>
                      <td>{issue.description}</td>
                      <td>
                        <Badge type="default">{issueCategoryLabel(issue.category)}</Badge>
                      </td>
                      <td className="text-sm text-muted">{issueRuleLabel(issue.category)}</td>
                      <td>
                        <Badge type={
                          issue.severity === "critical" || issue.severity === "high" ? "danger" :
                          issue.severity === "medium" ? "warning" : "info"
                        }>
                          {t_severity(issue.severity)}
                        </Badge>
                      </td>
                      <td>
                        {(issue.affected_lines || []).map((l) => t_line(l).split("（")[0]).join("、")}
                      </td>
                      <td>
                          <Badge type={issueStatusType(issue)}>
                            {issueStatusLabel(issue)}
                          </Badge>
                      </td>
                      <td>
                        <button
                          className="btn btn-ghost btn-sm"
                          onClick={() => setActiveIssue(expanded ? null : id)}
                        >
                          {expanded ? "收起" : "查看"}
                        </button>
                        <button
                          className="btn btn-default btn-sm"
                          disabled={false}
                          title={isReadonly ? "只读模式：仅生成处理草稿，不会修改源数据" : "生成处理草稿"}
                          onClick={() => { setActiveIssue(id); createGovernanceActionDraft(issue); }}
                        >
                          生成草稿
                        </button>
                      </td>
                    </tr>
                    {expanded && (
                      <tr>
                        <td colSpan={8} style={{ padding: 0, border: "none" }}>
                          <div style={{
                            padding: "12px 16px",
                            background: "var(--c-gray-50)",
                            borderTop: "1px dashed var(--c-gray-200)",
                            fontSize: "12px",
                            lineHeight: 1.8,
                          }}>
                            <div style={{ fontWeight: 600, marginBottom: "6px", color: "var(--c-gray-700)" }}>
                              问题详情
                            </div>
                            <div><strong>问题描述：</strong>{issue.description || "-"}</div>
                            {issue.analysis && (
                              <div><strong>初步分析：</strong>{issue.analysis}</div>
                            )}
                            {issue.suggested_action && (
                              <div><strong>建议处理：</strong>{issue.suggested_action}</div>
                            )}
                            <div><strong>证据绑定：</strong><span className="mono text-sm">{issue.evidence_ref || "尚未绑定物理记录"}</span></div>
                            <div><strong>影响产线：</strong>{(issue.affected_lines || []).map((l) => t_line(l)).join("、")}</div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </Card>
      </div>

      {/* 技术详情（折叠） */}
      <div style={{ marginTop: "16px" }}>
        <Collapse
          title={
            <span className="flex items-center gap-2">
              <Icon.Database />
              技术详情（数据合同）
            </span>
          }
          badge={<Badge type="default" dot>管理员可见</Badge>}
        >
          <div className="grid grid-2 gap-3">
            <div>
              <div style={{ fontSize: "12px", fontWeight: 600, color: "var(--c-gray-600)", marginBottom: "8px" }}>
                源表信息
              </div>
              <div className="detail-row">
                <div className="detail-label">工作簿</div>
                <div className="detail-value mono text-sm">{getSourceStatus()?.sim_workbook || "-"}</div>
              </div>
              <div className="detail-row">
                <div className="detail-label">总表数</div>
                <div className="detail-value mono text-sm">{getSourceStatus()?.total_sheets || 0}</div>
              </div>
              <div className="detail-row">
                <div className="detail-label">物化状态</div>
                <div className="detail-value mono text-sm">
                  {dq?.materialization_status
                    ? Object.entries(dq.materialization_status).map(([k, v]) => `${k}: ${v}`).join("; ")
                    : "-"}
                </div>
              </div>
            </div>
            <div>
              <div style={{ fontSize: "12px", fontWeight: 600, color: "var(--c-gray-600)", marginBottom: "8px" }}>
                检测规则
              </div>
              {defectTypes.map((d, i) => (
                <div key={i} className="detail-row">
                  <div className="detail-label">{t_defect(d.defect_type)}</div>
                  <div className="detail-value mono text-sm">
                    {d.detected_by || "规则引擎"} · {d.run_id || "-"}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </Collapse>
      </div>
    </div>
  );
}

// ========== 管理配置页 ==========
function DynamicDataAdapterPanel() {
  const [sourcePath, setSourcePath] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [governanceDraft, setGovernanceDraft] = useState(null);
  const [governanceDraftError, setGovernanceDraftError] = useState("");
  const [selectedMappings, setSelectedMappings] = useState([]);
  const [flow, setFlow] = useState("idle");
  const [drilldownDimension, setDrilldownDimension] = useState("");
  const [drilldownValue, setDrilldownValue] = useState("");
  const pendingMappings = (result?.mapping_manifest?.preview || []).filter(
    (item) => item.requires_human_confirmation && !item.confirmed
  );
  const pendingMappingIds = result?.mapping_manifest?.pending_mapping_ids || pendingMappings.map((item) => item.mapping_id).filter(Boolean);
  const mappingApproved = result?.mapping_manifest?.status === "approved" || pendingMappingIds.length === 0;
  const flowLabel = {
    idle: "等待分析",
    analyzed: "已分析，待确认映射",
    confirmed: "映射已确认，可预览",
    preview: "只读预览已应用",
    rolled_back: "已回退到正式载荷",
  }[flow] || "等待分析";

  const runAdaptation = async (confirmMappings = false, explicitMappingIds = null, filters = null) => {
    const confirmationIds = Array.isArray(explicitMappingIds) ? explicitMappingIds : selectedMappings;
    const shouldConfirm = confirmMappings || confirmationIds.length > 0;
    if (!sourcePath.trim()) {
      setError("请输入服务器可读取的数据文件路径");
      return;
    }
    if (shouldConfirm && confirmationIds.length === 0) {
      setError("请至少选择一条字段映射；仅分析不会视为确认");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/data-adapt", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_path: sourcePath.trim(), source_id: "UI-IMPORT", confirmations: shouldConfirm ? confirmationIds : [], drilldown_filters: filters || undefined }),
      });
      const payload = await response.json();
      if (!response.ok || payload.status === "blocked") {
        throw new Error(payload.detail || payload.error || "数据适配失败");
      }
      const adaptedResult = payload.result || payload;
      setResult(adaptedResult);
      const nextPending = (adaptedResult.mapping_manifest?.preview || []).filter(
        (item) => item.requires_human_confirmation && !item.confirmed
      );
      setFlow(nextPending.length === 0 || adaptedResult.mapping_manifest?.status === "approved" ? "confirmed" : "analyzed");
      if (!shouldConfirm) setSelectedMappings([]);
    } catch (err) {
      setResult(null);
      setFlow("idle");
      setError(err.message || "数据适配失败");
    } finally {
      setBusy(false);
    }
  };

  const createGovernanceActionDraft = async (issue) => {
    setGovernanceDraftError("");
    try {
      const response = await fetch("/api/governance-action-draft", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ issue, role: "factory" }),
      });
      const payload = await response.json();
      if (!response.ok || payload.status !== "ok") throw new Error(payload.detail || "无法生成处理草稿");
      setGovernanceDraft(payload.draft);
    } catch (error) {
      setGovernanceDraft(null);
      setGovernanceDraftError(error.message || "无法生成处理草稿");
    }
  };

  const applyPreview = () => {
    if (!mappingApproved || !result?.generated_payloads) {
      setError("请先完成映射确认，再应用只读预览");
      return;
    }
    try {
      applyDynamicPayloads(result.generated_payloads, result.peer_analysis);
      setFlow("preview");
      setError("");
    } catch (err) {
      setError(err.message || "只读预览应用失败");
    }
  };

  const rollbackPreview = () => {
    if (typeof rollbackDynamicPayloads === "function" && rollbackDynamicPayloads()) {
      setFlow("rolled_back");
      setError("");
    }
  };

  const overview = result?.generated_payloads?.overview;
  const drilldown = result?.drilldown_manifest || overview?.drilldown_manifest;
  const drilldownDimensions = Object.entries(drilldown?.dimensions || {}).filter(([, info]) => info?.available && (info.values_preview || []).length > 0);
  const selectedDrilldownInfo = drilldown?.dimensions?.[drilldownDimension];
  const selectedDrilldownValues = drilldownDimension === "line" && (drilldown?.active_line_ids || []).length > 0
    ? drilldown.active_line_ids
    : (selectedDrilldownInfo?.values_preview || []);
  const drilldownResult = result?.drilldown_result;
  const capabilities = overview?.capability_manifest || result?.capability_manifest || {};
  const available = Object.entries(capabilities).filter(([, value]) => value?.status === "available");
  const gaps = Object.entries(capabilities).filter(([, value]) => value?.status !== "available");

  return (
    <Card
      title={<span className="flex items-center gap-2"><Icon.Database style={{ color: "var(--c-primary-500)" }} />数据源自动适配</span>}
      extra={<Badge type="info" dot>只读试运行</Badge>}
    >
      <div className="text-sm text-muted" style={{ lineHeight: 1.6, marginBottom: "10px" }}>
        输入文件路径后，系统会自动生成数据源档案、映射确认结果、统一数据集和动态指标载荷。不会修改原始文件，也不会覆盖当前正式看板。
      </div>
      <div className="text-sm" style={{ marginBottom: "10px", padding: "8px 10px", borderRadius: "var(--radius-sm)", background: "var(--c-warning-50)", color: "var(--c-warning-800)" }}>
        当前为会话级只读预览：确认映射后才可应用，刷新页面或点击“回退正式载荷”即可恢复正式数据，不会写回数据源。
      </div>
      <div className="adapter-flow-steps" aria-label="数据适配流程" style={{ display: "flex", gap: "6px", flexWrap: "wrap", marginBottom: "10px" }}>
        {["分析", "确认映射", "应用只读预览", "回退"].map((label, index) => {
          const active = (index === 0 && ["analyzed", "confirmed", "preview", "rolled_back"].includes(flow)) ||
            (index === 1 && ["confirmed", "preview"].includes(flow)) ||
            (index === 2 && flow === "preview") || (index === 3 && flow === "rolled_back");
          return <span key={label} className="text-xs" style={{ padding: "4px 8px", borderRadius: "999px", background: active ? "var(--c-primary-50)" : "var(--c-gray-100)", color: active ? "var(--c-primary-700)" : "var(--c-gray-600)", fontWeight: active ? 600 : 400 }}>{index + 1}. {label}</span>;
        })}
        <span className="text-xs text-muted" style={{ alignSelf: "center" }}>当前：{flowLabel}</span>
      </div>
      <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
        <input
          value={sourcePath}
          onChange={(event) => setSourcePath(event.target.value)}
          placeholder="例如：D:\\Edgedownload\\数据包.xlsx"
          style={{ flex: 1, minWidth: 0, padding: "9px 10px", border: "1px solid var(--c-gray-300)", borderRadius: "var(--radius-sm)" }}
        />
        <button className="btn btn-primary" onClick={() => { setSelectedMappings([]); runAdaptation(false); }} disabled={busy}>
          {busy ? "适配中…" : "开始适配"}
        </button>
      </div>
      {error && <div className="text-sm" style={{ color: "var(--c-danger-600)", marginTop: "10px" }}>{error}</div>}
      {result && (
        <div style={{ marginTop: "12px", padding: "12px", background: "var(--c-gray-50)", borderRadius: "var(--radius-sm)" }}>
          <div className="flex items-center justify-between">
            <strong>适配结果</strong>
            <Badge type={mappingApproved ? "success" : "warning"}>
              {result.mapping_manifest?.status === "approved" ? "映射已确认" : "需要确认映射"}
            </Badge>
          </div>
          <div className="text-sm text-muted" style={{ marginTop: "6px" }}>
            统一记录 {result.canonical_dataset?.record_count ?? 0} 条 · 已批准映射 {result.mapping_manifest?.approved_count ?? 0} 条 · 待确认 {result.mapping_manifest?.confirmation_count ?? 0} 条
          </div>
          <div className="text-sm" style={{ marginTop: "8px" }}>
            可计算：{available.length ? available.map(([key]) => key === "oee" ? "综合设备效率（OEE）" : key === "yield" ? "良率" : key === "spc" ? "统计过程控制（SPC）" : key === "mtbf" ? "平均故障间隔时间（MTBF）" : key === "supply_risk" ? "供应风险" : key).join("、") : "暂无"}
          </div>
          {gaps.length > 0 && <div className="text-sm text-muted" style={{ marginTop: "4px" }}>
            暂不可判定：{gaps.map(([key]) => key === "spc" ? "统计过程控制（SPC）" : key === "mtbf" ? "平均故障间隔时间（MTBF）" : key === "supply_risk" ? "供应风险" : key).join("、")}
          </div>}
          {overview?.metrics?.oee && <div className="text-sm" style={{ marginTop: "4px" }}>统一载荷 OEE：{(overview.metrics.oee.value * 100).toFixed(2)}%</div>}
            {drilldown && <div style={{ marginTop: "12px", padding: "10px", border: "1px solid var(--c-gray-200)", borderRadius: "var(--radius-sm)", background: "var(--c-white)" }}>
              <div className="flex items-center justify-between"><strong>可下钻的事实层级</strong><Badge type="info">证据优先</Badge></div>
              <div className="text-xs text-muted" style={{ marginTop: "4px" }}>系统会先定位时间、班次、工单，再关联停机、不良、设备和物料记录；没有对应字段时只提示缺口，不生成猜测。</div>
             <div className="flex gap-2" style={{ marginTop: "8px", flexWrap: "wrap" }}>
               {(drilldown.levels || []).filter((level) => level.available).map((level) => <span key={level.level} className="text-xs" style={{ padding: "4px 8px", borderRadius: "999px", background: "var(--c-primary-50)", color: "var(--c-primary-700)" }}>{({ overview: "总览", time_slice: "日期/时间", shift: "班次", work_order: "工单", event_evidence: "事件与证据" }[level.level] || level.level)}</span>)}
             </div>
              {(drilldown.data_gaps || []).length > 0 && <div className="text-xs text-muted" style={{ marginTop: "6px" }}>当前数据暂缺：{drilldown.data_gaps.slice(0, 5).map((gap) => gap.replace(/^missing_/, "")).join("、")}</div>}
              {mappingApproved && drilldownDimensions.length > 0 && <div style={{ marginTop: "10px", paddingTop: "10px", borderTop: "1px dashed var(--c-gray-200)" }}>
                <div className="text-sm" style={{ fontWeight: 600, marginBottom: "6px" }}>按条件查看事实</div>
                <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                  <select value={drilldownDimension} onChange={(event) => { setDrilldownDimension(event.target.value); setDrilldownValue(""); }} style={{ minWidth: "150px", padding: "7px 8px", border: "1px solid var(--c-gray-300)", borderRadius: "var(--radius-sm)" }}>
                    <option value="">选择维度</option>
                    {drilldownDimensions.map(([key]) => <option key={key} value={key}>{({ line: "产线", date: "日期", shift: "班次", work_order: "工单", product: "产品", equipment: "设备", material: "物料", defect: "不良类型", stop_reason: "停机原因", process: "工序" }[key] || key)}</option>)}
                  </select>
                  <select value={drilldownValue} onChange={(event) => setDrilldownValue(event.target.value)} disabled={!selectedDrilldownInfo} style={{ minWidth: "190px", padding: "7px 8px", border: "1px solid var(--c-gray-300)", borderRadius: "var(--radius-sm)" }}>
                    <option value="">选择值</option>
                    {selectedDrilldownValues.map((value) => <option key={String(value)} value={String(value)}>{String(value)}</option>)}
                  </select>
                  <button className="btn btn-secondary btn-sm" disabled={!drilldownDimension || !drilldownValue || busy} onClick={() => runAdaptation(true, result.mapping_manifest?.approved_mapping_ids || [], { [drilldownDimension]: drilldownValue })}>查看事实</button>
                </div>
                {drilldownResult && <div style={{ marginTop: "10px", padding: "8px 10px", background: "var(--c-gray-50)", borderRadius: "var(--radius-sm)" }}>
                  <div className="text-sm"><strong>查询结果：</strong>{drilldownResult.facts?.record_count || 0} 条记录 · 证据 {drilldownResult.facts?.evidence_count || 0} 条</div>
                  <div className="text-xs text-muted" style={{ marginTop: "4px" }}>停机 {drilldownResult.facts?.downtime?.sum ?? "—"} 分钟 · 不良 {drilldownResult.facts?.defect_count?.sum ?? "—"} 件 · 产量 {drilldownResult.facts?.output?.sum ?? "—"} 件</div>
                  {(drilldownResult.root_cause_candidates || []).length > 0 && <div className="text-xs" style={{ marginTop: "5px" }}>优先排查线索：{drilldownResult.root_cause_candidates.slice(0, 3).map((item) => `${item.category}=${item.label}`).join("；")}（仅关联排序，需结合证据确认）</div>}
                  {(drilldownResult.evidence_refs || []).length > 0 && <details style={{ marginTop: "5px" }}><summary className="text-xs">查看证据引用（{drilldownResult.evidence_refs.length}）</summary><div className="mono text-xs text-muted" style={{ whiteSpace: "pre-wrap", marginTop: "4px" }}>{drilldownResult.evidence_refs.slice(0, 10).join("\n")}</div></details>}
                </div>}
              </div>}
            </div>}
           {result.peer_analysis && <div style={{ marginTop: "12px", padding: "10px", border: "1px solid var(--c-gray-200)", borderRadius: "var(--radius-sm)" }}>
             <div className="flex items-center justify-between"><strong>辅助分析（只读）</strong><Badge type="info">不改变正式指标</Badge></div>
             <div className="text-xs text-muted" style={{ marginTop: "4px" }}>已将当前已确认数据交给生产、质量、供应三个分析模块；仅使用可追溯证据，不能直接写回数据。</div>
             <div className="text-sm" style={{ marginTop: "6px" }}>已生成 {result.peer_analysis.peer_results?.length || 0} 项分析；{result.peer_analysis.requires_physical_evidence_resolution ? "部分结果仍需补充证据或人工确认" : "证据检查通过"}。</div>
             <div style={{ marginTop: "8px", display: "grid", gap: "6px" }}>
               {(result.peer_analysis.peer_results || []).map((item) => {
                 const labels = { "a01-oee-loss-tree": "OEE损失拆解", "a02-pareto": "主要原因排序", "a07-yield-funnel": "良率流转", "a03-spc-rules": "工艺稳定性数据检查", "a08-supply-chain-gap": "供应链缺口" };
                 const statuses = { available: "可用", warning: "需确认", blocked: "暂不可判定", not_observed: "未观察到" };
                 return <div key={item.skill_id} className="text-xs" style={{ display: "flex", justifyContent: "space-between", gap: "8px", padding: "6px 8px", background: "var(--c-white)", borderRadius: "var(--radius-sm)" }}><span>{labels[item.skill_id] || "辅助分析"}</span><span className="text-muted">{statuses[item.status] || "待确认"}{item.data_gaps?.length ? ` · 缺少${item.data_gaps.length}项数据` : ""}</span></div>;
               })}
             </div>
            </div>}
           {result.generated_payloads && mappingApproved && <div style={{ marginTop: "10px", display: "flex", gap: "8px", flexWrap: "wrap" }}>
            <button className="btn btn-primary" onClick={applyPreview} disabled={flow === "preview"}>3. 应用只读预览</button>
            {flow === "preview" && <button className="btn btn-default" onClick={rollbackPreview}>4. 回退正式载荷</button>}
          </div>}
          {false && <button className="btn btn-primary" style={{ marginTop: "10px" }} onClick={() => applyDynamicPayloads(result.generated_payloads)}>
            应用到当前看板（只读预览）
          </button>}
          {(pendingMappings.length > 0 || pendingMappingIds.length > 0) && (
            <div style={{ marginTop: "10px" }}>
              <div className="text-sm" style={{ marginBottom: "6px", fontWeight: 600 }}>待确认字段（最多显示 8 条）</div>
              {pendingMappingIds.length > 0 && <button className="btn btn-secondary btn-sm" onClick={() => runAdaptation(true, pendingMappingIds)} disabled={busy}>
                确认全部待审核映射（{pendingMappingIds.length} 条）
              </button>}
              {pendingMappings.slice(0, 8).map((item) => (
                <label key={item.mapping_id} className="text-sm" style={{ display: "flex", gap: "6px", alignItems: "center", marginTop: "4px" }}>
                  <input
                    type="checkbox"
                    checked={selectedMappings.includes(item.mapping_id)}
                    onChange={(event) => setSelectedMappings((current) => event.target.checked ? [...current, item.mapping_id] : current.filter((id) => id !== item.mapping_id))}
                  />
                  <span>{item.source_field || "未命名字段"} → {item.target_field ? t_field(item.target_field) : "待映射"}</span>
                </label>
              ))}
              {selectedMappings.length > 0 && <button className="btn btn-secondary" style={{ marginTop: "8px" }} onClick={() => runAdaptation(true)} disabled={busy}>确认所选映射并重算</button>}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

function RuleSimulationPanel() {
  const DEFAULT_SAMPLE = { availability: 0.85, performance_rate: 0.78, quality_rate: 0.912867, good_qty: 950, input_qty: 1000, actual_changeover_minutes: 22, standard_changeover_minutes: 15 };
  const [ruleSet, setRuleSet] = useState(null);
  const [draft, setDraft] = useState(null);
  const [inputSchema, setInputSchema] = useState({});
  const [ruleBinding, setRuleBinding] = useState(null);
  const [sample, setSample] = useState(DEFAULT_SAMPLE);
  const [sampleRows, setSampleRows] = useState([DEFAULT_SAMPLE]);
  const [simulation, setSimulation] = useState(null);
  const [draftSubmission, setDraftSubmission] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    fetch("/api/rule-defaults")
      .then((res) => res.json())
      .then((payload) => {
        if (!active) return;
        if (payload.status !== "ok") throw new Error(payload.error || "规则加载失败");
        setRuleSet(payload.rule_set);
        setInputSchema(payload.input_schema || {});
        setRuleBinding(payload.rule_binding || null);
        const candidate = JSON.parse(JSON.stringify(payload.rule_set));
        candidate.status = "draft";
        candidate.rule_version = `${payload.rule_set.rule_version}-draft`;
        setDraft(candidate);
      })
      .catch((err) => active && setError(err.message || "规则加载失败"))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  const sampleFields = useMemo(() => {
    const fields = Object.values(inputSchema || {}).flatMap((item) => Array.isArray(item?.fields) ? item.fields : []);
    return [...new Set(fields.length ? fields : Object.keys(DEFAULT_SAMPLE))];
  }, [inputSchema]);
  const sampleMinimum = useMemo(() => Math.max(1, ...Object.values(inputSchema || {}).map((item) => Number(item?.min_sample_size) || 1)), [inputSchema]);
  useEffect(() => {
    setSample((current) => Object.fromEntries(sampleFields.map((field) => [field, current[field] ?? DEFAULT_SAMPLE[field] ?? ""])));
    setSampleRows((current) => current.map((row, index) => index === 0
      ? Object.fromEntries(sampleFields.map((field) => [field, row[field] ?? DEFAULT_SAMPLE[field] ?? ""]))
      : row));
  }, [sampleFields]);

  const updateMetric = (metricId, field, value) => {
    setSimulation(null);
    setDraftSubmission(null);
    if (field === "formula") {
      setDraft((current) => ({ ...current, metrics: { ...current.metrics, [metricId]: { ...current.metrics[metricId], formula: value } } }));
      return;
    }
    const numeric = value === "" ? "" : Number(value);
    if (numeric !== "" && !Number.isFinite(numeric)) return;
    setDraft((current) => ({ ...current, metrics: { ...current.metrics, [metricId]: { ...current.metrics[metricId], thresholds: { ...current.metrics[metricId].thresholds, [field]: numeric } } } }));
  };
  const updateSample = (field, value, rowIndex = 0) => {
    setSimulation(null);
    setDraftSubmission(null);
    const numeric = value === "" ? "" : Number(value);
    if (numeric !== "" && !Number.isFinite(numeric)) return;
    if (rowIndex === 0) setSample((current) => ({ ...current, [field]: numeric }));
    setSampleRows((current) => current.map((row, index) => index === rowIndex ? { ...row, [field]: numeric } : row));
  };
  const validateSimulationInput = () => {
    if (!draft || !draft.metrics || typeof draft.metrics !== "object") return "候选规则不可用";
    for (const [metricId, metric] of Object.entries(draft.metrics)) {
      if (!metric || typeof metric.formula !== "string" || !metric.formula.trim()) return `${metricId} 公式不能为空`;
      for (const field of ["target", "warning", "critical"]) {
        if (metric.thresholds?.[field] === "" || !Number.isFinite(Number(metric.thresholds?.[field]))) return `${metricId} 阈值必须是有限数字`;
      }
    }
    for (const [rowIndex, row] of sampleRows.entries()) {
      for (const [field, value] of Object.entries(row)) {
        if (value === "" || !Number.isFinite(Number(value))) return `第${rowIndex + 1}行 ${field} 样本值必须是有限数字`;
        if (Number(value) < 0) return `第${rowIndex + 1}行 ${field} 样本值不能为负数`;
        if (["availability", "performance_rate", "quality_rate"].includes(field) && Number(value) > 1) return `第${rowIndex + 1}行 ${field} 必须在 0 到 1 之间`;
      }
    }
    if (sampleRows.length < sampleMinimum) return `当前规则至少需要 ${sampleMinimum} 条样本；请先添加样本行`;
    return "";
  };
  const runSimulation = async () => {
    if (!draft) return;
    const validationError = validateSimulationInput();
    if (validationError) { setError(validationError); setSimulation(null); return; }
    setRunning(true); setError("");
    try {
      const overviewContext = BIFROST_DATA.overview || {};
      const response = await fetch("/api/rule-simulate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
        candidate_rule_set: draft,
        rows: sampleRows,
        dataset_id: overviewContext.dataset_id || overviewContext.source_profile?.dataset_id,
        time_window: overviewContext.time_window || "last_7_shifts",
        source_payload_sha256: overviewContext.payload_sha256 || overviewContext.source_profile?.source_sha256,
      }) });
      const payload = await response.json();
      if (!response.ok || payload.status !== "ok") throw new Error(payload.detail || payload.error || "试算失败");
      if (!payload.simulation?.readonly || payload.simulation?.source_write_performed !== false) throw new Error("试算契约未通过只读门禁");
      setSimulation(payload.simulation);
    } catch (err) { setError(err.message || "试算失败"); setSimulation(null); }
    finally { setRunning(false); }
  };
  const resetDraft = () => {
    if (ruleSet) {
      const candidate = JSON.parse(JSON.stringify(ruleSet));
      candidate.status = "draft";
      candidate.rule_version = `${ruleSet.rule_version}-draft`;
      setDraft(candidate);
      setSample(DEFAULT_SAMPLE);
      setSampleRows([DEFAULT_SAMPLE]);
    }
    setSimulation(null); setDraftSubmission(null); setError("");
  };
  const submitDraft = async () => {
    if (!draft || !simulation?.readonly || simulation.source_write_performed !== false) {
      setError("请先完成只读试算，再提交审批草稿");
      return;
    }
    if (simulation.publishable !== true || (simulation.data_gaps || []).length > 0) {
      setError("当前试算存在数据缺口，不能提交规则审批草稿；请先补齐样本或修正公式");
      return;
    }
    setRunning(true); setError("");
    try {
      const response = await fetch("/api/rule-submit-draft", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ candidate_rule_set: draft, simulation }) });
      const payload = await response.json();
      if (!response.ok || payload.status !== "ok") throw new Error(payload.detail || payload.error || "提交审批草稿失败");
      if (!payload.draft?.requires_human_confirmation || !payload.draft?.readonly || payload.draft?.source_write_performed !== false || payload.draft?.actor_can_execute !== false) throw new Error("审批草稿契约未通过只读门禁");
      setDraftSubmission(payload.draft);
    } catch (err) { setError(err.message || "提交审批草稿失败"); setDraftSubmission(null); }
    finally { setRunning(false); }
  };
  const statusLabel = (status) => ({ pass: "达标", warning: "预警", critical: "严重", insufficient_data: "数据不足", blocked: "已阻断" }[status] || t_status(status) || "-");
  if (loading) return <Card title="规则试算"><div className="text-sm text-muted">正在加载规则定义…</div></Card>;
  if (!draft) return <Card title="规则试算"><div className="text-sm text-danger">{error || "规则定义不可用"}</div></Card>;

  return (
    <Card title={<span className="flex items-center gap-2"><Icon.Config style={{ color: "var(--c-primary-500)" }} />规则试算与影响预览</span>} extra={<Badge type="info" dot>只生成草稿，不直接发布</Badge>}>
      <div className="text-sm text-muted" style={{ marginBottom: "14px", lineHeight: 1.6 }}>修改候选公式或阈值后，用同一批样本比较新旧结果。试算不会修改历史事件、原始数据或正式规则；只有“数据完整、试算可发布”时才能生成审批草稿。</div>
      {ruleBinding && <div className="text-xs text-muted" style={{ marginBottom: "12px", padding: "8px 10px", background: "var(--c-gray-50)", borderRadius: "var(--radius-sm)" }}>
        当前试算标准：{ruleBinding.rule_set_id || "本地规则集"} · {ruleBinding.rule_version || "版本未提供"}。{ruleBinding.message}
      </div>}
      <div className="grid grid-2" style={{ gap: "14px" }}>
        <div>
          <div style={{ fontWeight: 600, marginBottom: "4px" }}>候选指标规则</div>
          <div className="text-xs text-muted" style={{ marginBottom: "8px", lineHeight: 1.5 }}>这里修改的是“下一版规则草稿”，用于回答“如果标准改变，结果会怎样”；不会直接改历史数据或正式看板。</div>
          {Object.entries(draft.metrics).map(([metricId, metric]) => (
            <div key={metricId} style={{ border: "1px solid var(--c-gray-200)", borderRadius: "var(--radius-sm)", padding: "10px", marginBottom: "8px" }}>
              <div className="flex items-center justify-between" style={{ marginBottom: "6px" }}><strong>{metric.label || t_field(metricId)}</strong></div>
              <details style={{ marginTop: "6px" }}>
                <summary className="text-xs text-muted" style={{ cursor: "pointer" }}>高级设置：公式表达式（管理员）</summary>
                <div className="text-xs text-muted" style={{ margin: "6px 0", lineHeight: 1.5 }}>仅用于维护指标计算逻辑；修改后必须先重新试算，不能直接发布。</div>
                <textarea className="input mono text-sm rule-formula-input" rows="2" value={metric.formula} onChange={(e) => updateMetric(metricId, "formula", e.target.value)} aria-label={`${metricId} 公式`} title={metric.formula} />
              </details>
              <div className="grid grid-3" style={{ gap: "6px", marginTop: "7px" }}>
                {["target", "warning", "critical"].map((field) => <label key={field} className="text-xs text-muted">{field === "target" ? "目标" : field === "warning" ? "预警" : "严重"}<input className="input text-sm" type="number" step="0.001" value={metric.thresholds[field]} onChange={(e) => updateMetric(metricId, field, e.target.value)} /></label>)}
              </div>
            </div>
          ))}
        </div>
        <div>
          <div style={{ fontWeight: 600, marginBottom: "4px" }}>试算样本：用一条班次记录做影响预览</div>
          <div className="text-xs text-muted" style={{ marginBottom: "8px", lineHeight: 1.5 }}>请填入同一班次的实际开动率、性能率、质量率和产量。点击“试算影响”后，右侧会显示哪些指标从达标变为预警，是否允许生成人工审批草稿。</div>
          <div className="grid grid-2" style={{ gap: "8px" }}>
            {sampleFields.filter((field) => !Object.prototype.hasOwnProperty.call(DEFAULT_SAMPLE, field)).map((field) => {
              const descriptor = inputSchema?._fields?.[field] || Object.values(inputSchema || {}).find((item) => item?.fields?.includes(field));
              const ratio = descriptor?.value_type === "ratio" || descriptor?.unit === "ratio";
              return <label key={`dynamic-${field}`} className="text-xs text-muted">{t_field(field)}{ratio ? "（0–1）" : ""}<input className="input text-sm" type="number" step={ratio ? "0.001" : "1"} value={sample[field]} onChange={(e) => updateSample(field, e.target.value)} /></label>;
            })}
            {[["availability", "开动率"], ["performance_rate", "性能率"], ["quality_rate", "质量率"], ["good_qty", "良品数"], ["input_qty", "投入数"], ["actual_changeover_minutes", "实际换产分钟"], ["standard_changeover_minutes", "标准换产分钟"]].map(([field, label]) => <label key={field} className="text-xs text-muted">{label}<input className="input text-sm" type="number" step={field.includes("rate") || field === "availability" || field === "performance_rate" ? "0.001" : "1"} value={sample[field]} onChange={(e) => updateSample(field, e.target.value)} /></label>)}
          </div>
          {sampleRows.length > 1 && <div style={{ marginTop: "10px" }}>
            <div className="text-xs text-muted" style={{ marginBottom: "6px" }}>其他样本行（用于满足最小样本量；每行都参与试算）</div>
            {sampleRows.slice(1).map((row, offset) => <div key={`sample-row-${offset + 1}`} className="grid grid-2" style={{ gap: "8px", marginBottom: "8px", padding: "8px", border: "1px solid var(--c-gray-200)", borderRadius: "var(--radius-sm)" }}>
              {sampleFields.map((field) => {
                const descriptor = inputSchema?._fields?.[field] || {};
                const ratio = descriptor.value_type === "ratio" || field.includes("rate") || field === "availability" || field === "performance_rate";
                return <label key={`${offset + 1}-${field}`} className="text-xs text-muted">{descriptor.label || t_field(field)}<input className="input text-sm" type="number" step={ratio ? "0.001" : "1"} min={descriptor.min ?? 0} value={row[field] ?? ""} onChange={(e) => updateSample(field, e.target.value, offset + 1)} /></label>;
              })}
            </div>)}
          </div>}
          <div className="flex items-center gap-2" style={{ marginTop: "12px" }}><button className="btn btn-primary btn-sm" onClick={runSimulation} disabled={running}>{running ? "试算中…" : "试算影响"}</button><button className="btn btn-default btn-sm" onClick={resetDraft}>恢复基线</button><span className="text-xs text-muted">当前版本：{draft.rule_version}</span></div>
          {simulation && <button className="btn btn-default btn-sm" onClick={submitDraft} disabled={running || !simulation.readonly || simulation.source_write_performed !== false || simulation.publishable !== true || (simulation.data_gaps || []).length > 0} style={{ marginTop: "8px" }}>{simulation.publishable === true && !(simulation.data_gaps || []).length ? "提交审批草稿" : "数据不足，不能提交"}</button>}
          {draftSubmission && <div className="text-sm text-muted" style={{ marginTop: "8px" }}>已生成审批草稿 {draftSubmission.draft_id}，等待人工确认；未修改正式规则。</div>}
           <div className="text-xs text-muted" style={{ marginTop: "8px" }}>当前样本行：{sampleRows.length} / 最少 {sampleMinimum}</div>
           <button className="btn btn-default btn-sm" onClick={() => setSampleRows((current) => [...current, { ...current[0] }])} style={{ marginTop: "8px" }}>新增样本行</button>
           {error && <div className="text-sm text-danger" style={{ marginTop: "8px" }}>{error}</div>}
          {simulation && <div style={{ marginTop: "14px", borderTop: "1px solid var(--c-gray-200)", paddingTop: "12px" }}><div className="flex items-center justify-between" style={{ marginBottom: "8px" }}><strong>影响预览</strong><Badge type={simulation.publishable ? "success" : "danger"}>{simulation.publishable ? "可提交审批" : "存在数据缺口"}</Badge></div>{Object.entries(simulation.changed_metrics || {}).length === 0 ? <div className="text-sm text-muted">候选规则未改变当前样本结果。</div> : Object.entries(simulation.changed_metrics).map(([metricId, change]) => <div key={metricId} className="list-item"><div style={{ flex: 1 }}><strong>{t_field(metricId)}</strong><div className="text-xs text-muted">{change.before.value}（{statusLabel(change.before.status)}） → {change.after.value}（{statusLabel(change.after.status)}）</div></div><Badge type={change.after.status === "pass" ? "success" : change.after.status === "critical" ? "danger" : "warning"}>{statusLabel(change.after.status)}</Badge></div>)}<div className="text-xs text-muted" style={{ marginTop: "8px" }}>候选规则的影响预览；正式发布仍需人工审批。</div></div>}
        </div>
      </div>
    </Card>
  );
}

function ConfigPage() {
  const sourceStatus = getSourceStatus();
  const dataSources = getDataSourceRegistry();
  const overview = BIFROST_DATA.overview;

  return (
    <div className="page-content">
      <DynamicDataAdapterPanel />
      <RuleSimulationPanel />
      <div className="grid grid-2 mb-4">
        {/* 数据源配置 */}
        <Card
          title={
            <span className="flex items-center gap-2">
              <Icon.Database style={{ color: "var(--c-primary-500)" }} />
              数据源管理
            </span>
          }
        >
          <div className="text-sm text-muted" style={{ marginBottom: "10px", lineHeight: 1.6 }}>
            当前载荷：<strong>{getDataSourceLabel(overview)}</strong>（{overview?.data_nature || "只读演示"}）。不同来源先经过同一套字段映射、质量门禁和指标合同，再生成这套看板；这里不为每份数据复制页面。
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            {dataSources.map((ds) => (
              <div
                key={ds.dataset_id}
                style={{
                  padding: "12px 14px",
                  border: "1px solid var(--c-gray-200)",
                  borderRadius: "var(--radius-sm)",
                  display: "flex",
                  alignItems: "center",
                  gap: "12px",
                }}
              >
                <div style={{
                  width: "36px", height: "36px",
                  borderRadius: "var(--radius-sm)",
                  background: "var(--c-primary-50)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  color: "var(--c-primary-500)",
                }}>
                  <Icon.Database />
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: "13px", fontWeight: 600 }}>{ds.label}</div>
                  <div className="text-xs text-muted">
                    {ds.data_nature || "本地演示数据"}
                  </div>
                  <div className="text-xs text-muted" style={{ marginTop: "2px" }}>
                    {ds.note}
                  </div>
                </div>
                <Badge type={ds.dataset_id === overview?.dataset_id || ds.status === "active" ? "success" : ds.status === "BLOCKED_INPUT_DATA" ? "warning" : "default"}>
                  {ds.dataset_id === overview?.dataset_id || ds.status === "active" ? "当前使用" : ds.status === "BLOCKED_INPUT_DATA" ? "待导入载荷" : "待确认"}
                </Badge>
              </div>
            ))}
          </div>
        </Card>

        {/* 连接模式 */}
        <Card
          title={
            <span className="flex items-center gap-2">
              <Icon.Config style={{ color: "var(--c-primary-500)" }} />
              连接模式
            </span>
          }
        >
          {sourceStatus?.connection_mode && Object.entries(sourceStatus.connection_mode).map(([key, val]) => (
            <div key={key} className="detail-row">
              <div className="detail-label">{
                { data_mode: "数据模式", aily_mode: "AI 模式", writeback_mode: "写回模式", bitable_status: "多维表格" }[key] || key
              }</div>
              <div className="detail-value">
                <Badge type={
                  (key === "aily_mode" && val === "disabled") ? "default" :
                  (key === "writeback_mode" && val === "readonly") ? "info" :
                  "success"
                }>
                  {BIFROST_I18N.connectionMode[key]?.[val] || val}
                </Badge>
              </div>
            </div>
          ))}
          <div className="detail-row">
            <div className="detail-label">规则版本</div>
            <div className="detail-value mono text-sm">{overview?.rule_version || "-"}</div>
          </div>
          <div className="detail-row">
            <div className="detail-label">知识版本</div>
            <div className="detail-value mono text-sm">{overview?.knowledge_version || "-"}</div>
          </div>
          <div className="detail-row">
            <div className="detail-label">数据截至</div>
            <div className="detail-value mono text-sm">{overview?.data_as_of || "-"}</div>
          </div>
        </Card>
      </div>

      {/* 控制表引用 */}
      <Card
        title={
          <span className="flex items-center gap-2">
            <Icon.Event style={{ color: "var(--c-primary-500)" }} />
            控制表引用
          </span>
        }
      >
        <table className="data-table">
          <thead>
            <tr>
              <th>控制表标识</th>
              <th>表格编号</th>
              <th>记录编号</th>
              <th>状态</th>
              <th>说明</th>
            </tr>
          </thead>
          <tbody>
            {sourceStatus?.control_table_refs && Object.entries(sourceStatus.control_table_refs).map(([key, val]) => (
              <tr key={key}>
                <td className="mono text-sm">{key}</td>
                <td className="mono text-sm">{val.table_id || "-"}</td>
                <td className="mono text-sm">{val.record_id || "-"}</td>
                <td>
                  <Badge type={val.event_status === "待确认" ? "warning" : "success"}>
                    {val.event_status || "-"}
                  </Badge>
                </td>
                <td className="text-sm text-muted">{val.note || ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {/* 管理配置注册表（P0-7 恢复 v3.1 四类） */}
      <div style={{ marginTop: "16px" }}>
        <Card
          title={
            <span className="flex items-center gap-2">
              <Icon.Config style={{ color: "var(--c-primary-500)" }} />
              注册与规则表
            </span>
          }
          extra={<Badge type="default" dot>只读展示</Badge>}
        >
          <div className="grid" style={{ gridTemplateColumns: "repeat(4, 1fr)", gap: "12px" }}>
            {(sourceStatus?.admin_config
              ? [
                  { key: "BF_RULE_VERSIONS", label: "规则版本注册", data: sourceStatus.admin_config["BF_RULE_VERSIONS"] },
                  { key: "BF_AGENT_REGISTRY", label: "智能体注册", data: sourceStatus.admin_config["BF_AGENT_REGISTRY"] },
                  { key: "BF_SKILL_REGISTRY", label: "技能注册", data: sourceStatus.admin_config["BF_SKILL_REGISTRY"] },
                  { key: "BF_KNOWLEDGE_REGISTRY", label: "知识库注册", data: sourceStatus.admin_config["BF_KNOWLEDGE_REGISTRY"] },
                ]
              : []
            ).map((item) => {
              const d = item.data || {};
              const refStatus = d.reference_status;
              const detailAccess = d.detail_access;
              return (
                <div
                  key={item.key}
                  style={{
                    padding: "14px",
                    border: "1px solid var(--c-gray-200)",
                    borderRadius: "var(--radius-md)",
                    background: "#fff",
                  }}
                >
                  <div className="flex items-center justify-between mb-2">
                    <div style={{ fontSize: "13px", fontWeight: 600, color: "var(--c-gray-900)" }}>
                      {item.label}
                    </div>
                    <Badge type={d.status === "loaded" ? "success" : d.status === "readonly" ? "info" : "warning"}>
                      {d.status === "loaded" ? "已加载" : d.status === "readonly" ? "只读" : d.status === "pending" ? "待确认" : "未接入"}
                    </Badge>
                  </div>
                  <div className="text-xs text-muted" style={{ marginBottom: "10px" }}>
                    {d.records ?? 0} 条配置记录 · 当前仅用于查看
                  </div>
                  <div className="detail-row">
                    <div className="detail-label" style={{ width: "70px" }}>记录数</div>
                    <div className="detail-value font-medium">{d.records ?? 0} 条</div>
                  </div>
                  <div className="detail-row">
                    <div className="detail-label" style={{ width: "70px" }}>引用状态</div>
                    <div className="detail-value text-sm">
                      {refStatus === "summary_only" ? "仅摘要" : refStatus || "-"}
                    </div>
                  </div>
                  <div className="detail-row">
                    <div className="detail-label" style={{ width: "70px" }}>明细接入</div>
                    <div className="detail-value text-sm">
                      {detailAccess === "not_connected"
                        ? "未接入"
                        : detailAccess === "full" ? "完全接入" : detailAccess || "-"}
                    </div>
                  </div>
                  {d.current_version && (
                    <div className="detail-row">
                      <div className="detail-label" style={{ width: "70px" }}>当前版本</div>
                      <div className="detail-value mono text-sm">{d.current_version}</div>
                    </div>
                  )}
                  {d.agents && Array.isArray(d.agents) && (
                    <div className="detail-row">
                      <div className="detail-label" style={{ width: "70px" }}>Agent 列表</div>
                      <div className="detail-value text-sm">{d.agents.map((agent) => t_field(agent)).join("、")}</div>
                    </div>
                  )}
                  {d.note && (
                    <div style={{ fontSize: "11px", color: "var(--c-gray-500)", marginTop: "8px", lineHeight: 1.5 }}>
                      {d.note}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </Card>
      </div>

      {/* 视图统计 */}
      <div style={{ marginTop: "16px" }}>
        <Card
          title={
            <span className="flex items-center gap-2">
              <Icon.Dashboard style={{ color: "var(--c-primary-500)" }} />
              视图覆盖统计
            </span>
          }
          extra={
            <Badge type="success">{getViewCount()} / 100 个视图已加载</Badge>
          }
        >
          <div className="grid" style={{ gridTemplateColumns: "repeat(6, 1fr)", gap: "10px" }}>
            {getAllRoles().map((role) => {
              const count = getRoleViews(role)?.length || 0;
              return (
                <div key={role} style={{
                  padding: "12px",
                  background: "var(--c-gray-50)",
                  borderRadius: "var(--radius-sm)",
                  textAlign: "center",
                }}>
                  <div style={{ fontSize: "12px", color: "var(--c-gray-500)", marginBottom: "4px" }}>
                    {t_roles(role)}
                  </div>
                  <div style={{ fontSize: "20px", fontWeight: 700, color: "var(--c-gray-900)" }}>
                    {count}
                  </div>
                  <div className="text-xs text-muted">个视图</div>
                </div>
              );
            })}
          </div>

          <div style={{ marginTop: "16px" }}>
            <div style={{ fontSize: "12px", color: "var(--c-gray-500)", marginBottom: "8px" }}>
              时间窗口覆盖
            </div>
            <div className="flex gap-2">
              {getAllTimeWindows().map((tw) => (
                <Badge key={tw} type="success">{t_timeWindow(tw)}</Badge>
              ))}
            </div>
          </div>
        </Card>
      </div>

      {/* 管理员信息 */}
      <div style={{ marginTop: "16px" }}>
        <Collapse
          title={
            <span className="flex items-center gap-2">
              <Icon.Info />
              管理员技术信息
            </span>
          }
          badge={<Badge type="default" dot>管理员专属</Badge>}
        >
          <div className="grid grid-2 gap-3">
            <div>
              <div className="detail-row">
                <div className="detail-label">载荷版本</div>
                <div className="detail-value mono text-sm">Overview {overview?.payload_version || "-"}</div>
              </div>
              <div className="detail-row">
                <div className="detail-label">数据集编号</div>
                <div className="detail-value mono text-sm">{overview?.dataset_id || "-"}</div>
              </div>
              <div className="detail-row">
                <div className="detail-label">数据性质</div>
                <div className="detail-value mono text-sm">{overview?.data_nature || "-"}</div>
              </div>
              <div className="detail-row">
                <div className="detail-label">生成时间</div>
                <div className="detail-value mono text-sm">{overview?.payload_generated_at || "-"}</div>
              </div>
            </div>
            <div>
              <div className="detail-row">
                <div className="detail-label">黄金事件时间</div>
                <div className="detail-value mono text-sm">{overview?.golden_event_time || "-"}</div>
              </div>
              <div className="detail-row">
                <div className="detail-label">事件摘要数</div>
                <div className="detail-value mono text-sm">{getEventSummaries()?.length || 0} 条</div>
              </div>
              <div className="detail-row">
                <div className="detail-label">待确认数</div>
                <div className="detail-value mono text-sm">{getPendingConfirmations()?.length || 0} 条</div>
              </div>
              <div className="detail-row">
                <div className="detail-label">数据源数</div>
                <div className="detail-value mono text-sm">{dataSources?.length || 0} 个</div>
              </div>
            </div>
          </div>
        </Collapse>
      </div>
    </div>
  );
}

// 导出到全局
Object.assign(window, {
  DashboardPage,
  EventsPage,
  GovernancePage,
  ConfigPage,
});
