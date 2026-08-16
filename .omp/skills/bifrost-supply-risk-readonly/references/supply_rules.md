# 供应链风险只读分析参考规则

## 适用范围
本 Skill 仅消费 `BIFROST_DECISION_INPUT_v0.1`，不直接读取原始 Excel/CSV/JSON、语义数据面 ZIP、Overview/Event 载荷、多维表格或控制表。

## 可分析语义实体
- purchase_order（采购订单）
- material_code / material_name / supplier
- planned_arrival / actual_arrival / promised_delivery_date
- inventory_snapshot（库存快照）
- material_shortage / shortage_risk（物料缺口）
- freeze_quantity（质量冻结）
- order_amount（订单金额）

## 物料缺口与质量冻结
- 缺口物料不一定是冻结物料。
- 没有已物化的 BusinessKey / 物料关系时不得合并原因。
- 采购订单、库存、工单、冻结之间只有 `relation_materialization_status=materialized` 时才能关联。
- 禁止按物料名称相似、记录行号一致、ID 前缀或日期接近自行建立关系。

## 库存快照粒度
- inventory_snapshot 当前为 `view_projection_only`，`grain_status=unresolved`，`aggregation_allowed=false`。
- 粒度未解决前：可返回逐记录库存事实；禁止跨记录求和、平均或推导全局库存；必须输出 `aggregation_not_allowed` 或结构化 data_gap。

## 到货逾期判定
- 必须有承诺日期、实际/预计到货日期及批准的时间比较规则。
- 字段缺失时不得判断逾期，输出 data_gap。
- 比较规则：实际/预计到货晚于承诺交期即为逾期（确定性日期比较，无宽限期阈值）。

## 金额消费
- 金额只消费标准化后的 cny 值；raw_value 仅用于证据审计。
- 负金额、无单位金额、单位未登记等状态不得进入业务结论，转 data_gap。

## 缺料与 OEE
- 缺料不得直接表述为当前 OEE 下降原因。
- 没有 MATERIALS 停机关联时只能表述为后续生产连续性风险。

## 高风险动作
加急采购、替代料、修改交付承诺、解除冻结、修改采购订单属于高风险动作：
- `needs_human_confirmation=true`
- `prohibited_auto_execute=true`
- `actor_can_execute=false`
- 不生成虚构 ConfirmationID
- 不写回采购、库存或订单系统

## 严重度
- 无批准阈值规则时 `severity=unknown`，输出 `missing_severity_rule`。

## 置信度
- confidence 由证据覆盖率确定性计算：`usable_facts_with_evidence / total_usable_facts`。
- 不得写死。
