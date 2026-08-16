---
name: bifrost-production-diagnosis-readonly
description: "BIFROST生产诊断只读Skill。消费 BIFROST_DECISION_INPUT_v0.1，输出 BIFROST_SPECIALIST_RESULT_v0.1.3，分析 OEE 三因子、产量、停机、换产和源值复算差异。不得写回业务数据；没有足够数据时不得伪造 MTBF、MTTR、SPC 或 Cpk；高风险动作只生成待人工确认草稿。"
---
# BIFROST 生产诊断只读 Skill

## 版本信息

- **Skill 逻辑版本:** 0.1.2
- **输出合同版本:** BIFROST-SPECIALIST-RESULT-v0.1.3
- **输入合同版本:** BIFROST-DECISION-INPUT-v0.1
- **状态:** LOCALLY_VALIDATED_NOT_DEPLOYED

## 职责

本 Skill 只承担生产专业的确定性分析：

1. OEE 三因子（availability / performance_rate / quality_factor）直接驱动分析
2. 班次产量 / 良率分析
3. 停机证据分析（非计划停机 / 计划停机）
4. 换产分析
5. OEE 源值与复算值对比

不承担字段映射、数据接入、跨源关联、业务写回或最终决策执行。

## 链路

```
语义消费者 (bifrost-semantic-consumer-readonly)
→ BIFROST_DECISION_INPUT_v0.1
→ bifrost-production-diagnosis-readonly (本 Skill)
→ BIFROST_SPECIALIST_RESULT_v0.1.3
→ BIFROST 决策编排智能体
```

## 安全约束

- 全部只读，`actor_can_execute` 始终为 `false`
- 高风险动作只能标记 `needs_human_confirmation=true`，禁止自动执行
- 不得创建虚构 DecisionID / ConfirmationID / RunID / EvidenceRef
- 不得解除冻结、修改排产、修改采购订单、修改业务数据
- 不得发布、安装或上架 Skill
- 不得修改现有智能体工作指令

## v0.1.2 变更（04D.3-PROD）

1. **输出合同升级为 v0.1.3** — 逐字节复制共享 Schema 和验证器，哈希校验通过
2. **EVREF-v1 字段级证据** — 使用共享 `build_canonical_evidence_ref` 生成 `EVREF-v1:<SHA256>`
3. **删除所有占位证据** — `EV:no_evidence`、`EV:*:no_provenance`、裸 `semantic_record_key` 等
4. **metrics/causes/actions 证据验证** — 每条证据必须通过 `validate_specialist_result_against_input`
5. **高风险动作状态优先级** — 非 blocked 结果必须为 `needs_confirmation`，不得为 `warning`/`completed`
6. **data_gaps 归并** — 使用共享 `merge_data_gaps`，输出 `affected_record_count`/`occurrence_count`/`sample_source_locators`（≤3）
7. **修复重复 data_gap** — 321/741 条原始缺口经归并后大幅缩减
8. **既有规则保留** — OEE 三因子白名单、物料风险非直接原因、禁止伪造 MTBF/MTTR、禁止制造趋势
9. **变异测试** — 错误字段 EVREF、裸 record_key、占位证据、高风险+warning 必须失败

## 目录结构

```
bifrost-production-diagnosis-readonly_v0.1.2/
├── SKILL.md                                    # 本文件
├── schema/
│   ├── BIFROST_DECISION_INPUT_v0.1.schema.json    # 输入 Schema（逐字节复制）
│   └── BIFROST_SPECIALIST_RESULT_v0.1.3.schema.json  # 输出 Schema（逐字节复制）
├── scripts/
│   ├── __init__.py
│   ├── production_constants.py                 # 常量与语义字段定义
│   └── production_diagnosis.py                 # 主诊断模块
├── validator/
│   ├── specialist_contract_validator.py        # 共享验证器（逐字节复制）
│   └── production_validator.py                 # 生产专业独立验证器
├── references/
│   └── production_rules.md                     # 生产诊断规则
├── tests/
│   ├── fixtures/
│   │   └── golden_event_values.json            # 合成夹具
│   ├── test_production_diagnosis.py            # 合同测试
│   ├── test_real_consumer_integration.py       # 真实 consumer 联调
│   └── results/                                 # 测试结果（运行时生成）
└── docs/
    ├── acceptance_report.md                    # 验收报告
    └── migration_notes_v0.1.2.md               # 迁移说明
```

## 运行方式

```bash
# 合同测试
cd bifrost-production-diagnosis-readonly_v0.1.2
python3 -m pytest tests/test_production_diagnosis.py -v

# 真实 consumer 联调
python3 tests/test_real_consumer_integration.py
```

## 依赖

- Python 3.10+
- 共享合同验证器 `specialist_contract_validator.py`（逐字节复制自 BIFROST_SPECIALIST_CONTRACT_v0.1.3）
- 语义消费者 `bifrost-semantic-consumer-readonly` v0.1.1（只调用，不修改）
- 语义数据面 `BIFROST_SEMANTIC_DATA_PLANE_v0.2_FINAL`（只读取，不修改）
