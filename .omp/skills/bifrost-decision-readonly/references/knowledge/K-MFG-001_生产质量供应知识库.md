# K-MFG-001 生产质量供应知识库

## 元数据
- knowledge_level: D（团队模拟/项目设计）
- source_type: 团队模拟/项目设计
- knowledge_version: KNOWLEDGE-v1.1
- 不得表述为歌尔内部真实制度或真实生产知识
- **本库只保存框架、语义和规则；黄金事件的具体停机/缺陷数值移入独立测试用例 `test_fixtures/golden_event_values.json`。**

## 5M1E 框架
- Man（人）：当前无人员数据接入
- Machine（机）：设备停机数据来自模拟，缺少 EquipmentID、故障码、维修工单
- Material（料）：物料数据来自模拟，包括缺口和冻结
- Method（法）：工艺参数数据不足，缺少 SPC 测量点
- Measurement（测）：无 SPC 原始测量点和规格限
- Environment（环）：无环境数据接入

## 停机分类
- 停机原因：从 equipment role downtime_events 的「源停机原因」字段动态读取
- 停机组：从「源停机组」字段动态读取（FAILURE / SETUPS-CHANGEOVERS / MATERIALS / OPERATIONAL）
- 最大单次故障：从 downtime_events 中 note 含「最大」的记录动态取值
- 计划停机 vs 非计划停机：由 downtime_summary.unplanned_events / planned_events 区分
- 累计停机分钟、非计划停机分钟：从 equipment role KPI 动态读取
- **不得硬编码停机条数、分钟数或故障原因**

## 缺陷分类（六类数据质量维度）
1. missing（缺失）
2. duplicate（重复）
3. outlier（异常值）
4. format（格式不一致）
5. logic（逻辑冲突）
6. stale（时效滞后）
- 缺陷类型分布（外观不良、尺寸超差等）：从 quality role alerts 动态读取

## 换产规则
- 换产属于计划性停机
- 换产事件判定：downtime_events 中 是否换产事件=是
- 换产超时影响开动率
- 当前无法确证换产与质量异常的因果关系（缺少 SPC 证据）

## 已知数据缺口（重要）
- 缺少 SPC 原始测量点和规格限 → 不能计算 Cpk，不能判断 SPC 越界
- 缺少 EquipmentID、故障码和维修工单 → 不能可靠计算 MTBF/MTTR
- 不得虚构人员、技能、真实供应商或歌尔内部制度
- 不得把相关性表述为已证实因果关系

## 产线特征
- LINE-S01：稳态基准线
- LINE-S02：设备瓶颈线
- LINE-S03：质量瓶颈线
- 产线角色与时间窗的组合由 view_key 唯一定位（role|scope|time_window）

## 物料规则
- 物料缺口物料与质量冻结物料可能是不同物料，不得合并为同一原因
- 冻结状态从 material_detail 结构化字段读取，不得硬编码
