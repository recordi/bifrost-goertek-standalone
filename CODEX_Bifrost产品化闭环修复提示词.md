# Codex 执行提示词：把 Bifrost 修成真正可对标 OpenDesign 的数据分析产品

你现在是 Bifrost 项目的首席工程师，直接在当前仓库中工作：

```text
C:\Users\xuan\Desktop\桌面\比赛\歌尔claude
```

## 一、最终目标

把当前 Bifrost 从“模块很多但主链未闭合的原型”，修成一个真正可演示、可验证、可发布的数据分析与 BI 产品。

产品形态对标 OpenDesign：

- 自然语言驱动任务。
- 清晰的工作台和实时执行过程。
- 专业技能自动路由。
- 高质量可视化产物。
- 独立验证和局部修复。
- 产物版本、预览、发布和导出。

Bifrost 必须具备 OpenDesign 没有的数据可信能力：

- 真实数据导入。
- 统一指标口径。
- SQL 安全执行。
- FactSet 唯一数字来源。
- 岗位权限过滤。
- 数据断言。
- 事实溯源。
- 六道 Gate 硬阻断。
- 事实评审与视觉评审分离。

最终用户流程必须是：

```text
创建项目
→ 上传真实或脱敏数据
→ 自动生成数据画像
→ 选择岗位和数据集
→ 输入自然语言诉求
→ 自动完成计划、查询、执行、事实评审、叙事和看板生成
→ 查看每个数字的来源
→ 通过 Gate 后发布
→ 导出 HTML / PDF / PPTX 或发送飞书
```

## 二、当前真实基线

开始前必须自己重新运行命令确认，以下数字只作为当前已知参考，不能直接当成最新结果：

- Runner 测试：`214` 通过、`0` 失败。
- daemon 测试：`490` 通过、`4` 失败。
- Config 测试：`8` 通过、`0` 失败。
- Context Keeper 测试：`13` 通过、`0` 失败。
- Web 测试：`4` 通过、`0` 失败。
- Contracts TypeScript 测试：`49` 通过、`0` 失败。
- daemon 类型检查约有 `193` 个错误，其中约 `84` 个在生产代码。
- Runner 类型检查约有 `5` 个测试类型错误。
- Web 构建通过。
- daemon 构建失败。

已知核心断点：

1. `apps/daemon/src/orchestrator/index.ts` 的 `executeFactStage()` 仍然直接抛出 Runner 未实现错误，没有调用已经存在的 `/internal/execute`。
2. `apps/web/src/components/ChatPanel.tsx` 仍加载 demo Profile、Role、Metrics，并发送旧请求字段，与新 RunCreateRequest 不兼容。
3. Run 路由先返回 `202`，再异步构建上下文；构建失败时 Run 状态和 SSE 失败事件可能丢失。
4. 新增的飞书、图表渲染、配色和布局模块存在大量类型错误。
5. 新增可视化和导出模块多数没有接入 Maker、orchestrator 或正式路由。
6. 发布接口仍是占位，只返回 `published: true`。
7. Web 没有真正的 `/dashboard/:dashboardId` 发布页面。
8. orchestrator 仍使用内存 Run 状态，服务重启不能恢复。
9. 取消运行只修改状态，不会中断模型、Runner、截图和交付请求。
10. 飞书 H5 认证仍返回固定测试用户，回调没有验签。

## 三、工作方式

### 3.1 本提示词视为总体方案确认

可以直接进入实现，不需要每个普通步骤都等待用户确认。

只有以下情况必须停下来询问：

- 删除真实数据或数据库。
- 修改不可兼容的公开 API。
- 需要更换核心技术路线。
- 需要创建分支或 worktree。
- 需要真实飞书凭据、生产域名或外部付费资源。

### 3.2 禁止事项

- 禁止创建新分支或 worktree。
- 禁止覆盖或回退当前工作区中其他人的未提交修改。
- 禁止使用 `git reset --hard`、`git clean -fd` 等清理命令。
- 禁止在生产代码里使用 Mock。
- 禁止用预制 FactSet 证明真实数据主链完成。
- 禁止新增静默跳过、默认通过或文本降级逻辑。
- 禁止吞掉审计、数据执行、Gate 和安全错误后继续发布。
- 禁止为了通过类型检查使用大面积 `any`、`as unknown as` 或关闭严格检查。
- 禁止继续增加未接入主链的新模块。
- 禁止只根据测试数量宣称功能完成。

### 3.3 文件与环境

