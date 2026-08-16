/* ===== BIFROST 主应用 v3.2 =====
   应用外壳：侧边导航 + 顶部栏 + 二级筛选 + AI 抽屉
*/

const { useState, useEffect, useMemo, useRef } = React;

function App() {
  const [loading, setLoading] = useState(true);
  const [currentPage, setCurrentPage] = useState("dashboard");
  const [role, setRole] = useState("factory");
  const [timeWindow, setTimeWindow] = useState("last_7_shifts");
  const [scope, setScope] = useState("ALL_LINES");
  const [selectedEventId, setSelectedEventId] = useState(null);
  const [aiDrawerOpen, setAiDrawerOpen] = useState(false);
  const [sysStatusOpen, setSysStatusOpen] = useState(false);
  const [, setDataRevision] = useState(0);
  const sysStatusRef = useRef(null);

  // 加载数据
  useEffect(() => {
    loadBifrostData().then(() => {
      const windows = getAllTimeWindows();
      const lines = getAllLines();
      setTimeWindow((current) => windows.includes(current) ? current : (windows[0] || "full_history"));
      setScope(() => {
        const preferred = resolveScopeForRole(role, "ALL_LINES");
        return preferred === "ALL_LINES" || lines.includes(preferred) ? preferred : (lines[0] || "ALL_LINES");
      });
      setLoading(false);
    });
  }, []);

  useEffect(() => {
    const refresh = () => setDataRevision((revision) => revision + 1);
    window.addEventListener("bifrost:data-updated", refresh);
    return () => window.removeEventListener("bifrost:data-updated", refresh);
  }, []);

  // 点击外部关闭系统状态面板
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (sysStatusRef.current && !sysStatusRef.current.contains(e.target)) {
        setSysStatusOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // 页面切换时关闭 AI 抽屉的状态重置等
  const handlePageChange = (page) => {
    setCurrentPage(page);
    if (page === "ai") {
      setAiDrawerOpen(true);
    }
  };

  const handleAskAI = () => {
    setAiDrawerOpen(true);
  };

  // AI 看板意图：先切换到用户要求的业务视图，再把同一上下文交给问答链路。
  // 这是导航意图，不修改数据、指标或规则；无法识别的内容保持当前视图。
  const handleAiViewIntent = (query) => {
    const text = String(query || "").toLowerCase();
    const nextWindow = /七天|7天|七个班|7个班|一周|本周|最近7/.test(text)
      ? "last_7_shifts"
      : (/三十天|30天|30个班|一个月|最近30/.test(text) ? "last_30_shifts" : null);
    const roleRules = [
      [/厂长|全厂|所有产线|总体/, "factory"],
      [/线长|产线|生产线/, "line"],
      [/质量|良率|不良|缺陷/, "quality"],
      [/设备|停机|故障|维修/, "equipment"],
      [/工艺|换产|工序|过程稳定/, "process"],
      [/供应链|物料|缺料|库存|到货/, "supply"],
    ];
    const nextRole = roleRules.find(([pattern]) => pattern.test(text))?.[1] || null;
    const nextPage = /事件|告警|异常/.test(text)
      ? "events"
      : (/治理|数据质量|数据健康/.test(text) ? "governance" : "dashboard");
    const lineMatch = text.match(/(?:一|二|三|1|2|3)号?(?:产线|线)/);
    let nextScope = null;
    if (lineMatch) {
      const ordinal = lineMatch[0].replace(/号?(?:产线|线)/, "");
      const index = { "一": 0, "二": 1, "三": 2, "1": 0, "2": 1, "3": 2 }[ordinal];
      const lines = getAllLines();
      nextScope = lines[index] || null;
    }
    if (!nextRole && !nextWindow && !nextScope && nextPage === "dashboard" && !/趋势|看板|图表|分析/.test(text)) return;
    const resolvedRole = nextRole || role;
    setRole(resolvedRole);
    setScope(resolveScopeForRole(resolvedRole, nextScope || scope));
    if (nextWindow && getAllTimeWindows().includes(nextWindow)) setTimeWindow(nextWindow);
    setCurrentPage(nextPage);
  };

  // 角色切换时按数据合同中的角色权限恢复范围，避免遗留上一角色的产线范围
  const handleRoleChange = (newRole) => {
    setRole(newRole);
    setScope(resolveScopeForRole(newRole, scope));
  };

  // AI 上下文
  const aiContext = useMemo(
    () => ({
      role,
      scope,
      timeWindow,
      eventId: currentPage === "events" ? selectedEventId : null,
    }),
    [role, scope, timeWindow, currentPage, selectedEventId]
  );

  // 连接模式状态
  const conn = useMemo(() => {
    const s = getSourceStatus();
    return s?.connection_mode || {};
  }, [loading]);

  // 系统状态汇总（顶部按钮显示）
  const sysStatusSummary = useMemo(() => {
    const items = [];
    if (conn.data_mode === "snapshot") items.push("演示数据");
    if (conn.aily_mode === "disabled") items.push("AI未连");
    if (conn.writeback_mode === "readonly") items.push("只读");
    return items.length > 0 ? items.join(" · ") : "运行正常";
  }, [conn]);

  // 页面标题
  const pageTitle = useMemo(() => {
    if (currentPage === "dashboard") return "看板中心";
    if (currentPage === "events") return "事件中心";
    if (currentPage === "governance") return "数据治理";
    if (currentPage === "config") return "管理配置";
    return "";
  }, [currentPage]);

  if (loading) {
    return (
      <div style={{
        width: "100vw", height: "100vh",
        display: "flex", alignItems: "center", justifyContent: "center",
        background: "var(--c-primary)",
        color: "#fff",
        flexDirection: "column",
        gap: "16px",
      }}>
        <div style={{
          width: "48px", height: "48px",
          borderRadius: "12px",
          background: "var(--c-accent)",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontWeight: 700, fontSize: "20px",
          color: "#1a1f29",
        }}>
          B
        </div>
        <div style={{ fontSize: "16px", fontWeight: 600 }}>BIFROST 智能看板</div>
        <div style={{ fontSize: "13px", color: "rgba(255,255,255,0.6)" }}>正在加载数据...</div>
      </div>
    );
  }

  return (
    <div className="app-shell">
      {/* 侧边导航 */}
      <aside className="sidebar">
        <div className="sidebar-logo">
          <div className="sidebar-logo-icon">B</div>
          <span>BIFROST</span>
        </div>

        <nav className="sidebar-nav">
          <button
            className={`sidebar-nav-item ${currentPage === "dashboard" ? "active" : ""}`}
            onClick={() => handlePageChange("dashboard")}
          >
            <span className="sidebar-nav-icon"><Icon.Dashboard /></span>
            看板中心
          </button>
          <button
            className={`sidebar-nav-item ${currentPage === "events" ? "active" : ""}`}
            onClick={() => handlePageChange("events")}
          >
            <span className="sidebar-nav-icon"><Icon.Event /></span>
            事件中心
            <Badge type="danger" dot style={{ marginLeft: "auto" }}>
              11
            </Badge>
          </button>
          <button
            className={`sidebar-nav-item ${currentPage === "governance" ? "active" : ""}`}
            onClick={() => handlePageChange("governance")}
          >
            <span className="sidebar-nav-icon"><Icon.Governance /></span>
            数据治理
          </button>
          <button
            className={`sidebar-nav-item ${currentPage === "config" ? "active" : ""}`}
            onClick={() => handlePageChange("config")}
          >
            <span className="sidebar-nav-icon"><Icon.Config /></span>
            管理配置
          </button>

          <button
            className="sidebar-nav-item ai-entry"
            onClick={() => setAiDrawerOpen(true)}
          >
            <span className="sidebar-nav-icon"><Icon.AI /></span>
            AI 助手
          </button>
        </nav>

        <div className="sidebar-footer">
          v3.2.1 · 基线版
        </div>
      </aside>

      {/* 主内容区 */}
      <main className="main-content">
        {/* 顶部栏 - 第一行 */}
        <header className="topbar">
          <div className="topbar-title">
            {pageTitle}
          </div>

          <div className="topbar-breadcrumb">
            <span style={{ color: "var(--c-gray-700)" }}>{t_roles(role)}</span>
            <Icon.ChevronRight style={{ width: 12, height: 12 }} />
            <span>{scope === "ALL_LINES" ? t_scope(scope) : t_line(scope)}</span>
          </div>

          <div className="topbar-spacer" />

          <div className="topbar-actions">
            {/* 问 AI 主按钮 */}
            <button className="btn btn-accent" onClick={handleAskAI}>
              <Icon.AI />
              问 AI
            </button>

            {/* 通知 */}
            <button className="icon-btn" title="通知">
              <Icon.Bell />
            </button>

            {/* 帮助 */}
            <button className="icon-btn" title="帮助">
              <Icon.Help />
            </button>

            {/* 系统状态 */}
            <div ref={sysStatusRef} style={{ position: "relative" }}>
              <button
                className="btn btn-default btn-sm"
                onClick={() => setSysStatusOpen(!sysStatusOpen)}
                title="系统状态"
              >
                <Icon.Status />
                <span className="text-xs" style={{ color: "var(--c-gray-600)" }}>
                  {sysStatusSummary}
                </span>
                <Icon.ChevronDown style={{ width: 10, height: 10 }} />
              </button>
              {sysStatusOpen && <SystemStatusPanel onClose={() => setSysStatusOpen(false)} />}
            </div>
          </div>
        </header>

        {BIFROST_DATA.runtime_mode === "adapter-test" && (
          <div style={{ padding: "8px 24px", background: "#fff7e6", color: "#ad6800", borderBottom: "1px solid #ffd591", fontSize: "12px" }}>
            适配器测试模式：数据来自本地只读辅助分析模块，不代表企业生产数据；高风险动作不可执行。
          </div>
        )}

        {/* 二级导航 / 筛选栏 - 第二行 */}
        {currentPage === "dashboard" && (
          <div className="subnav">
            <div className="subnav-group">
              <span className="subnav-group-label">角色</span>
              <Segmented
                value={role}
                onChange={handleRoleChange}
                items={getAllRoles().map((r) => ({ value: r, label: t_roles(r) }))}
              />
            </div>

            <div className="subnav-group">
              <span className="subnav-group-label">时间范围</span>
              <Segmented
                value={timeWindow}
                onChange={setTimeWindow}
                items={getAllTimeWindows().map((tw) => ({ value: tw, label: t_timeWindow(tw) }))}
              />
            </div>

            {role === "factory" ? (
              <div className="subnav-group" style={{ marginLeft: "auto" }}>
                <span className="subnav-group-label">产线</span>
                <button
                  className="btn btn-default btn-sm"
                  style={{ fontWeight: 500 }}
                >
                  {t_scope("ALL_LINES")} <Icon.ChevronDown style={{ width: 12, height: 12, marginLeft: "4px" }} />
                </button>
              </div>
            ) : (
              <div className="subnav-group" style={{ marginLeft: "auto" }}>
                <span className="subnav-group-label">产线</span>
                <Segmented
                  value={resolveScopeForRole(role, scope)}
                  onChange={(nextScope) => setScope(resolveScopeForRole(role, nextScope))}
                  items={getAllowedLinesForRole(role).map((l) => ({ value: l, label: getLineLabel(l, getViewSnapshot(`line|${l}|${timeWindow}`)) }))}
                />
                {role === "line" && <>
                  <span className="text-xs text-muted" title="线长角色仅授权三号产线">仅查看三号产线</span>
                  <button className="btn btn-ghost btn-sm" onClick={() => { handleRoleChange("factory"); }}>返回全厂</button>
                </>}
              </div>
            )}
          </div>
        )}

        {currentPage === "events" && (
          <div className="subnav">
            <div className="subnav-group">
              <span className="subnav-group-label">角色</span>
              <Segmented
                value={role}
                onChange={handleRoleChange}
                items={getAllRoles().map((r) => ({ value: r, label: t_roles(r) }))}
              />
            </div>
            {role !== "factory" && (
              <div className="subnav-group">
                <span className="subnav-group-label">产线</span>
                <Segmented
                  value={resolveScopeForRole(role, scope)}
                  onChange={(nextScope) => setScope(resolveScopeForRole(role, nextScope))}
                  items={getAllowedLinesForRole(role).map((line) => ({ value: line, label: getLineLabel(line, getViewSnapshot(`line|${line}|${timeWindow}`)) }))}
                />
                {role === "line" && <span className="text-xs text-muted" title="线长角色仅授权三号产线">仅查看三号产线</span>}
              </div>
            )}
            <div className="subnav-group" style={{ marginLeft: "auto" }}>
              <button className="btn btn-default btn-sm">
                <Icon.Refresh />
                刷新
              </button>
              <button className="btn btn-default btn-sm">
                全部状态
                <Icon.ChevronDown style={{ width: 12, height: 12, marginLeft: "4px" }} />
              </button>
            </div>
          </div>
        )}

        {currentPage === "governance" && (
          <div className="subnav">
            <div className="subnav-group">
              <span className="subnav-group-label">视图</span>
              <Segmented
                value="overview"
                onChange={() => {}}
                items={[
                  { value: "overview", label: "总览" },
                  { value: "defects", label: "缺陷详情" },
                  { value: "rules", label: "检测规则" },
                ]}
              />
            </div>
            <div className="subnav-group" style={{ marginLeft: "auto" }}>
              <span className="text-xs text-muted">
                <Icon.Clock style={{ width: 12, height: 12, verticalAlign: "middle", marginRight: "4px" }} />
                最近检测：以数据源元数据为准
              </span>
            </div>
          </div>
        )}

        {currentPage === "config" && (
          <div className="subnav">
            <div className="subnav-group">
              <span className="subnav-group-label">配置项</span>
              <Segmented
                value="data"
                onChange={() => {}}
                items={[
                  { value: "data", label: "数据源" },
                  { value: "rules", label: "规则管理" },
                  { value: "roles", label: "权限角色" },
                  { value: "system", label: "系统设置" },
                ]}
              />
            </div>
          </div>
        )}

        {/* 页面内容 */}
        {currentPage === "dashboard" && (
          <DashboardPage
            role={role}
            setRole={handleRoleChange}
            timeWindow={timeWindow}
            setTimeWindow={setTimeWindow}
            scope={scope}
            setScope={setScope}
            onAskAI={handleAskAI}
            onNavigate={handlePageChange}
          />
        )}
        {currentPage === "events" && (
          <EventsPage
            role={role}
            setRole={handleRoleChange}
            timeWindow={timeWindow}
            setTimeWindow={setTimeWindow}
            scope={scope}
            setScope={setScope}
            selectedEventId={selectedEventId}
            onEventChange={setSelectedEventId}
            onAskAI={handleAskAI}
          />
        )}
        {currentPage === "governance" && <GovernancePage />}
        {currentPage === "config" && <ConfigPage />}
      </main>

      {/* AI 助手抽屉 */}
      <AIDrawer
        open={aiDrawerOpen}
        onClose={() => setAiDrawerOpen(false)}
        context={aiContext}
        role={role}
        onViewIntent={handleAiViewIntent}
      />
    </div>
  );
}

// 挂载
const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
