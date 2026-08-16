# K-BIZ-001 指标口径与规则库

## 元数据
- knowledge_level: D（团队模拟/项目设计）
- source_type: 团队模拟/项目设计
- knowledge_version: KNOWLEDGE-v1.1
- 不得表述为歌尔内部真实制度或真实生产知识
- **本库只保存公式、语义、权限和规则；黄金事件的具体数值移入独立测试用例 `test_fixtures/golden_event_values.json`。**

## 指标公式

### OEE（综合设备效率）
- 公式：OEE = 开动率 × 性能率 × 质量因子
- 取值范围：0-1（小数），由前端格式化为百分比
- 数据来源：materialization.oee_recompute
- **OEE 质量因子从 line role KPI: QUALITY 动态读取。**

### 开动率（Availability）
- 公式：开动率 = 实际运行时间 / 计划运行时间
- 数据来源：equipment role KPI: AVAILABILITY

### 性能率（Performance Rate）
- 公式：性能率 = 实际节拍产出 / 理论节拍产出
- 数据来源：line/process role KPI: PERFORMANCE

## 质量率口径修正（04A.2 修订：移除全部事件固定值，仅保留动态数据源说明）

**三者必须严格区分，不得混用：**

| 口径 | 定义 | 数据来源 | 用途 |
|------|------|----------|------|
| **OEE 质量因子** | OEE 公式中的 Q 项 | line role KPI: QUALITY（动态读取） | 仅用于 OEE 计算 |
| **源质量率** | 质量角色报告的质量率 | quality role KPI: QUALITY（动态读取） | 质量视角的质量水平，口径与 OEE 质量因子一致但语义独立 |
| **整数良品复算率** | 良品数 / 总产出（整数复算） | materialization.yield_recompute（动态读取） | 供应链/财务对账用，基于整数良品数复算 |

- OEE 公式中**只使用 OEE 质量因子（从 line role KPI: QUALITY 动态读取）**，不得用整数良品复算率替代。
- **三种质量率在特定事件上数值可能不一致**，该差异登记为数据质量问题 DQ-YIELD-001（详见测试夹具 `test_fixtures/golden_event_values.json`）；在业务方统一口径前，OEE 计算继续采用载荷 line role KPI: QUALITY 提供的质量因子。
- 整数良品复算率与 OEE 质量因子数值可能接近但口径不同，报告时必须标注口径。
- 源质量率低于阈值时触发质量告警，阈值由规则定义（非固定值）。

## 不良口径
- 不良总数：materialization.defect_total（动态读取）
- 不良类型分布：quality role alerts（动态读取）
- 不良占比 = 该类型不良数 / 不良总数

## 物料缺口口径
- 公式：物料缺口 = MAX(需求量 - 需求日前可用量, 0)
- 需求量 = MAX(计划数量 × BOM用量 - 已领料, 0)
- 需求日前可用量 = MAX(现有库存 - 已占用 - 质量冻结 + 需求日前确认到货, 0)
- 数据来源：supply role material_detail（动态读取）

## 质量冻结口径
- 冻结状态：从 supply.material_detail[freeze_id].freeze_status 结构化字段读取
- 冻结原因：从 material_detail 对应字段读取
- 冻结数量：material_detail.质量冻结
- **不得硬编码冻结单号或状态值**

## 换产超时口径
- 换产事件判定：downtime_events 中 是否换产事件=是
- 最长换产：取 downtime_events 中换产事件的最大 持续时间_分钟
- 数据来源：equipment role downtime_summary / downtime_events（动态）

## 风险等级规则
- OEE < 50%：高
- OEE 50-70%：中
- OEE > 70%：低
- 风险等级：materialization.risk_level（动态读取）

## 人工确认规则
- 确认状态：validation_results.decision_confirmation_map 中各 confirmation 的 status 字段
- 可能状态：待确认 / 撤回 / 已确认
- **高风险动作（解除冻结、修改阈值、调整排产等）必须生成待确认草稿，禁止自动执行**
- 确认状态从结构化字段动态读取，不得硬编码
