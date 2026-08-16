/* ===== BIFROST 中文标签字典 (i18n Layer) v3.2 =====
   纯表现层映射，不改数据合同。
   内部值 → 用户展示名
*/

const BIFROST_I18N = {
  // ===== 角色 =====
  roles: {
    factory: "厂长",
    line: "线长",
    quality: "质量",
    equipment: "设备",
    process: "工艺",
    supply: "供应链",
  },

  // ===== 范围 / 产线 =====
  scope: {
    ALL_LINES: "全部产线",
    "LINE-S01": "一号产线",
    "LINE-S02": "二号产线",
    "LINE-S03": "三号产线",
  },

  lineFullNames: {
    "LINE-S01": "一号产线（LINE-S01）",
    "LINE-S02": "二号产线（LINE-S02）",
    "LINE-S03": "三号产线（LINE-S03）",
  },

  // ===== 时间窗口 =====
  timeWindows: {
    last_7_shifts: "最近 7 个班次",
    last_30_shifts: "最近 30 个班次",
    pre_improvement: "改善前",
    post_improvement: "改善后",
    full_history: "全部历史",
  },

  // ===== KPI / 指标 =====
  metrics: {
    TOTAL_OUTPUT: "总产量",
    AVAILABILITY: "开动率",
    PERFORMANCE: "性能率",
    QUALITY: "良品率",
    OEE: "综合设备效率（OEE）",
    MTBF: "平均故障间隔时间（MTBF）",
    MTTR: "平均修复时间（MTTR）",
    SPC: "统计过程控制（SPC）",
    Cpk: "过程能力指数（Cpk）",
    UPH: "小时产量（UPH）",
    YIELD: "良率",
    DEFECT_RATE: "不良率",
    DOWNTIME: "停机时长",
    DOWNTIME_MIN: "停机时长",
    CHANGEOVER_OVERTIME: "换产超时",
    MATERIAL_GAP_COUNT: "物料缺口项数",
    MATERIAL_GAP_QTY: "缺料数量",
    FREEZE_COUNT: "冻结批次数",
  },

  fields: {
    availability: "开动率",
    performance_rate: "性能率",
    quality_rate: "质量率",
    yield_rate: "良率",
    total_output: "总产量",
    actual_output: "实际产量",
    good_output: "良品数",
    defect_total: "不良总数",
    oee_source: "来源 OEE",
    oee_recomputed: "复算 OEE",
    production_line: "产线",
    line_id: "产线编号",
    shift_date: "生产日期",
    production_date: "生产日期",
    phase: "改善阶段",
    spc_measurement_points: "SPC 测量点",
    sample_rule: "抽样规则",
    equipment_id: "设备编号",
    material_id: "物料编码",
    blocked_gap_count: "受阻缺口数",
  },

  metricShort: {
    TOTAL_OUTPUT: "总产量",
    AVAILABILITY: "开动率",
    PERFORMANCE: "性能率",
    QUALITY: "良品率",
    OEE: "OEE",
    MTBF: "MTBF",
    MTTR: "MTTR",
    SPC: "SPC",
    Cpk: "Cpk",
    UPH: "UPH",
  },

  // ===== 数据性质 / 连接状态 =====
  dataNature: {
    snapshot: "本地演示数据",
    disabled: "AI 尚未连接",
    readonly: "只读模式",
    not_tested: "未检测",
    BLOCKED_EXTERNAL: "等待外部接入",
    loaded: "已加载",
    pending: "待处理",
  },

  // ===== 数据连接模式 =====
  connectionMode: {
    data_mode: {
      snapshot: "本地演示数据",
      live: "实时数据接入",
    },
    aily_mode: {
      disabled: "AI 尚未连接",
      connected: "AI 已连接",
    },
    writeback_mode: {
      readonly: "只读模式",
      enabled: "可写回",
    },
    bitable_status: {
      loaded: "多维表格已连接",
      disconnected: "多维表格未连接",
      not_connected: "未接入实时多维表格（当前使用本地快照）",
      connected: "已接入实时多维表格",
    },
  },

  // ===== 六类缺陷 =====
  defectTypes: {
    missing: "缺失",
    duplicate: "重复",
    outlier: "异常值",
    format_inconsistent: "格式不一致",
    format: "格式不一致",
    logic_conflict: "逻辑冲突",
    logic: "逻辑冲突",
    unit_inconsistent: "单位不一致",
    duplicate_key: "业务键重复",
    temporal_gap: "时间字段缺失",
    referential_broken: "关联引用失败",
    business_exception: "业务规则异常",
    stale: "时效滞后",
    field_mapping: "字段映射",
    data_gap: "数据缺口",
    version: "版本治理",
    binding: "关联绑定",
  },

  defectTypeDescriptions: {
    missing: "必要字段为空或记录不存在，可能导致计算缺项",
    duplicate: "同一业务实体有多条重复记录",
    outlier: "数值超出合理范围或统计异常",
    format_inconsistent: "相同含义字段格式不统一",
    logic_conflict: "字段间存在业务逻辑矛盾",
    stale: "数据长时间未更新，时效不足",
    field_mapping: "业务字段尚未完成统一映射，可能影响跨表关联和规则计算",
    data_gap: "当前数据源缺少该分析所需的字段，不能据此推断业务异常",
    version: "规则、载荷或知识版本之间需要保持一致并可追溯",
    binding: "决策、确认、任务或证据之间的绑定关系需要校验",
  },

  defectRuleDescriptions: {
    missing: "检查必填字段是否为空，以及主键记录是否存在",
    duplicate: "按业务主键检查重复记录和重复采集",
    outlier: "按字段类型、范围和统计分布检查异常值",
    format_inconsistent: "检查日期、编码、单位和枚举格式是否统一",
    logic_conflict: "检查跨字段业务时序和数量守恒关系",
    stale: "按数据更新时间和业务时效阈值检查滞后数据",
    field_mapping: "检查来源字段到业务语义字段的映射覆盖率",
    data_gap: "检查当前分析所需字段是否存在且达到最小样本量",
    version: "检查规则、知识、载荷版本是否可追溯",
    binding: "检查事件、任务、确认和证据是否一对一绑定",
  },

  // ===== 严重程度 =====
  severity: {
    critical: "严重",
    high: "高",
    medium: "中",
    low: "低",
  },

  // ===== 状态 =====
  status: {
    待确认: "待确认",
    已确认: "已确认",
    处理中: "处理中",
    已关闭: "已关闭",
    open: "未解决",
    resolved: "已修复",
    investigating: "排查中",
  },

  // ===== 事件类型 =====
  alertTypes: {
    oee_drop: "OEE 下降",
    quality_issue: "质量异常",
    downtime: "设备停机",
    material_shortage: "物料短缺",
    process_deviation: "工艺偏移",
  },

  // ===== 页面标题 =====
  pages: {
    dashboard: "看板中心",
    events: "事件中心",
    governance: "数据治理",
    config: "管理配置",
    ai: "AI 助手",
  },

  // ===== AI 状态机 =====
  aiStatus: {
    ready: "准备就绪",
    thinking: "正在理解问题",
    analyzing: "分析执行中",
    awaiting_confirm: "等待人工确认",
    completed: "已完成",
    failed: "执行失败",
    blocked_external: "等待外部接入",
    disabled: "AI 尚未连接",
  },

  // ===== 快捷问题（按角色） =====
  quickQuestions: {
    factory: [
      "比较三条产线并指出最需处理的问题",
      "本周最大的三个风险是什么",
      "需要我拍板的决策有哪些",
    ],
    line: [
      "解释本线 OEE 下降原因并给出今天的动作",
      "今天有哪些待处理异常",
      "本班产量和良率预计能否达标",
    ],
    quality: [
      "分析主要缺陷并创建复检任务草稿",
      "当前冻结的批次有哪些",
      "最近质量趋势是否在恶化",
    ],
    equipment: [
      "汇总停机原因并指出缺少的维修证据",
      "MTBF 和 MTTR 的最新情况",
      "哪些设备需要预防性维护",
    ],
    process: [
      "检查换产是否超时及适用的规则版本",
      "SPC 控制图有无异常点",
      "Cpk 是否达标，哪些工序偏弱",
    ],
    supply: [
      "评估缺料对当前工单的影响",
      "齐套率最低的工单是哪些",
      "冻结对交付承诺有什么影响",
    ],
  },

  // ===== 通用系统标签 =====
  system: {
    role: "当前角色",
    scope: "分析范围",
    timeWindow: "时间范围",
    currentEvent: "当前事件",
    systemStatus: "系统状态",
    dataSource: "数据来源",
    ruleVersion: "规则版本",
    datasetId: "数据集编号",
    lastUpdated: "最后更新",
    evidenceRef: "证据引用",
    viewKey: "视图编号",
  },
};

