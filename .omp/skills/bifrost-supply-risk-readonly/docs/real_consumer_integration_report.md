# 真实 Consumer 联调报告 — bifrost-supply-risk-readonly v0.1.3 (04D.4C.1-SUPPLY)

## 1. 联调链路

```
RC1 数据面 ZIP (BIFROST_v0.3_RC1, sha=b12e1f6c…)
  → Consumer v0.1.3 (orchestrate_consumer_run)
  → BIFROST_DECISION_INPUT_v0.1 (PO-2026-0001, P01, 20 字段级事实)
  → Supply v0.1.3 (orchestrate_supply_analysis, is_real_data_plane=True)
  → BIFROST_SPECIALIST_RESULT_v0.1.3
  → 共享验证器 + 跨输入 EVREF 验证
```

- Consumer v0.1.3 信任注册表已登记 RC1 SHA-256，ZIP↔解压目录绑定校验通过；
- P01 字段已具备完整 value_consumption_status=usable，本轮无需等待 Consumer 0.1.4；
- 数据面 ZIP 运行前后 SHA-256 不变（b12e1f6c…）。

## 2. 普通只读查询结果（PO-2026-0001 / MAT-001）

| 必验项 | 结果 |
|--------|------|
| purchase_qty=6666 / arrived_qty=6573 / shortfall_qty=93 | ✅ 确定性计算 6666−6573=93，metrics 体现 |
| arrived_qty<purchase_qty → delivery_status=partial_arrival | ✅ conclusion "存在部分到货采购订单"，cause category=partial_delivery_shortfall |
| delivery_completion_status=indeterminate | ✅ data_gap=missing_full_delivery_completion_evidence |
| actual_arrival_date 仅登记到货，非整单完成 | ✅ cause 含"仅到货登记事实，非整单完成判定" |
| 无 as_of_time → overdue_status=indeterminate | ✅ data_gap=missing_as_of_time_for_remaining_overdue |
| 输出 missing_full_delivery_completion_evidence / 对应 data_gap | ✅ |
| 普通只读查询不得出现催货/加急/紧急采购动作 | ✅ recommended_actions 为空，expedite_gate=explicit_request_required |
| action_id=local_run_only，无持久化 ActionID/ConfirmationID | ✅ |
| actor_can_execute=false | ✅ |
| needs_human_confirmation=false（只读无高风险） | ✅ |
| 20 条 EVREF-v1 全部可解析 | ✅ |
| 共享验证器 + 跨输入 EVREF 验证通过 | ✅ |

## 3. 显式加急请求门控结果

对同一真实 decision_input 注入 query_context.requested_action=expedite_purchase：

| 必验项 | 结果 |
|--------|------|
| expedite_gate=explicit_request_detected | ✅ |
| 真实数据面无 material_shortage 实体 → shortage 字段级 EVREF 不充分 | 门控第二条件不满足 |
| 不生成加急动作（门控正确拦截） | ✅ recommended_actions 无加急动作 |
| 共享验证器通过、actor_can_execute=false | ✅ |

正向用例（显式请求 + EVREF 充分 → 生成 needs_confirmation 草稿）由回归测试 `test_23_explicit_expedite_sufficient` 覆盖并通过：status=needs_confirmation、is_high_risk=true、needs_human_confirmation=true、prohibited_auto_execute=true、actor_can_execute=false、action_identifier_scope=local_run_only。

## 4. 回归测试

`tests/test_supply_risk_analyzer.py`：43 passed, 4 skipped。覆盖输入合同失败、source_write 阻塞、证据缺失阻塞、删除证据变异、普通只读不加急、显式加急门控、local_run_only、独立验证器等。

## 5. 机器可读测试结果

`integration/machine_readable_test_results.json`：20/20 通过，0 失败。

## 6. 边界与状态

- 未修改 Consumer v0.1.3、RC1 数据面、共享合同或其他专业 Skill；
- 未上传、未发布、未安装；
- delivery_status=LOCAL_CONTRACT_VALIDATED_REAL_CONSUMER_INTEGRATED_NOT_DEPLOYED；
- 阻塞项（blocking_reasons）：无；部署就绪（deployment_ready）=true（指包装/合同层面就绪，按项目规则本轮不部署）。
