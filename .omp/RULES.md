# BIFROST 硬门禁规则

## 数据和证据
- 所有业务事实必须能够追溯到 EvidenceRef、ViewKey、EventID 或真实 RecordID。
- 禁止前端、自然语言模型或施工代理硬编码业务数值。
- 禁止凭 ID 前缀、行号、日期相同、产品名相似自行建立跨表关联。
- 未验证的字段、空值、关联歧义必须输出 data_gap，不得猜测补全。
- 官方脱敏数据、团队模拟数据、公开 Zenodo 数据必须清晰区分。

## 指标
- OEE = 开动率 × 性能率 × 质量因子。
- 物料缺口默认是生产连续性风险，不是 OEE 直接原因；只有存在明确 MATERIALS 停机证据关联时，才可表述为间接影响。
- 没有原始测量点、规格限和抽样规则时，禁止计算或声称计算 SPC/Cpk。
- 没有 EquipmentID、故障码、维修工单时，禁止声称已经计算 MTBF/MTTR。
- 相关性不得直接表述为根因。

## 权限和写入
- 专业 Skill 默认只读，`actor_can_execute=false`。
- 禁止修改源数据、语义数据面、Overview/Event Payload、Excel、UI 基线和正式合同。
- 解除冻结、100%复检、修改公式阈值、修改交付承诺、重大排产调整等高风险动作只能生成待人工确认草稿。
- 禁止创建虚假的 DecisionID、ConfirmationID、RunID 或 EvidenceRef。
- OMP 工程代理不得自行发布、安装、上传 Skill 或修改飞书数据。

## UI 回归
- UI v3.2.1 是受保护基线。
- 默认 UI_CHANGE_LEVEL=PATCH。
- 未经明确书面授权，禁止重构导航、页面结构、布局、主题、角色切换、多产线对比、时间窗口、数据治理、事件中心和 AI 入口。
- Payload 哈希不变不等于 UI 没有回退；所有 UI 改动必须检查功能矩阵、截图和 manifest。

## OMP 角色边界
- `architect`、`planner`、`executor`、`tester`、`reviewer` 等是工程施工代理。
- 厂长、线长、质量、设备、工艺、供应链是产品业务角色，不能写入 `.omp/agents/` 作为同义替代。
- 工程施工代理必须按任务合同传递结构化结果，不能只输出自然语言结论。
