# BIFROST 供应链风险只读 Skill v0.1.3

## 交付包信息

- **Skill 逻辑版本**: 0.1.3
- **输出合同**: BIFROST_SPECIALIST_RESULT_v0.1.3
- **输入合同**: BIFROST_DECISION_INPUT_v0.1
- **阶段**: 04D.4B_SUPPLY_P1_DELIVERY_SEMANTIC_FIX_LOCALLY_VALIDATED_NOT_DEPLOYED
- **状态**: LOCAL_CONTRACT_VALIDATED_NOT_INTEGRATED
- **输入 ZIP SHA-256**: d19325e4a90e0ca54cada07c7e8b3038affc493d7d7f29bcf008ed5667d8a279

## v0.1.3 变更（04D.4B-SUPPLY-P1 到货完成状态与逾期判定语义修复）

修复 P1_RUNTIME_SEMANTIC_GAP：

1. actual_arrival_date 只解释为"已登记到货日期"，不得自动解释为整单完成日期
2. 到货状态由 purchase_qty 与 arrived_qty 确定性确定：
   - arrived_qty is null → unknown
   - arrived_qty = 0 → not_arrived
   - 0 < arrived_qty < purchase_qty → partial_arrival
   - arrived_qty = purchase_qty → completed
   - arrived_qty > purchase_qty → over_received_anomaly
3. 部分到货时 delivery_completion_status=indeterminate，不得仅因到货日期不晚于承诺交期就判定全单已完成；保留 shortfall_qty；缺少完整到货证据时输出 data_gap
4. 剩余数量逾期判定依赖明确 as_of_time；缺失时 overdue_status=indeterminate，不使用系统当前时间猜测
5. 高风险加急采购仅在明确请求 + 字段级 EVREF 充分时生成草稿；普通只读查询不生成加急动作
6. action_id 登记 identifier_scope=local_run_only（在 specialist_details 中），不生成 ConfirmationID

## 测试结果

- 43 项回归测试：全部通过
- 4 项真实 consumer 联调测试：跳过（integration 产物沿用 v0.1.2，未重新生成）
- 旧错误表述静态扫描：零命中
- 源码固定值扫描：零命中（MAT-001、MAT-002、PO-2026-0001、6666、6573、93）
- 变异测试（删除数量 EVREF 后不得生成高风险草稿）：通过

## 新增测试用例

- 部分到货日期早于承诺日期，不得推出全单已完成
- 部分到货且缺 as_of_time → overdue indeterminate
- 部分到货且 as_of_time 晚于承诺日期 → 剩余数量逾期
- arrived_qty=purchase_qty → completed
- arrived_qty>purchase_qty → over_received_anomaly
- 缺 purchase_qty/arrived_qty → data_gap
- 普通只读查询不生成加急动作
- 明确加急请求且证据充分 → needs_confirmation
- 删除任一数量 EVREF 后不得生成高风险草稿

## 文件清单

详见 CONTENTS.json

## 安全约束

- 全部只读，actor_can_execute 恒为 false
- 不发布、不安装、不进入平台调用
- 不修改 consumer、数据面、其他专业 Skill、共享合同、前端或正式基线

## 范围

仅修复 bifrost-supply-risk-readonly 的 P1_RUNTIME_SEMANTIC_GAP。
不修改 Consumer、数据面、Production、Quality、共享合同、前端、智能体工作指令或 MAP/SEM/DQ 基线。
