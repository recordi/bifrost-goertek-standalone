# 质量诊断专业规则参考

## 可分析字段

| 字段 | 说明 |
|------|------|
| yield / yield_rate / quality_rate | 良率 |
| defect_count / defect_total | 不良数量/总数 |
| defect_type / defect_type_name | 不良类型 |
| defect_ratio / defect_percentage | 不良占比 |
| freeze_status | 冻结状态 |
| freeze_id | 冻结单号 |
| freeze_quantity | 冻结数量 |
| freeze_reason | 冻结原因 |
| inspection_status / reinspection_status | 检验/复检状态 |
| total_output / good_output / defect_output | 总产出/良品/不良品 |
| spc_measurement_points | SPC 原始测量点 |
| usl / lsl | 规格上限/下限 |
| sample_rule | 抽样规则 |

## 不良守恒规则

- 各不良类型数量之和 = 不良总数
- 各不良类型占比之和 = 1.0（允许浮点误差 0.001）
- 不守恒时输出 data_gap，**不得自动补平**

## SPC 门控规则

SPC 必需字段：`spc_measurement_points`、`usl`、`lsl`

- 三者全部存在 → Cpk 可计算
- 任一缺失 → 禁止计算 Cpk/Cp，禁止判断 SPC 越界，输出 `GAP-SPC-MEASUREMENT`
- `sample_rule` 缺失 → 输出 data_gap，SPC 判定结果不可靠

## 冻结关联规则

- 冻结记录与质量事件只有存在**已物化关联字段**（quality_event_id / event_id / linked_event_ref / relation_ref）时才可关联
- 禁止按相同日期、产品名或文本相似度自行关联
- 无关联字段时输出 data_gap

## 冻结状态机

终态状态（不得重新进入待确认）：
- resolved（已解除）
- revoked（已撤回）
- released（已释放）
- cancelled（已取消）
- closed（已关闭）

## 高风险动作清单

| 动作 | 规则 |
|------|------|
| 解除冻结 | needs_human_confirmation=true, prohibited_auto_execute=true |
| 覆盖检验结果 | needs_human_confirmation=true, prohibited_auto_execute=true |
| 启动 100% 复检 | needs_human_confirmation=true, prohibited_auto_execute=true |

所有高风险动作：actor_can_execute=false，不生成虚构 ConfirmationID。

## 趋势判断规则

- 没有时间字段（record_timestamp / inspection_date / shift_id）时不得宣称趋势
- 即使有时间字段，也需要多个时间点才能判断趋势方向
- 不得自行推断趋势方向

## 因果边界规则

- 不良分布相关性 → 标注为"关联现象"或"待验证原因"
- causal_evidence_level = "correlation_not_causation"
- 不得使用"根因""已验证原因""确定原因""根本原因"等表述

## 良率口径区分（K-BIZ-001）

| 口径 | 定义 | 用途 |
|------|------|------|
| OEE 质量因子 | OEE 公式中的 Q 项 | 仅用于 OEE 计算 |
| 源质量率 | 质量角色报告的质量率 | 质量视角的质量水平 |
| 整数良品复算率 | good_output / total_output | 供应链/财务对账 |

报告时必须标注口径。

## 风险等级规则

- 没有批准的阈值规则时 severity=unknown
- 输出 missing_severity_rule=true
- confidence = 有证据的事实数 / 总事实数（确定性计算）