- 所有中文文件按 UTF-8 读写。
- PowerShell 读取中文前设置 UTF-8 输出。
- Python 优先使用 `apps/runner/.venv/Scripts/python.exe`。
- 不新建虚拟环境。
- 使用 `pnpm.cmd`，避免 PowerShell 执行策略阻止 `pnpm.ps1`。
- 测试临时目录必须放在仓库内，测试结束后安全清理。

### 3.4 记录要求

开始前读取：

- `AGENTS.md`
- `README.md`
- `ARCHITECTURE.md`
- `Bifrost_完整架构方案_V3.md`
- `Bifrost_开发文档_V1.md`
- `Bifrost_后续计划方案_V1.md`
- `Bifrost_后续开发方案_V2.md`
- `task_plan.md`
- `progress.md`
- `findings.md`

每完成一个阶段，更新：

- `task_plan.md`
- `progress.md`
- `findings.md`

只有新增模块、部署方式、依赖或重要设计决定变化时，才更新：

- `README.md`
- `ARCHITECTURE.md`

## 四、实施顺序

必须严格按以下顺序推进。当前阶段没有通过验收，不得跳到下一阶段。

## 第一阶段：恢复稳定工程基线

### 目标

让当前已有代码重新达到可编译、可测试状态，不增加产品功能。

### 工作内容

1. 重新运行全仓类型检查、测试和构建，记录准确失败清单。
2. 修复 daemon 生产代码类型错误。
3. 修复 daemon 测试类型错误。
4. 修复 Runner 测试类型错误。
5. 修复 SQL Validator 的 `4` 个失败测试，统一 RunnerClient 改造后的错误语义和调用参数。
6. 修复测试中的 raw-storage、usage 缺失和数据库未初始化警告。
7. 确认 Config、Context Keeper、Contracts、Runner、Web 和 daemon 的测试可重复运行。

### 重点文件

```text
apps/daemon/src/agents/chart-type-selector.ts
apps/daemon/src/feishu/client.ts
apps/daemon/src/delivery/bitable-export.ts
apps/daemon/src/delivery/h5-export.ts
apps/daemon/src/delivery/message-card-export.ts
apps/daemon/src/visualization/chart-renderer.ts
apps/daemon/src/visualization/color-scheme-generator.ts
apps/daemon/src/visualization/dashboard-layout-optimizer.ts
apps/daemon/test/agents/sql-validator.test.ts
apps/runner/tests/test_execute_endpoint.py
```

### 验收

```powershell
pnpm.cmd typecheck
pnpm.cmd test
pnpm.cmd build
```

要求：

- 类型错误 `0`。
- 测试失败 `0`。
- 构建失败 `0`。
- daemon 测试不再输出原始输出、usage 或 DB 初始化异常。

## 第二阶段：修复 Web 与新 Run 契约

### 目标

让用户从真实页面能够成功创建一个使用服务端可信上下文的 Run。

### 工作内容

1. 删除 `ChatPanel` 中 demo Profile、Role、Metrics 加载。
2. 增加真实项目、岗位和数据集选择状态。
3. Run 请求只发送：

```json
{
  "brief": "分析本周各产线 OEE",
  "role_id": "plant_manager",
  "dataset_ids": ["ds_production_daily"],
  "params": {}
}
```

4. 前端加载项目真实数据集列表。
5. 数据集 Profile 未完成时明确展示 `E_PROFILE_NOT_READY`。
6. daemon 必须先建立 Run 记录和事件通道，再返回 `202`。
7. 输入构建失败时，Run 状态必须为 `failed`，用户可以通过状态接口和 SSE 读取完整错误。
8. 禁止返回服务器绝对文件路径。

### 重点文件

```text
apps/web/src/components/ChatPanel.tsx
apps/web/src/components/DatasetsPanel.tsx
apps/web/src/components/WorkspaceShell.tsx
apps/daemon/src/routes/runs.ts
apps/daemon/src/services/run-input-builder.ts
apps/daemon/src/services/project-context.ts
apps/daemon/src/routes/datasets.ts
```

### 验收

- 页面请求不再出现 demo 数据。
- 新 Run 请求通过契约校验。
- 非法可信字段被拒绝。
- Profile 未就绪、岗位不存在、数据集不存在都有可查询的失败 Run。
- 增加前后端集成测试，而不是只增加单元测试。

## 第三阶段：接通真实 Fact 执行

### 目标

真正打通：

```text
QuerySet
→ daemon
→ Runner /internal/execute
→ DuckDB
→ FactSet
→ Gate 4
```

### 工作内容

