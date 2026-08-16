---
name: bifrost-supply-risk-readonly
label: BIFROST供应链风险只读
description: "BIFROST制造业供应链风险只读能力。消费经过可信门控的BIFROST_DECISION_INPUT_v0.1，分析采购、到货、库存、缺料与冻结风险，严格区分生产连续性风险和OEE直接原因，输出BIFROST_SPECIALIST_RESULT_v0.1.3。高风险动作只生成确认需求，禁止自动执行。"
---
# BIFROST 供应链风险只读 Skill

## 版本信息

| 项目 | 值 |
|---|---|
| Skill 逻辑版本 | 0.1.3 |
| 输出合同 | BIFROST_SPECIALIST_RESULT_v0.1.3 |
| 输入合同 | BIFROST_DECISION_INPUT_v0.1 |
| 阶段 | 04D.4C.1_SUPPLY_REAL_CONSUMER_INTEGRATION_PLATFORM_MINIMAL_NOT_DEPLOYED |
| 共享合同版本 | v0.1.3 |
| 证据引用粒度 | 字段级 EVREF-v1 |

## v0.1.3 变更（04D.4B-SUPPLY-P1 到货完成状态与逾期判定语义修复）

- actual_arrival_date 只解释为"已登记到货日期"，不得自动解释为整单完成日期
- 到货状态由 purchase_qty 与 arrived_qty 确定性确定：unknown / not_arrived / partial_arrival / completed / over_received_anomaly
- 部分到货时 delivery_completion_status=indeterminate，不得仅因到货日期不晚于承诺交期就判定全单已完成
- 剩余数量逾期判定依赖明确 as_of_time；缺失时 overdue_status=indeterminate，不使用系统当前时间猜测
- 高风险加急采购仅在明确请求 + 字段级 EVREF 充分时生成草稿；普通只读查询不生成加急动作
- action_id 登记 identifier_scope=local_run_only（在 specialist_details 中），不生成 ConfirmationID

## 职责边界

仅承担供应链专业的确定性分析：
- 采购订单到货状态分析（基于数量的到货状态 + 基于时点的逾期判定）
- 物料缺口分析（逐记录、不跨记录聚合）
- 库存粒度门控（grain_status=unresolved 时禁止聚合）
- 缺口与冻结原因分离
- 供应连续性风险分类

不承担字段映射、跨源关联、业务写回或最终决策执行。

## 关键规则

- actual_arrival_date 仅为已登记到货日期，非整单完成日期
- 到货状态由 purchase_qty 与 arrived_qty 确定性确定
- 部分到货时 delivery_completion_status=indeterminate
- 剩余数量逾期判定依赖明确 as_of_time
- 缺口与冻结原因不得合并
- 库存粒度未解决时禁止跨记录聚合
- 无物化关系不跨实体 join
- 缺料仅为后续生产连续性风险，非 OEE 直接原因
- 高风险动作仅在明确请求 + 证据充分时生成 needs_confirmation 草稿
- action_id 为 local_run_only，不生成 ConfirmationID

## 证据引用

所有 evidence_refs 使用字段级 EVREF-v1:<SHA256> 格式，由共享 `build_canonical_evidence_ref` 确定性构建。

## data_gaps 归并

使用共享 `merge_data_gaps` 按 5 键归并，输出 `affected_record_count` 和 `occurrence_count`。

## 文件结构

```
scripts/supply_risk_analyzer.py     分析器主逻辑（v0.1.3 语义修复）
scripts/run_integration.py           真实 consumer 联调脚本
validator/specialist_contract_validator.py  共享合同验证器（逐字节复制 v0.1.3）
validator/supply_specialist_validator.py    供应链专用验证器（v0.1.3）
schema/BIFROST_SPECIALIST_RESULT_v0.1.3.schema.json  输出 Schema（逐字节复制）
schema/BIFROST_DECISION_INPUT_v0.1.schema.json        输入 Schema（逐字节复制）
tests/                               43 项回归测试 + 真实联调测试
integration/                         真实 consumer 联调产物
```

## 状态

LOCAL_CONTRACT_VALIDATED_REAL_CONSUMER_INTEGRATED_NOT_DEPLOYED

不发布、不安装、不进入平台调用。
