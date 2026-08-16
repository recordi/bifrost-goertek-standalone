# OMP-13 施工 04B：AI 结果合同与可读呈现验收报告

## 结论

施工 04B 已完成。BIFROST AI 助手现在同时保留兼容字段 `answer` 和结构化 `result_contract`，前端优先渲染结构化合同，不再把模型原始文本或 JSON 直接铺在面板上。

本轮没有修改移动端布局、业务载荷、业务数据、Skill、角色权限或人工确认边界。

## 实现内容

### 1. 统一 AI Result Contract

文件：`.omp/integration/serve_bifrost_ui.py`

同时增加了 Windows 后台桥接的环境变量规范化，去除 `PATH/Path` 大小写重复，避免 detached OMP 子进程出现假性 provider 失败。

新增 `BIFROST-AI-RESULT-v1`，包括：

- `run_id`、`role`、`scope`、`time_window`、`event_id`
- `headline`
- `kpis`
- `risks`
- `evidence_refs`
- `recommended_actions`
- `needs_human_confirmation`
- `data_gaps`
- `confidence`
- `source.readonly` 与 `source_write_performed`

合同中的指标、风险、动作、证据和数据缺口均来自固定只读适配器；模型文本只用于生成简短结论标题和兼容的 `answer` 字段。

### 2. AI 助手分层呈现

文件：`output/bifrost-ui-runtime/src/components.jsx`

AI 面板按以下顺序展示：

1. 核心结论
2. 关键指标
3. 重点风险
4. 建议动作
5. 数据缺口
6. 证据引用（默认折叠）

高风险动作显示“需人工确认”，普通动作显示“仅生成草稿”，不会出现可直接执行的按钮。

### 3. 中文业务标签

补充 OEE、总产量、良品数、缺陷总数、良率等字段映射，避免 `oee_source`、`total_output`、`defect_total` 等英文键名直接暴露给使用者。

## 验收结果

| 检查项 | 结果 |
|---|---:|
| Python 语法检查 | PASS |
| AI Result Contract 合同测试 | 4/4 PASS |
| 六角色合同测试 | 6/6 PASS |
| 高风险人工确认边界 | PASS |
| 只读写入边界 | PASS |
| 固定夹具前端结构化渲染 | PASS |
| AI 面板关键区域 | 8 个指标、3 个风险、2 个动作、证据折叠均显示 |
| 原始 JSON 暴露 | 否 |
| 桌面端回归 | PASS |
| 移动端回归 | PASS（仅验证未回退，不继续设计） |
| UI peer overlay | 5/5 PASS |
| peer daemon bridge | 6/6 PASS |
| governance precheck | 3/3 PASS |
| peer skill adapters | 5/5 PASS |

## Grok 审查

custom-grok 已在隔离只读模式下审查当前桥接和前端链路，确认原链路是“纯文本返回 + 前端按换行猜结构”，并建议采用稳定合同和分层渲染。本轮没有把真实业务查询数据再次外发给外部模型；合同验证使用本地固定适配器结果完成。

实时 provider 说明：已在用户授权后使用本地 `adapter-test` 数据完成一次真实 custom-grok 调用。返回 `status=ok`、`contract_version=BIFROST-AI-RESULT-v1`，并成功回放到 AI 面板；只读和人工确认边界保持不变。此前后台进程的 `OMP_PROVIDER_FAILED` 已通过环境变量规范化修复。

## 回滚

本轮修改文件：

- `.omp/integration/serve_bifrost_ui.py`
- `output/bifrost-ui-runtime/src/components.jsx`
- `output/bifrost-ui-runtime/styles.css`

如需回滚，只需恢复以上三个文件到施工 04B 前版本；Overview/Event 载荷和 Skill 文件未被改动。

## 证据文件

- `.omp/ui-review/ai-contract-fixture.json`
- `.omp/ui-review/ai-contract-render.png`
- `.omp/ui-review/capture.json`
- `.omp/ui-review/arbiter.json`
- `.omp/integration/test_ai_result_contract.py`
- `.omp/integration/test_ai_contract_ui.mjs`
