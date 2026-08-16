# OMP-17 三任务并行收口验收报告

## 结论

三条工作流已完成一个可运行的只读垂直切片：

1. 原始数据自动适配：数据源档案、映射摘要、数据质量摘要、关联候选、指标能力清单和动态 Overview/Event Payload 存根。
2. 展示语义层：业务页面使用中文标签和可读状态，原始字段只作为证据详情。
3. 同学 Skill 后处理桥：a01/a02/a03/a07/a08 通过统一合同以只读后处理方式接入，不覆盖 BIFROST 权威指标。

## 新增接口

| 接口 | 作用 |
|---|---|
| `POST /api/data-adapt` | 对允许目录内的 xlsx/csv/json 执行只读适配 |
| `POST /api/peer-postprocess` | 对统一任务合同执行角色范围内的同学 Skill 后处理 |
| `GET /api/presentation-semantics` | 返回展示层安全约束 |

## 验收结果

- 自动适配单元测试：2/2 PASS
- 展示语义单元测试：2/2 PASS
- 同学 Skill 后处理单元测试：1/1 PASS
- API 合同测试：3/3 PASS
- 规则引擎回归：5/5 PASS
- Peer Skill 原有回归：5/5 PASS
- AI 结果合同回归：4/4 PASS
- 数据治理回归：3/3 PASS
- UI Peer Overlay 回归：5/5 PASS

## 两套数据试跑

同一条适配流程已对本地两份团队工程化 Excel 运行：

- 19 表版本：映射状态 `needs_confirmation`，发现 50 条质量问题；
- 20 表工程化修正版：映射状态 `needs_confirmation`，发现 55 条质量问题；
- 两者均生成统一 `overview` 和 `event` Payload 存根；
- 未修改 UI、Skill、原始数据和正式指标；
- 因字段存在歧义和缺口，系统没有伪造 OEE、SPC、MTBF 或供应风险。

## Grok 审查说明

三路 custom-grok 分别审查了自动适配、治理边界和前端/Skill 集成。自动适配草案中存在“所有字段直接转为小写字段名”和语法错误，未被合入；最终实现复用了现有只读映射 Skill 和 Peer Skill 执行器。

## 尚未宣称完成的部分

- 当前 Payload 编译器输出的是安全存根，不会凭空生成业务指标；
- 真实生产环境的文件上传、映射确认界面和多维表实时写回仍需下一阶段接入；
- 官方脱敏原始工作簿仍需实际导入后，才能完成第二数据源的完整端到端演示。

## 真实数据功能测试补充

使用同一条 `AutoAdaptPipeline` 分别运行两份本地团队数据：

| 数据 | 表数 | 映射状态 | 质量发现 | 关联候选 | 可用能力 |
|---|---:|---|---:|---:|---|
| v3 第一阶段 | 19 | `needs_confirmation` | 50 | 248 | 良率 |
| 工程化修正版 | 20 | `needs_confirmation` | 55 | 242 | 良率 |

两份数据均生成 `overview` 和 `event` Payload 存根，均保持 `source_write_performed=false`。OEE、SPC、MTBF 和供应风险被标记为 `not_observable`，原因是必要字段尚未完成映射确认，系统未强行计算。

Peer 真实适配器测试：`PASS`，3 个任务、5 个 Skill 输出、只读边界保持有效。

## 安全边界

- `source_write_performed=false`
- Peer Skill 为 `readonly_postprocessor`
- 原始字段不进入业务标题
- 缺少必要字段时返回 `not_observable` 或 `needs_confirmation`
- 高风险动作不会自动执行

## 最新补充：映射确认与统一载荷回归（2026-08-14）

本轮在原有三条工作流之上补齐了“映射确认 → 统一数据集 → 动态载荷”的编译链，并修正了顶层能力清单与实际载荷能力不一致的问题。

| 数据 | 映射状态 | 已批准映射 | 待确认映射 | 统一记录数 | 可计算能力 |
|---|---|---:|---:|---:|---|
| `BIFROST_飞书导入数据包_v3_5M1E第一阶段.xlsx` | `needs_confirmation` | 15 | 213 | 525 | OEE、良率 |
| `BIFROST_飞书导入数据包_v3_5M1E第一阶段_工程化修正.xlsx` | `needs_confirmation` | 32 | 182 | 5000（有界采样） | OEE、良率 |

两套数据均生成 `BIFROST_OVERVIEW_DYNAMIC_v1` 与 `BIFROST_EVENT_DYNAMIC_v1`。OEE 只在开动率、性能率、质量率均已确认且有数值时计算；SPC、MTBF、供应风险因缺少必要字段仍标记为 `not_observable`，不强行补算。计算结果同时保留物理证据引用和 `source_write_performed=false`。

最新实测 OEE：第一阶段数据 `0.6063113304`，工程化修正版 `0.6049498705`。映射仍处于 `needs_confirmation` 是预期的安全状态，不代表流程失败；确认具体字段后才会提升为 `approved`。

回归结果：新增工作流测试 9/9 PASS，原有集成回归 28/28 PASS。当前完成的是后端适配与载荷编译，浏览器端文件上传、映射确认界面以及动态载荷切换尚未接入。

## UI 接入第一步（2026-08-14）

管理配置页已增加“数据源自动适配”只读试运行面板：可提交服务器允许目录内的数据文件路径，调用 `/api/data-adapt`，展示映射状态、统一记录数、已批准/待确认映射数、可计算指标和数据缺口，并可勾选待确认字段后重新提交确认。面板可将已生成的动态 Payload 投影为“动态适配数据（只读）”预览视图，不会覆盖正式看板载荷；完整多角色趋势和产线下钻仍需后续补充字段投影。

UI 静态回归与历史集成回归合计 `29/29 PASS`。