// 便捷查找函数
function t_roles(key) {
  return BIFROST_I18N.roles[key] || key;
}
function t_scope(key) {
  return BIFROST_I18N.scope[key] || key;
}
function t_timeWindow(key) {
  const dynamicLabel = window.BIFROST_DATA?.overview?.view_coverage?.window_labels?.[key];
  return dynamicLabel || BIFROST_I18N.timeWindows[key] || key;
}
function t_metric(key, full = false) {
  if (full) return BIFROST_I18N.metrics[key] || key;
  return BIFROST_I18N.metricShort[key] || BIFROST_I18N.metrics[key] || key;
}
function t_field(key) {
  return BIFROST_I18N.fields[key] || BIFROST_I18N.metrics[key] || key;
}
function t_line(key) {
  return BIFROST_I18N.lineFullNames[key] || BIFROST_I18N.scope[key] || key;
}
function t_defect(key) {
  const aliases = { format: "format_inconsistent", logic: "logic_conflict" };
  const normalized = aliases[key] || key;
  return BIFROST_I18N.defectTypes[normalized] || key;
}
function t_severity(key) {
  return BIFROST_I18N.severity[key] || key;
}
function t_status(key) {
  return BIFROST_I18N.status[key] || key;
}
function t_alertType(key) {
  return BIFROST_I18N.alertTypes[key] || key;
}
function t_page(key) {
  return BIFROST_I18N.pages[key] || key;
}
function t_aiStatus(key) {
  return BIFROST_I18N.aiStatus[key] || key;
}
function t_dataNature(key) {
  return BIFROST_I18N.dataNature[key] || key;
}
function t_sys(key) {
  return BIFROST_I18N.system[key] || key;
}

// 导出到全局
Object.assign(window, {
  BIFROST_I18N,
  t_roles,
  t_scope,
  t_timeWindow,
  t_metric,
  t_field,
  t_line,
  t_defect,
  t_severity,
  t_status,
  t_alertType,
  t_page,
  t_aiStatus,
  t_dataNature,
  t_sys,
});
