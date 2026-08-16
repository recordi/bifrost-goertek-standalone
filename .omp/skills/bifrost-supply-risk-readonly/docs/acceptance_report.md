# 04D.4B-SUPPLY-P1 验收报告

## 交付信息

| 项目 | 值 |
|---|---|
| 任务编号 | 04D.4B-SUPPLY-P1 |
| 修复目标 | bifrost-supply-risk-readonly P1_RUNTIME_SEMANTIC_GAP |
| 逻辑版本 | 0.1.2 → 0.1.3 |
| 输入 ZIP SHA-256 | d19325e4a90e0ca54cada07c7e8b3038affc493d7d7f29bcf008ed5667d8a279 |
| 输出合同 | BIFROST_SPECIALIST_RESULT_v0.1.3（未修改） |
| 状态 | LOCAL_CONTRACT_VALIDATED_NOT_INTEGRATED |

## 修复内容

### 1. actual_arrival_date 语义修复
- 只解释为"已登记到货日期"，不得自动解释为整单完成日期
- 在部分到货原因中追加已登记到货日期的事实描述，但不作为整单完成判定

### 2. 到货状态由数量确定性确定
- arrived_qty is null → unknown
- arrived_qty = 0 → not_arrived
- 0 < arrived_qty < purchase_qty → partial_arrival
- arrived_qty = purchase_qty → completed
- arrived_qty > purchase_qty → over_received_anomaly

### 3. 部分到货语义修复
- delivery_completion_status=indeterminate
- 不得仅因到货日期不晚于承诺交期就判定全单已完成
- 保留 shortfall_qty=purchase_qty-arrived_qty
- 缺少完整到货证据时输出 data_gap: missing_full_delivery_completion_evidence

### 4. 剩余数量逾期判定
- 依赖明确 as_of_time + promised_delivery_date + remaining_qty > 0
- as_of_time 缺失 → overdue_status=indeterminate，不使用系统当前时间猜测
- as_of_time > promised 且仍有缺口 → 剩余数量逾期，但不表述为整单从未发生到货

### 5. 高风险加急采购门控
- 普通只读查询不生成加急动作
- 明确加急请求 + 字段级 EVREF 充分 → needs_confirmation
- status/is_high_risk/needs_human_confirmation/prohibited_auto_execute/actor_can_execute 门控保持

### 6. action_id 标识
- identifier_scope=local_run_only（在 specialist_details 中登记）
- 不冒充业务系统持久化 ActionID
- 不生成 ConfirmationID

## 测试结果

| 测试类别 | 数量 | 结果 |
|---|---|---|
| 输入合同测试 | 4 | 全部通过 |
| 到货语义测试 | 2 | 全部通过 |
| 库存粒度测试 | 2 | 全部通过 |
| 缺口冻结分离测试 | 3 | 全部通过 |
| 金额测试 | 2 | 全部通过 |
| 高风险门控测试 | 2 | 全部通过 |
| 到货语义修复新增测试 | 9 | 全部通过 |
| 变异测试 | 3 | 全部通过 |
| 共享合同 Schema 测试 | 16 | 全部通过 |
| 真实 consumer 联调测试 | 4 | 跳过（integration 产物沿用 v0.1.2） |
| **合计** | **47** | **43 通过 / 0 失败 / 4 跳过** |

## 静态扫描

- 旧错误表述（整单未逾期/整单按期完成/整单按期）：零命中
- 源码固定值（MAT-001/MAT-002/PO-2026-0001/6666/6573/93）：零命中
- 全部合规夹具输出通过共享验证器

## 范围合规

- 未修改 Consumer、数据面、Production、Quality、共享合同、前端、智能体工作指令或 MAP/SEM/DQ 基线
- 未发布、未安装、未更新线上 Supply Skill
- 真实场景和合成夹具分开登记
