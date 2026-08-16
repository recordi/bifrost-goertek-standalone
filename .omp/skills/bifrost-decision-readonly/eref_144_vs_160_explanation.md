# EvidenceRef 144 次与 160 次的统计范围差异说明

## 结论

- **160** = Event v1.4 载荷 `roles` 中所有 `evidence_refs` 条目的总出现次数（`evidence_ref_summary.occurrence_count`）
- **144** = 160 减去 `tasks`(9) 和 `decisions_required`(7) 的 evidence_refs 条目数 = kpis + charts + role-level + alerts

## 详细统计

Event v1.4 载荷 `roles` 数组中各 JSON 路径的 `evidence_refs` 条目计数：

| JSON 路径 | evidence_refs 条目数 | 说明 |
|-----------|---------------------|------|
| `roles[].kpis[].evidence_refs` | 66 | 各角色 KPI 指标的证据引用 |
| `roles[].charts[].evidence_refs` | 40 | 各角色图表的证据引用 |
| `roles[].evidence_refs`（角色级） | 29 | 角色级别的直接证据引用 |
| `roles[].alerts[].evidence_refs` | 9 | 各角色告警的证据引用 |
| `roles[].tasks[].evidence_refs` | 9 | 各角色待办任务的证据引用 |
| `roles[].decisions_required[].evidence_refs` | 7 | 各角色待决策事项的证据引用 |
| **合计** | **160** | `evidence_ref_summary.occurrence_count` |

## 144 的来源

144 = 160 - 9 (tasks) - 7 (decisions_required) = 66 + 40 + 29 + 9 = **144**

144 的统计范围排除了 `tasks` 和 `decisions_required` 两类 evidence_refs，仅涵盖：
- KPI 指标引用 (66)
- 图表引用 (40)
- 角色级引用 (29)
- 告警引用 (9)

## 使用场景

- **160** 用于 EvidenceRef 完整性校验：所有 `evidence_ref_summary.occurrence_count` 声明的引用都必须有完整的物理解析（source_table + record_key + record_id）
- **144** 用于业务回答验证：`validate_evidence_contract()` 在校验 `metrics`/`causes`/`recommended_actions` 时，引用范围对应 KPI + 图表 + 角色级 + 告警，不包括待办任务和待决策事项（这两类不属于业务回答的指标证据）

## 去重统计

- `evidence_ref_summary.deduplicated_physical_record_count` = **27**
- 160 个 evidence_refs 条目去重后对应 27 个不同的物理记录键（`source_table:record_id`）
- 所有 160 个引用都有完整的物理解析，无缺失

## Overview v2.1 载荷

Overview 载荷的 `view_snapshots` 中也有 evidence_refs 条目，总计约 100 个，与 Event 载荷的 160/144 是独立统计。