1. 扩展 `RunOrchestrationInput`，正式包含数据集执行引用、Profile 列表和 Metrics 来源。
2. 删除生产路径中的 `factset?: FactSet` 旁路。
3. 在 RunnerClient 中增加正式 `executeFactSet()` 方法。
4. `executeFactStage()` 调用 Runner `/internal/execute`。
5. 传递岗位禁止字段和最大敏感级别。
6. 数据集只使用受控相对路径，Runner 再次校验路径不能离开项目数据目录。
7. Metrics 路径必须位于项目目录，禁止任意路径读取。
8. 保存 FactSet、断言结果和安全过滤审计。
9. 任一断言失败时 Run 进入 `blocked`，不得进入 Narrative 和 Maker。
10. 修正 Runner 注释与真实执行步骤不一致的问题，确保 SQL 绑定后重新执行白名单校验。

### 重点文件

```text
apps/daemon/src/orchestrator/index.ts
apps/daemon/src/runner-client.ts
apps/daemon/src/services/run-input-builder.ts
apps/runner/src/bifrost_runner/routes/execute.py
apps/runner/src/bifrost_runner/datasets/registry.py
apps/runner/src/bifrost_runner/datasets/binder.py
apps/runner/src/bifrost_runner/factset/generator.py
```

### 必须新增的集成测试

使用真实 fixture CSV：

```text
上传文件
→ 生成 Profile
→ 构造 QuerySet
→ 调 Runner 执行
→ 得到 FactSet
→ 验证数字和断言
```

测试禁止注入预制 Profile 或 FactSet。

### 验收

- `executeFactStage()` 不再包含 Runner 未实现的 throw。
- 不传预制 FactSet 时主链能够完成 Fact 阶段。
- 未声明数据集、禁止 SQL、路径越界、敏感字段和断言失败全部被阻断。

## 第四阶段：形成真正的多 Agent 闭环

### 目标

从串行角色调用升级为按问题归属修正的 Agent 工作流。

### 工作内容

1. Narrative 输出成为 Maker 正式输入。
2. 图表类型选择器、配色和布局模块接入 Maker，而不是保持孤立模块。
3. Fact Review 的 finding 增加明确路由：

```text
SQL、时间窗口、维度错误 → Query
数据断言失败 → Fact 或阻断
指标口径冲突 → 人工审批
结论表达错误 → Narrative
布局、颜色、重叠 → Maker Patch
权限越界 → 直接阻断
```

4. Fact Review 能触发 Query 与 Fact 重新执行。
5. Presentation Review 只能修改表达和布局，禁止修改 FactSet。
6. Context Keeper 只负责上下文压缩，不得丢失指标、权限、Fact 和 finding。
7. 所有 Agent 使用统一 Runtime 接口。
8. 增加 Run Budget：模型调用次数、Token、执行时长和 Patch 轮数。
9. 增加真正的 AbortController，取消后终止模型、Runner、截图和交付调用。

### 验收

- 一个 SQL 时间窗口错误能够自动回到 Query 并重新生成 FactSet。
- 一个视觉错误只执行 Maker Patch。
- Narrative 内容能在最终看板找到对应章节。
- 取消后不再产生任何新外部副作用。

## 第五阶段：完成 BI 看板产品模型

### 目标

从“整页 HTML 生成器”升级为真正的 BI 看板产品。

### 工作内容

1. 增加 Dashboard Manifest 契约：

```text
Dashboard
→ Page
→ Widget
→ FactBinding
→ Filter
→ Layout
→ Theme
```

2. Maker 同时生成 Manifest 和 HTML。
3. 每个 KPI、图表、表格和包含数字的文本都绑定 Fact ID。
4. 图表渲染、配色和布局模块必须通过 Manifest 调用。
5. 建立不可变 Artifact 版本，禁止覆盖旧产物。
6. 增加 Dashboard、DashboardVersion 和 Publication 持久化表。
7. 实现稳定发布页面：

```text
/dashboard/:dashboardId
```

8. 实现发布、取消发布、版本查看和回滚。
9. 实现事实溯源：Fact → Query → Metric → Dataset → Filter。
10. 实现 HTML、PDF、PPTX 前端导出入口。

### 验收

- Web 构建结果中存在 Dashboard 路由。
- 发布后重启服务，Dashboard 仍然可访问。
- 每个关键数字都可以查看来源。
- 所有导出格式使用同一个 FactSet 和 DashboardVersion。

## 第六阶段：持久化、安全与交付

### 目标

达到可部署产品的最低要求。

### 工作内容

