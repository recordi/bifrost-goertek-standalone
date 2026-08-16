"""
BIFROST 生产诊断只读分析 — 常量与语义字段定义
logical_version: 0.1.2

本模块集中声明生产诊断可识别的语义字段、OEE 直接驱动白名单、
停机组分类与输出合同元信息。生产代码不硬编码任何业务数值，
所有业务值均从 BIFROST_DECISION_INPUT_v0.1 的 normalized_facts 动态读取。

v0.1.2 变更（04D.3-PROD）：
- SPECIALIST_CONTRACT_VERSION 升级为 v0.1.3（字段级 EvidenceRef 收口版）
- SPECIALIST_LOGICAL_VERSION 升级为 0.1.2
- evidence_refs 改用 EVREF-v1:<SHA256>（字段事实级，由共享 build_canonical_evidence_ref 生成）
- data_gaps 使用共享 merge_data_gaps 归并，输出 affected_record_count/occurrence_count/sample_source_locators
- 高风险动作存在时，非 blocked 结果必须为 needs_confirmation
- 删除所有占位证据（EV:no_evidence、EV:*:no_provenance、裸 semantic_record_key 等）
"""

# ---------- 输出合同元信息 ----------
SPECIALIST_CONTRACT_NAME = "BIFROST_SPECIALIST_RESULT_v0.1"
SPECIALIST_CONTRACT_VERSION = "BIFROST-SPECIALIST-RESULT-v0.1.3"
SPECIALIST_TYPE = "production"
SPECIALIST_LOGICAL_VERSION = "0.1.2"

# ---------- 输入合同元信息 ----------
INPUT_CONTRACT_NAME = "BIFROST_DECISION_INPUT_v0.1"
INPUT_CONTRACT_VERSION = "BIFROST-DECISION-INPUT-v0.1"

# 仅消费 value_consumption_status=usable 的事实
USABLE_STATUS = "usable"

# 输入 validation.status 不得为以下值
BLOCKED_VALIDATION_STATUSES = {"failed", "blocked"}

# ---------- OEE 直接驱动白名单（生产专业规则 §1）----------
# 只有这三项可作为 OEE 直接驱动因子
OEE_DIRECT_DRIVERS = ("availability", "performance_rate", "quality_factor")

# OEE 三因子齐全时方可复算
OEE_RECOMPUTE_REQUIRED_FACTORS = ("availability", "performance_rate", "quality_factor")

# oee_source 与 oee_recomputed 独立展示，不得互相覆盖
OEE_SOURCE_FIELD = "oee_source"
OEE_RECOMPUTED_FIELD = "oee_recomputed"
CAN_RECOMPUTE_OEE_FIELD = "can_recompute_oee"

# ---------- 停机相关字段 ----------
UNPLANNED_DOWNTIME_FIELD = "unplanned_downtime_minutes"
PLANNED_DOWNTIME_FIELD = "planned_downtime_minutes"
DOWNTIME_EVENT_COUNT_FIELD = "downtime_event_count"
DOWNTIME_GROUP_FIELD = "downtime_group"          # FAILURE / SETUPS-CHANGEOVERS / MATERIALS / OPERATIONAL
DOWNTIME_REASON_FIELD = "downtime_reason"
MAX_SINGLE_FAULT_FIELD = "max_single_fault_minutes"

# 物料缺口字段（不得进入 OEE 直接原因）
MATERIAL_GAP_QTY_FIELD = "material_gap_qty"
MATERIAL_GAP_MATERIAL_FIELD = "material_gap_material_code"
MATERIAL_GAP_ENTITY = "material_detail"

# 停机组中与物料相关的组（需关联物化后方可作为停机证据）
MATERIALS_DOWNTIME_GROUP = "MATERIALS"

# 关联物化状态字段
RELATION_MATERIALIZATION_FIELD = "relation_materialization_status"
MATERIALIZED_STATUS = "materialized"

# ---------- 产量/质量字段 ----------
TOTAL_OUTPUT_FIELD = "total_output"
GOOD_OUTPUT_FIELD = "good_output"
DEFECT_TOTAL_FIELD = "defect_total"
YIELD_RECOMPUTE_FIELD = "yield_recompute"
SOURCE_QUALITY_RATE_FIELD = "source_quality_rate"
OEE_QUALITY_FACTOR_FIELD = "oee_quality_factor"

# ---------- MTBF/MTTR 字段（缺证据时不得计算）----------
EQUIPMENT_ID_FIELD = "equipment_id"
FAULT_CODE_FIELD = "fault_code"
REPAIR_WORK_ORDER_FIELD = "repair_work_order"
MTBF_FIELD = "mtbf"
MTTR_FIELD = "mttr"

# ---------- 换产字段 ----------
CHANGEOVER_FLAG_FIELD = "changeover_event_flag"
CHANGEOVER_DURATION_FIELD = "changeover_duration_minutes"

# ---------- 班次/趋势字段 ----------
SHIFT_ID_FIELD = "shift_id"
SHIFT_DATE_FIELD = "shift_date"
SHIFT_SEQUENCE_FIELD = "shift_sequence"
LINE_ID_FIELD = "line_id"

# 趋势判定所需的最小时间/顺序字段
TREND_REQUIRED_FIELDS = (SHIFT_DATE_FIELD, SHIFT_SEQUENCE_FIELD)
TREND_MIN_RECORDS = 2

# ---------- 风险等级 ----------
RISK_LEVEL_FIELD = "risk_level"
SEVERITY_UNKNOWN = "unknown"
MISSING_SEVERITY_RULE_CODE = "missing_severity_rule"

# ---------- 高风险动作 ----------
HIGH_RISK_RESCHEDULE_ACTION = "adjust_production_schedule"
PROHIBITED_AUTO_EXECUTE = True

# 生产诊断期望的证据字段全集（用于 confidence 覆盖率计算）
# 覆盖率 = 已提供且 usable 的证据字段数 / 期望证据字段数
PRODUCTION_EVIDENCE_FIELDS = (
    OEE_SOURCE_FIELD,
    "availability",
    "performance_rate",
    "quality_factor",
    UNPLANNED_DOWNTIME_FIELD,
    TOTAL_OUTPUT_FIELD,
    GOOD_OUTPUT_FIELD,
    DEFECT_TOTAL_FIELD,
)

# ---------- 状态枚举（v0.1.3 共享合同）----------
STATUS_COMPLETED = "completed"
STATUS_WARNING = "warning"
STATUS_BLOCKED = "blocked"
STATUS_NEEDS_CONFIRMATION = "needs_confirmation"

# ---------- data_gap value_consumption_status 枚举 ----------
VCS_MISSING = "missing"
VCS_UNUSABLE = "unusable"
VCS_BLOCKED = "blocked"

# ---------- 不产出 metric 的字段（元数据/控制字段，非度量指标）----------
NON_METRIC_FIELDS = frozenset({
    RELATION_MATERIALIZATION_FIELD, CAN_RECOMPUTE_OEE_FIELD,
    EQUIPMENT_ID_FIELD, FAULT_CODE_FIELD, REPAIR_WORK_ORDER_FIELD,
    "severity_rule_id", "risk_level",
    LINE_ID_FIELD, SHIFT_ID_FIELD, "source_shift_id",
    SHIFT_DATE_FIELD, SHIFT_SEQUENCE_FIELD,
    DOWNTIME_GROUP_FIELD, DOWNTIME_REASON_FIELD,
    MATERIAL_GAP_MATERIAL_FIELD,
})
