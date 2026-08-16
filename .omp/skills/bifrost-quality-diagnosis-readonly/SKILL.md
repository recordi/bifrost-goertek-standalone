---
name: bifrost-quality-diagnosis-readonly
description: "BIFROST质量诊断只读Skill。消费 BIFROST_DECISION_INPUT_v0.1，输出 BIFROST_SPECIALIST_RESULT_v0.1.3，执行不良守恒、良率、质量冻结和数据门控分析。没有测量点与规格限时禁止 SPC/Cpk；高风险动作只生成待人工确认草稿；不写回业务数据。"
---
# bifrost-quality-diagnosis-readonly

**logical_version: 0.1.2**
**output_contract: BIFROST_SPECIALIST_RESULT_v0.1.3**
**stage: LOCALLY_VALIDATED_NOT_DEPLOYED**

## 用途

BIFROST 质量诊断只读分析 Skill。消费 `BIFROST_DECISION_INPUT_v0.1`，输出 `BIFROST_SPECIALIST_RESULT_v0.1.3`，供决策编排智能体消费。

本阶段只读、不执行任何业务动作。

## 链路

```
语义数据面ZIP
→ bifrost-semantic-consumer-readonly v0.1.1
→ BIFROST_DECISION_INPUT_v0.1
→ bifrost-quality-diagnosis-readonly v0.1.2
→ BIFROST_SPECIALIST_RESULT_v0.1.3
→ 决策编排智能体
```

## 10 个确定性能力

| # | 能力 | 说明 |
|---|------|------|
| 1 | `validate_quality_input_contract` | 验证输入合同（contract_name/version、source_write_performed、actor_can_execute、validation.status、可追溯性、usable 门控） |
| 2 | `group_quality_facts_by_record` | 按 semantic_record_key 分组事实 |
| 3 | `extract_quality_metrics` | 提取质量指标与字段 |
| 4 | `validate_defect_distribution_conservation` | 不良分布守恒检查（不守恒输出 data_gap，不补平） |
| 5 | `analyze_yield_and_defects` | 良率与不良分布分析 |
| 6 | `analyze_freeze_state` | 冻结状态分析（仅物化关联，终态排除，高风险只输出建议） |
| 7 | `enforce_spc_cpk_data_requirements` | SPC/Cpk 数据门控（缺测量点/规格限禁 Cpk） |
| 8 | `classify_quality_risk` | 质量风险分类（无阈值规则时 severity=unknown） |
| 9 | `build_quality_result` | 构建 v0.1.3 输出（EVREF-v1 字段级证据、merge_data_gaps 9 字段） |
| 10 | `validate_specialist_result_contract` | 输出合同内部预校验 |

## v0.1.2 迁移变更（→ v0.1.3 输出合同）

- **evidence_refs 升级为字段事实级 EVREF-v1**：由共享 `build_canonical_evidence_ref` 确定性生成 `EVREF-v1:<SHA256>`，替代 v0.1.1 的记录级 `EV-{field}@...`
- **metrics 字段绑定**：每个 metric 的 evidence_refs 解析到的 `semantic_field` 必须与 metric 声明的 `semantic_field` 一致
- **data_gaps 升级为 9 字段**：由共享 `merge_data_gaps` 归并，新增 `affected_record_count`（唯一 locator 数）/ `occurrence_count`（原始条数）/ `sample_source_locators`
- **纯 data_gap warning 模式**：无业务事实时 `conclusion=""` / `evidence_refs=[]`
- **contract_version**: `BIFROST-SPECIALIST-RESULT-v0.1.3`
- **删除旧 Schema**：仅保留 `BIFROST_SPECIALIST_RESULT_v0.1.3.schema.json`
- **逐字节复制** v0.1.3 权威 Schema 和独立验证器

## 质量专业规则（全部保留）

- 不良守恒检查：不守恒输出 data_gap，不得自动补平
- SPC/Cpk 数据门控：缺测量点/规格限/抽样规则时禁 Cpk/Cp/SPC 越界判定
- 冻结关系：仅物化关联，终态冻结排除，不得按日期/产品名/文本相似度自行关联
- 缺时间字段不制造趋势结论
- 相关性不得表述为根因
- 高风险动作（解除冻结/覆盖检验/100%复检）只返回 needs_confirmation，不自动执行

## 安全约束

- 全部只读，`actor_can_execute` 恒 `false`
- 高风险动作 `needs_human_confirmation=true`、`prohibited_auto_execute=true`
- 禁止虚构 DecisionID/ConfirmationID/RunID/EvidenceRef
- 禁止使用记录键、占位字符串或其他字段的证据支持质量指标

## 状态语义（共享优先级）

`blocked > needs_confirmation > warning > completed`

- **blocked**：不得输出业务结论/metrics/causes/recommended_actions
- **needs_confirmation**：必须存在至少一个合规高风险动作
- **warning**：必须存在非空 data_gaps
- **completed**：data_gaps 必须为空

## 依赖

- 输入合同：`BIFROST_DECISION_INPUT_v0.1`（逐字节不变）
- 共享验证器：`specialist_contract_validator.py` v0.1.3（逐字节复制自权威合同包）
- consumer：`bifrost-semantic-consumer-readonly` v0.1.1
- 数据面：`BIFROST_SEMANTIC_DATA_PLANE_v0.2_FINAL`

## 部署状态

**LOCALLY_VALIDATED_NOT_DEPLOYED** — 本地验证完成，不发布、不安装、不进入平台运行。
