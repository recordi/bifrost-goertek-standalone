# 生产专业规则摘要

本文件是运行时参考，不包含任何具体业务数值。所有业务值从 BIFROST_DECISION_INPUT_v0.1 的 normalized_facts 动态读取。

## OEE 公式

OEE = 开动率 × 性能率 × 质量因子

- 开动率（availability）= 实际运行时间 / 计划运行时间
- 性能率（performance_rate）= 实际节拍产出 / 理论节拍产出
- 质量因子（quality_factor）= OEE 公式中的 Q 项

## 质量率口径区分（三者不得混用）

| 口径 | 定义 | 用途 |
|------|------|------|
| OEE 质量因子 | OEE 公式中的 Q 项 | 仅用于 OEE 计算 |
| 源质量率 | 质量角色报告的质量率 | 质量视角质量水平 |
| 整数良品复算率 | good_output / total_output | 供应链/财务对账 |

OEE 公式中只使用 OEE 质量因子，不得用整数良品复算率替代。

## OEE 直接驱动白名单

只有以下三项可作为 OEE 直接驱动因子：
- availability
- performance_rate
- quality_factor

其他指标（物料缺口、停机等）不得进入 OEE 直接驱动。

## 停机分类

- 停机组：FAILURE / SETUPS-CHANGEOVERS / MATERIALS / OPERATIONAL
- 非计划停机可作为开动率下降证据
- 换产属于计划性停机
- 物料缺口默认表述为生产连续性风险，除非有明确且已物化的 MATERIALS 停机关联

## 复算规则

- can_recompute_oee=true 且三因子齐全时可复算
- can_recompute_oee=false 或三因子不完整时不得复算
- oee_source 与 oee_recomputed 独立展示，不得互相覆盖

## MTBF/MTTR 门控

缺少以下任一时不得计算 MTBF/MTTR：
- EquipmentID
- 故障码
- 维修工单

## 趋势判定

- 需要 shift_date + shift_sequence 同时存在
- 至少 2 条有序记录
- 缺少时间字段或顺序证据时不得声称形成趋势

## 严重度

- 无批准的严重度阈值规则时 severity=unknown
- 输出 missing_severity_rule 标记
- severity 依据输入中已物化的 risk_level + severity_rule_id

## 高风险动作

- 调整排产计划 → needs_human_confirmation=true, prohibited_auto_execute=true
- 解除冻结、修改阈值、修改订单、覆盖数据 → 同上
- 不得生成虚构 ConfirmationID
- actor_can_execute 恒为 false

## 关联查询门控

- relation_materialization_status != materialized 时禁止关联查询
- 不得根据 ID 前缀、行号相同或文本相似自行建立关联
- 不得跨记录、跨实体自行拼接