1. Run、Stage、Event、NodeCall、ArtifactVersion、Gate、Review 全量持久化。
2. SSE 支持 `Last-Event-ID` 和事件回放。
3. 服务重启后历史 Run 和 Dashboard 可恢复。
4. 增加幂等键，重复请求不重复运行和交付。
5. 所有导出路径由服务端生成，禁止任意路径写入。
6. 增加 Web 身份认证和项目权限中间件。
7. 实现真实飞书 H5 免登，删除固定测试用户。
8. 飞书回调进入业务逻辑前完成验签和防重放。
9. 新 H5、Bitable、MessageCard 导出服务接入正式交付流程。
10. 交付失败必须明确记录，不得把 Run 标记为完全成功。

### 验收

- 重启恢复通过。
- 跨项目访问被拒绝。
- 路径写入攻击被拒绝。
- 飞书伪造回调被拒绝。
- 重复回调不会重复写入。

## 第七阶段：OpenDesign 式产品体验

### 目标

让产品不仅能运行，而且达到专业产品完成度。

### 工作内容

1. 结构化 Brief：明确岗位、数据范围、目标、时间窗口和输出形式。
2. 自动技能路由：分析技能、叙事技能、视觉技能。
3. 项目级设计系统和主题 Token。
4. 工作台完整展示：

```text
对话
数据集
数据画像
运行过程
事实溯源
验证结果
项目记忆
看板预览
版本历史
发布与导出
```

5. 支持只修改一个卡片，不整页重生成。
6. 支持桌面和移动端。
7. 动画只用于表达状态和层级，禁止为了好看阻塞操作。
8. Web 主要用户流程增加组件测试和浏览器测试，不能只保留健康接口测试。

### 验收

- 首次用户无需理解内部 Agent 和 FactSet 即可完成操作。
- 专业用户可以查看完整事实和审计链。
- 同一项目能够复用岗位、口径、主题和历史修改偏好。
- 看板在桌面和移动端无溢出、遮挡和重叠。

## 五、测试与验证策略

### 5.1 默认 CI

默认 CI 必须稳定、确定性执行：

```powershell
pnpm.cmd typecheck
pnpm.cmd test
pnpm.cmd build
```

并运行不依赖外部模型的真实数据链测试：

```text
真实文件
→ Profile
→ QuerySet
→ Runner
→ FactSet
→ Gate
```

### 5.2 发布验收

发布前单独运行真实模型全流程：

```text
用户自然语言
→ Insight
→ Query
→ Runner
→ Fact Review
→ Narrative
→ Maker
→ Verify
→ Publish
```

必须使用真实配置的模型端点，不在生产代码里放 Mock。

### 5.3 每阶段验证顺序

1. 最小相关测试。
2. 受影响包类型检查。
3. 相邻集成测试。
4. 全仓类型检查。
5. 全仓测试。
6. 构建。
7. Review diff，检查是否修改任务范围外文件。
8. 第一性原理复核，确认没有更简单的实现。

## 六、最终完成定义

只有以下条件全部满足，才能宣布产品完成：

- 前端不再加载 demo Profile、Role、Metrics。
- 新 Run 请求可以从真实页面成功发起。
- Fact 阶段真实调用 Runner。
- 不存在生产 FactSet 旁路。
- 从上传文件到最终看板存在真实端到端证明。
- Dashboard Manifest、HTML 和 FactSet 完整绑定。
- Fact Review 能回到正确上游节点。
- 所有 Gate 真正阻断发布。
- Dashboard 有稳定发布页和不可变版本。
- 服务重启后 Run、事件和 Dashboard 不丢失。
- 取消运行能终止外部调用。
- 飞书认证和回调验签使用真实逻辑。
- daemon、runner、web 全部构建通过。
- 全仓类型检查错误 `0`。
- 全仓测试失败 `0`。
- 默认 CI 数据链测试通过。
- 真实模型发布验收通过。
- README、ARCHITECTURE、STATE、task_plan、progress 和实际代码一致。

## 七、执行输出要求

每次阶段完成后，用简短中文输出：

```text
完成内容：
- ...

验证结果：
- 通过 X
- 失败 0

剩余阻塞：
- ...
```

不要复读背景，不要夸大完成度，不要因为单元测试通过就宣称端到端完成。

现在开始：

1. 读取规则与项目记录。
2. 检查 `git status`，保护现有未提交改动。
3. 重新运行类型检查、测试和构建，建立最新基线。
4. 更新 `task_plan.md`。
5. 从“第一阶段：恢复稳定工程基线”开始执行。
