# 差异与回滚说明 — bifrost-supply-risk-readonly v0.1.2 → v0.1.3

## 背景

v0.1.2 在 04D.4C 预览联调中暴露 P1_RUNTIME_SEMANTIC_GAP（见 BIFROST_04D.4C_PREVIEW_RC1_FINAL_REPORT.json `17_not_yet_ready` 第 2 项）：

- arrival_compare_rule 对 PO-2026-0001#row12 输出确定性逾期结论（到货逾期 11 天），违反本轮要求 overdue_status 必须为 indeterminate/data_gap；
- 在普通只读查询下生成催货动作 A-SUP-001（向供应商紧急催货），违反只读查询不得生成主动动作。

v0.1.3 针对 P1 到货完成状态与逾期判定语义进行确定性修复。

## 迁移差异

### 到货完成状态语义

| 维度 | v0.1.2 | v0.1.3 |
|------|--------|--------|
| actual_arrival_date 解释 | 可被解释为整单完成日期 | 仅"已登记到货日期"，不得解释为整单完成日期 |
| 到货状态判定 | arrival_compare_rule 直接基于日期 | 由 purchase_qty 与 arrived_qty 确定性确定（unknown / not_arrived / partial_arrival / completed / over_received_anomaly） |
| 部分到货 completion_status | 可能基于到货日期早于承诺交期判定完成 | delivery_completion_status=indeterminate，不得仅因到货日期不晚于承诺交期判全单完成 |
| registered_arrival_note | 无 | 新增，仅事实描述到货登记，不作为整单逾期结论 |

### 逾期判定语义

| 维度 | v0.1.2 | v0.1.3 |
|------|--------|--------|
| 剩余数量逾期 | 缺 as_of_time 时仍输出确定性逾期天数 | 缺明确 as_of_time → overdue_status=indeterminate，不使用系统当前时间猜测 |
| data_gap | 无 missing_as_of_time_for_remaining_overdue | 新增该 data_gap |
| data_gap | 无 missing_full_delivery_completion_evidence | 部分到货新增该 data_gap |
| arrival_compare_rule.note | 无 | "不使用系统当前时间猜测 as_of_time；不含宽限期/阈值" |

### 加急动作门控

| 维度 | v0.1.2 | v0.1.3 |
|------|--------|--------|
| 普通只读查询 | 可能生成催货动作 A-SUP-001 | 不生成加急/催货/紧急采购动作（expedite_gate=explicit_request_required） |
| 加急生成条件 | 无明确门控 | 仅当明确请求 expedite_purchase/substitute_material 且 shortage 字段级 EVREF 充分时生成 |
| 生成的动作属性 | — | status=needs_confirmation；is_high_risk=true；needs_human_confirmation=true；prohibited_auto_execute=true；actor_can_execute=false |
| action_id 持久化 | 可生成持久化标识 | identifier_scope=local_run_only，不生成持久化 ActionID / ConfirmationID |
| specialist_details.expedite_gate | 无 | 新增 explicit_request_required / explicit_request_detected |
| specialist_details.action_identifier_scope | 无 | 新增 local_run_only |
| specialist_details.delivery_semantic_fix | 无 | 新增 v0.1.3_P1_actual_arrival_date_is_registered_only |

### 规则版本

- DELIVERY_STATUS_RULE.rule_id / ARRIVAL_COMPARE_RULE.rule_id 升级，rule_text 重写为 v0.1.3 语义。
- contract_versions 中 delivery_status_rule_version / arrival_compare_rule_version 随之更新。

## 回滚方案

回滚 = 退回 v0.1.2 交付包 `BIFROST_SUPPLY_RISK_READONLY_v0.1.2.zip`，恢复 v0.1.2 运行时 Skill 目录。

风险：
1. v0.1.2 在普通只读查询下会生成催货动作，违反只读约束；
2. v0.1.2 对部分到货输出确定性逾期结论，违反 as_of_time 缺失时必须 indeterminate 的要求；
3. v0.1.2 不通过本轮 04D.4C.1 真实 Consumer 联调验收（must-verify 4/5 失败）。

回滚步骤：
1. 保留 v0.1.2 交付包；
2. 将运行时 Skill 目录替换为 v0.1.2 版本；
3. 在 04D.4C.1 验收清单中标注 v0.1.2 不通过 P1 语义项。

不建议回滚：v0.1.3 为 P1 语义修复，回滚将重新引入已识别的运行时语义缺陷。
