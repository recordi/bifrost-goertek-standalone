# Bifrost 后续开发实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在当前 Bifrost 代码基础上，完成真实数据驱动、可恢复、可审计、可发布的数据分析与 BI 看板全流程。

**Architecture:** 保留 `web -> daemon -> runner` 三服务结构。daemon 负责身份、配置、编排、持久化和交付；runner 负责文件读取、SQL 安全校验、确定性计算和 FactSet；web 只提交引用并展示状态、事实、看板和审计。Dashboard Manifest 与 HTML 共同组成看板产物，所有数字统一引用 FactSet。

**Tech Stack:** Node.js 22、pnpm 9、TypeScript、Express 5、Next.js 16、React 19、Python 3.12、FastAPI、DuckDB、SQLite、Cheerio、Playwright、Vitest、Pytest、JSON Schema、Pydantic。

> **评审修订：** 当前工作区已经存在 `@bifrost/config`、Run 请求契约、数据集注册器和运行上下文等部分实现。执行任务时以当前 Git 状态为准：文件存在则先审查、补测试和修正，禁止按“Create”步骤覆盖。本文同时补齐 Artifact 版本表、Dashboard 发布表、稳定 CI 与真实模型验收的分层。

---

## 一、实施原则

1. 先修稳定性，再接主链，再做产品功能。
2. 每个行为先写失败测试，再实现最小代码。
3. 不允许用预制 FactSet 作为端到端验收依据。
4. 不允许新增静默跳过、默认通过或“先继续运行”的关键路径逻辑。
5. 不修改用户当前未提交代码之外的无关模块。
6. 数据库迁移、删除文件和清理真实运行数据前必须单独确认。
7. 每个任务结束后运行受影响包测试；每个阶段结束后运行全仓测试。
8. 当前工作区不创建新分支和 worktree，除非用户另行明确授权。

## 二、目标文件结构

### 新增文件

```text
packages/contracts/schemas/dashboard-manifest.schema.json
packages/contracts/schemas/run-request.schema.json
apps/runner/src/bifrost_runner/datasets/registry.py
apps/runner/src/bifrost_runner/datasets/binder.py
apps/runner/src/bifrost_runner/routes/datasets.py

apps/daemon/src/services/project-context.ts
apps/daemon/src/services/run-input-builder.ts
apps/daemon/src/services/dashboard-manifest.ts
apps/daemon/src/orchestrator/cancellation.ts
apps/daemon/src/orchestrator/event-store.ts
apps/daemon/src/routes/published-dashboards.ts

apps/web/src/app/dashboard/[dashboardId]/page.tsx
apps/web/src/components/DatasetPanel.tsx
apps/web/src/components/DashboardToolbar.tsx
apps/web/src/components/RunHistoryPanel.tsx

apps/e2e/package.json
apps/e2e/tests/real-data-flow.spec.ts
```

### 重点修改文件

```text
apps/daemon/src/routes/runs.ts
apps/daemon/src/routes/datasets.ts
apps/daemon/src/routes/projects.ts
apps/daemon/src/orchestrator/index.ts
apps/daemon/src/runner-client.ts
apps/daemon/src/agents/query.ts
apps/daemon/src/agents/maker.ts
apps/daemon/src/agents/fact-review.ts
apps/daemon/src/agents/narrative.ts
apps/daemon/src/runtimes/registry.ts
apps/daemon/src/server.ts

packages/config/src/runtime.ts
packages/config/test/runtime.test.ts

packages/runtime/package.json
packages/runtime/tsconfig.json
packages/runtime/vitest.config.ts
packages/runtime/src/index.ts
packages/runtime/src/simple-factory.ts
packages/runtime/test/runtime.test.ts

apps/runner/src/bifrost_runner/main.py
apps/runner/src/bifrost_runner/routes/profile.py
apps/runner/src/bifrost_runner/routes/execute.py
apps/runner/src/bifrost_runner/factset/generator.py
apps/runner/src/bifrost_runner/middleware/hmac.py

apps/web/src/components/ChatPanel.tsx
apps/web/src/components/WorkspacePanel.tsx
apps/web/src/components/WorkspaceShell.tsx
apps/web/src/components/ProvenancePanel.tsx
apps/web/src/components/MemoryPanel.tsx
```

## 三、开发任务

### Task 1：稳定类型检查和测试基线

**Files:**

- Modify: `apps/daemon/src/routes/projects.ts`
- Modify: `apps/daemon/src/routes/runs.ts`
- Modify: `apps/daemon/test/routes/projects.test.ts`
- Modify: `apps/web/src/components/WorkspacePanel.tsx`
- Modify: `apps/web/src/components/WorkspaceShell.tsx`
- Modify: `apps/runner/src/bifrost_runner/routes/profile.py`
- Modify: `apps/runner/src/bifrost_runner/middleware/hmac.py`
- Modify: `apps/runner/tests/conftest.py`
- Modify: `apps/runner/tests/test_hmac_middleware.py`
- Test: existing daemon、web、runner tests

- [ ] **Step 1：固定当前失败清单**

运行：

```powershell
pnpm.cmd --filter daemon typecheck
pnpm.cmd --filter web typecheck
pnpm.cmd --filter runner typecheck
```

预期基线：daemon `3` 个错误、web `1` 个错误、runner `10` 个错误。若数量变化，先更新本任务记录，不能直接假设是同一问题。

- [ ] **Step 2：修复 TypeScript 不安全转换**

禁止直接把结构化类型转为 `Record<string, unknown>`。需要访问动态字段时，先建立明确的窄接口：

```typescript
interface RunStateWithParams extends RunState {
  params?: Record<string, string | number | boolean | null>;
}
```

如果参数属于正式能力，应把字段加入 `RunState` 契约，而不是长期保留局部断言。

- [ ] **Step 3：统一 WorkspacePanel 属性**

`WorkspaceShell` 与 `WorkspacePanel` 只保留一套标签切换职责。推荐由父组件管理状态：

```typescript
interface WorkspacePanelProps {
  runId: string | null;
  projectId: string;
  activeTab: TabKind;
  gates: GateResult[];
}
```

删除没有被子组件使用的 `onTabChange`，或在子组件真实需要切换时明确加入接口，不能两边定义不一致。

- [ ] **Step 4：修复 HMAC 中间件类型**

使用 Starlette 当前版本的 `RequestResponseEndpoint`：

```python
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

async def dispatch(
    self,
    request: Request,
    call_next: RequestResponseEndpoint,
) -> Response:
    return await call_next(request)
```

- [ ] **Step 5：消除测试全局环境污染**

`test_hmac_middleware.py` 不得在模块导入时永久修改 `os.environ`。改为 fixture：

```python
@pytest.fixture(autouse=True)
def hmac_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BIFROST_HMAC_SECRET", "test-hmac-middleware")
    monkeypatch.setenv("BIFROST_ENV", "test")
```

如果应用在导入时读取密钥，应把密钥读取改为请求期或应用工厂注入，不能依赖测试导入顺序。

- [ ] **Step 6：阻止测试吞掉审计错误**

为 `recordNodeCall` 增加严格模式。测试环境中 raw、usage 或 DB 未初始化时必须抛错：

```typescript
interface RecordNodeCallOptions {
  strict: boolean;
}
```

生产环境是否允许审计降级由环境策略决定，受监管模式必须阻断。

- [ ] **Step 7：验证**

运行：

```powershell
pnpm.cmd --filter daemon typecheck
pnpm.cmd --filter web typecheck
pnpm.cmd --filter runner typecheck
pnpm.cmd --filter daemon test
pnpm.cmd --filter web test
./apps/runner/.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp ./apps/runner/.test-tmp apps/runner/tests
```

预期：类型检查全部通过；Runner 全量和单文件结果一致；daemon 测试没有 raw-storage、usage、DB 初始化警告。

**Done:** 当前代码形成稳定开发基线，没有新增产品行为。

---

### Task 2：建立统一运行配置

**Files:**

- Create: `packages/config/package.json`
- Create: `packages/config/src/index.ts`
- Create: `packages/config/src/runtime.ts`
- Modify: `pnpm-workspace.yaml`
- Modify: `apps/daemon/src/config.ts`
- Modify: `apps/daemon/src/runner-client.ts`
- Modify: `apps/daemon/src/agents/sql-validator.ts`
- Modify: `apps/runner/src/bifrost_runner/config.py`
- Modify: `.env.example`
- Test: `packages/config/test/runtime.test.ts`
- Test: `apps/daemon/test/runner-client/runner-client.test.ts`

- [ ] **Step 1：先写配置一致性失败测试**

测试以下条件：

- daemon 默认 Runner 地址与 runner 默认监听端口一致。
- staging、prod 缺少 HMAC 密钥时启动失败。
- URL、端口和超时非法时启动失败。
- `sql-validator` 和 `runner-client` 使用同一配置对象。

- [ ] **Step 2：定义配置结构**

```typescript
export interface RunnerRuntimeConfig {
  baseUrl: string;
  hmacSecret: string;
  requestTimeoutMs: number;
}

export interface BifrostRuntimeConfig {
  env: 'dev' | 'test' | 'staging' | 'prod';
  daemonPort: number;
  runnerPort: number;
  runner: RunnerRuntimeConfig;
  projectsDir: string;
  runsDir: string;
  databasePath: string;
}
```

- [ ] **Step 3：固定端口定义**

选择一个唯一 Runner 默认端口。建议继续使用当前 runner 配置中的 `8788`：

```text
RUNNER_PORT=8788
RUNNER_URL=http://127.0.0.1:8788
```

daemon 禁止再硬编码 `8001`。

- [ ] **Step 4：统一 HMAC 调用**

`runnerClient` 提供唯一请求入口：

```typescript
interface RunnerRequestOptions {
  method: 'GET' | 'POST';
  path: string;
  body?: unknown;
  signal?: AbortSignal;
}

async function requestRunner<T>(options: RunnerRequestOptions): Promise<T>;
```

`sql-validator`、profile、execute 全部通过该入口调用，禁止自行 `fetch` Runner。

- [ ] **Step 5：验证**

```powershell
pnpm.cmd --filter @bifrost/config test
pnpm.cmd --filter daemon test -- runner-client
pnpm.cmd --filter daemon typecheck
```

预期：所有 Runner 请求地址、签名和超时来自同一配置。

**Done:** 不再存在 `8001`、`8788` 和 HMAC 行为不一致。

---

### Task 3：统一 Dataset、Profile 和 Metrics 契约

**Files:**

- Modify: `packages/contracts/schemas/dataset.schema.json`
- Modify: `packages/contracts/schemas/profile.schema.json`
- Create: `packages/contracts/schemas/run-request.schema.json`
- Modify: `packages/contracts/scripts/generate-ts.mjs`
- Modify: `packages/contracts/scripts/generate-py.mjs`
- Modify: `apps/runner/src/bifrost_runner/routes/profile.py`
- Modify: `apps/runner/src/bifrost_runner/profiling/__init__.py`
- Modify: `apps/daemon/src/routes/datasets.ts`
- Modify: `apps/daemon/src/security/metrics-loader.ts`
- Test: `packages/contracts/test/contracts.test.mjs`
- Test: `apps/runner/tests/test_profiling.py`
- Test: `apps/daemon/test/routes/datasets.test.ts`

- [ ] **Step 1：确定唯一 Profile 输出**

HTTP profile 路由直接返回 `Profile` 契约，不再维护临时返回结构。建议最小字段：

```json
{
  "profile_id": "pf_xxx",
  "dataset_id": "ds_xxx",
  "row_count": 100,
  "columns": [],
  "quality": {
    "score": 1,
    "defects": []
  },
  "generated_at": "2026-08-07T00:00:00.000Z"
}
```

- [ ] **Step 2：收紧数据格式**

第一轮只承诺 `csv`、`xlsx`、`parquet`。如果 JSON 必须保留，则连接器、画像、契约和执行测试必须同时支持；禁止只在上传接口声明支持。

- [ ] **Step 3：统一项目口径路径**

项目口径固定为：

```text
projects/<projectId>/knowledge/metrics.yml
```

若项目没有该文件，可以在项目创建时复制明确版本的默认模板，但运行过程中禁止临时回退到仓库根 `knowledge/metrics.yml`。

- [ ] **Step 4：新增 RunCreateRequest 契约**

```json
{
  "brief": "分析本周各产线 OEE",
  "role_id": "plant_manager",
  "dataset_ids": ["ds_production_daily"],
  "params": {}
}
```

明确删除客户端传入的完整 `profile`、`role`、`metrics` 和 `factset`。

- [ ] **Step 5：生成并检查契约**

```powershell
pnpm.cmd --filter @bifrost/contracts gen
pnpm.cmd --filter @bifrost/contracts check
pnpm.cmd --filter @bifrost/contracts test
```

预期：TS 与 Python 契约无漂移。

**Done:** Dataset、Profile、Metrics 和 Run 请求只保留一套定义。

---

### Task 4：实现 Runner 数据集注册与安全绑定

**Files:**

- Create: `apps/runner/src/bifrost_runner/datasets/__init__.py`
- Create: `apps/runner/src/bifrost_runner/datasets/registry.py`
- Create: `apps/runner/src/bifrost_runner/datasets/binder.py`
- Modify: `apps/runner/src/bifrost_runner/connectors/file.py`
- Modify: `apps/runner/src/bifrost_runner/routes/execute.py`
- Modify: `apps/runner/src/bifrost_runner/factset/generator.py`
- Test: `apps/runner/tests/test_dataset_registry.py`
- Test: `apps/runner/tests/test_dataset_binder.py`
- Test: `apps/runner/tests/test_execute_endpoint.py`

- [ ] **Step 1：写未注册数据集失败测试**

测试 QuerySet 引用了 `{{ds_a}}`，但请求没有提供 `ds_a` 时返回明确错误：

```text
E_DATASET_NOT_DECLARED
```

- [ ] **Step 2：定义数据集注册输入**

```python
class DatasetBinding(BaseModel):
    dataset_id: str
    kind: Literal["csv", "xlsx", "parquet"]
    path: str
    sheet: str | None = None
```

- [ ] **Step 3：建立 DuckDB 视图**

```python
def register_datasets(
    conn: duckdb.DuckDBPyConnection,
    bindings: list[DatasetBinding],
) -> dict[str, str]:
    """返回 dataset_id 到安全视图名的映射。"""
```

视图名必须由程序生成，文件路径使用参数绑定或严格转义，禁止把用户字符串直接拼进 SQL。

- [ ] **Step 4：替换数据集占位符**

```python
def bind_dataset_placeholders(
    sql: str,
    views: dict[str, str],
) -> str:
    """只替换已经声明并注册的数据集占位符。"""
```

替换后重新解析 SQL，确认没有遗留 `{{...}}`、未声明表和跨数据库引用。

- [ ] **Step 5：执行顺序固定**

```text
校验 QuerySet 契约
→ 校验指标和维度引用
→ 注册数据集视图
→ 绑定占位符
→ 再次执行 SQL 白名单校验
→ 执行查询
→ 生成 FactSet
→ 执行断言
→ 权限过滤
→ 敏感值清理
```

- [ ] **Step 6：验证**

```powershell
./apps/runner/.venv/Scripts/python.exe -m pytest -q apps/runner/tests/test_dataset_registry.py apps/runner/tests/test_dataset_binder.py apps/runner/tests/test_execute_endpoint.py
```

预期：真实 CSV、XLSX、Parquet 均能注册和查询；路径注入、未声明表和目录伪装文件全部失败。

**Done:** Runner 能从真实数据文件安全执行 QuerySet。

---

### Task 5：由 daemon 构建可信运行上下文

**Files:**

- Create: `apps/daemon/src/services/project-context.ts`
- Create: `apps/daemon/src/services/run-input-builder.ts`
- Modify: `apps/daemon/src/routes/runs.ts`
- Modify: `apps/daemon/src/routes/projects.ts`
- Modify: `apps/daemon/src/routes/datasets.ts`
- Modify: `apps/daemon/src/security/role-loader.ts`
- Modify: `apps/daemon/src/security/metrics-loader.ts`
- Test: `apps/daemon/test/services/project-context.test.ts`
- Test: `apps/daemon/test/services/run-input-builder.test.ts`
- Test: `apps/daemon/test/routes/runs.test.ts`

- [ ] **Step 1：写前端伪造配置负例**

请求中即使包含 `role`、`profile`、`metrics`、`factset` 字段，服务端也必须拒绝或忽略并记录非法字段，不能使用这些值。

- [ ] **Step 2：定义项目上下文**

```typescript
export interface ProjectContext {
  projectId: string;
  role: RoleProfile;
  metrics: Metrics;
  datasets: Dataset[];
  profiles: Profile[];
  memory: MemoryDigest;
}
```

- [ ] **Step 3：构建运行输入**

```typescript
export async function buildRunInput(
  request: RunCreateRequest,
  actor: AuthenticatedActor,
): Promise<RunOrchestrationInput>;
```

函数内部完成：项目访问校验、岗位加载、数据集存在性校验、Profile 就绪检查、Metrics 加载、记忆摘要加载和安全边界检查。

- [ ] **Step 4：画像未完成时明确失败**

返回：

```json
{
  "code": "E_PROFILE_NOT_READY",
  "dataset_id": "ds_xxx"
}
```

不允许运行过程中临时猜测数据列类型。

- [ ] **Step 5：验证**

```powershell
pnpm.cmd --filter daemon test -- project-context run-input-builder runs
pnpm.cmd --filter daemon typecheck
```

**Done:** 前端只提交引用，可信配置全部由 daemon 加载。

---

### Task 6：接通 orchestrator Fact 阶段

**Files:**

- Modify: `apps/daemon/src/runner-client.ts`
- Modify: `apps/daemon/src/orchestrator/index.ts`
- Modify: `apps/daemon/src/orchestrator/persistence.ts`
- Modify: `apps/daemon/src/routes/runs.ts`
- Test: `apps/daemon/test/orchestrator/fact-stage.test.ts`
- Test: `apps/daemon/test/orchestrator/index.test.ts`
- Test: `apps/daemon/test/integration/real-fact-flow.test.ts`

- [ ] **Step 1：删除生产路径中的预制 FactSet 旁路**

`RunOrchestrationInput.factset` 只能存在于明确的单元测试 helper，不能存在于生产请求和生产编排接口。

- [ ] **Step 2：定义 Runner execute 调用**

```typescript
interface ExecuteFactRequest {
  queryset: QuerySet;
  role_id: string;
  metrics_source: string;
  datasets: Array<{
    dataset_id: string;
    kind: 'csv' | 'xlsx' | 'parquet';
    path: string;
    sheet?: string;
  }>;
  forbidden_fields: string[];
  max_sensitivity: 'public' | 'internal' | 'confidential';
  run_id: string;
}
```

- [ ] **Step 3：实现 executeFactStage**

```typescript
const result = await runnerClient.executeFactSet({
  queryset: state.artifacts.queryset,
  role: input.role,
  metricsPath: input.metricsPath,
  datasets: input.datasets,
  runId: input.runId,
  signal: input.signal,
});

state.artifacts.factset = result.factset;
```

如果断言失败，保存 FactSet 和断言结果后把运行标记为 `blocked`，不得进入 Narrative 和 Maker。

- [ ] **Step 4：持久化 FactSet**

FactSet 写入受控 artifact 目录，并在 `run_artifacts` 中登记内容摘要和路径。API 返回 artifact ID，不返回绝对路径。

- [ ] **Step 5：验证真实链路**

测试必须使用 fixture CSV，经真实 Runner HTTP 调用完成：

```text
QuerySet
→ Runner
→ DuckDB
→ FactSet
→ Gate 4
```

预期：不注入 FactSet，测试仍通过。

**Done:** 主编排第一次具备真实数据计算能力。

---

### Task 7：修正 Agent 输入输出和问题路由

**Files:**

- Modify: `packages/contracts/schemas/analysis-plan.schema.json`
- Modify: `packages/contracts/schemas/review.schema.json`
- Create: `packages/contracts/schemas/narrative-plan.schema.json`
- Modify: `apps/daemon/src/agents/types.ts`
- Modify: `apps/daemon/src/agents/fact-review.ts`
- Modify: `apps/daemon/src/agents/narrative.ts`
- Modify: `apps/daemon/src/agents/maker.ts`
- Modify: `apps/daemon/src/orchestrator/index.ts`
- Test: `apps/daemon/test/agents/narrative.test.ts`
- Test: `apps/daemon/test/orchestrator/review-routing.test.ts`

- [ ] **Step 1：定义 NarrativePlan**

```typescript
interface NarrativePlan {
  headline: string;
  executiveSummary: string;
  sections: Array<{
    sectionId: string;
    purpose: string;
    factIds: string[];
    preferredChart?: ChartSpec;
  }>;
  cautions: string[];
}
```

- [ ] **Step 2：Maker 必须消费 NarrativePlan**

```typescript
interface MakerPayload {
  plan: AnalysisPlan;
  narrative: NarrativePlan;
  factset: FactSet;
  mode: MakerMode;
}
```

Maker 不得自行重新解释指标或生成 NarrativePlan 中不存在的业务结论。

- [ ] **Step 3：定义 Review 路由目标**

```typescript
type FindingRoute =
  | 'query'
  | 'fact'
  | 'metrics_approval'
  | 'narrative'
  | 'maker_patch'
  | 'block';
```

- [ ] **Step 4：按问题类型回到正确节点**

```text
SQL、维度、时间窗口错误 → query
数据缺失、断言失败 → fact 或 block
指标口径冲突 → metrics_approval
结论表达错误 → narrative
布局、颜色、遮挡 → maker_patch
权限越界 → block
```

- [ ] **Step 5：限制修正范围**

每次路由必须生成新的 artifact 版本并保留父版本，不能原地覆盖。最大总修正轮次写入运行预算。

- [ ] **Step 6：验证**

构造一个 Query 时间窗口错误，验证流程只重跑 Query、Fact 及后续阶段；构造一个颜色问题，验证只执行 Maker Patch。

**Done:** 多 Agent 从串行调用升级为按问题归属闭环协作。

---

### Task 8：统一 Runtime、取消和运行预算

**Files:**

- Modify: `packages/runtime/src/index.ts`
- Modify: `packages/runtime/src/simple-factory.ts`
- Modify: `apps/daemon/src/runtimes/registry.ts`
- Modify: all files under `apps/daemon/src/agents/`
- Create: `apps/daemon/src/orchestrator/cancellation.ts`
- Modify: `apps/daemon/src/orchestrator/index.ts`
- Modify: `apps/daemon/src/routes/runs.ts`
- Test: `apps/daemon/test/orchestrator/cancellation.test.ts`
- Test: `apps/daemon/test/runtimes/budget.test.ts`

- [ ] **Step 1：定义统一调用接口**

```typescript
interface AgentCallOptions {
  runId: string;
  node: string;
  messages: RuntimeMessage[];
  responseSchema: object;
  signal: AbortSignal;
  timeoutMs: number;
}
```

- [ ] **Step 2：定义运行预算**

```typescript
interface RunBudget {
  maxModelCalls: number;
  maxInputTokens: number;
  maxOutputTokens: number;
  maxDurationMs: number;
  maxPatchRounds: number;
}
```

超出预算时返回明确的 `E_RUN_BUDGET_EXCEEDED`，不得继续调用模型。

- [ ] **Step 3：真正取消运行**

每个 Run 持有一个 `AbortController`。取消接口执行：

```typescript
controller.abort(new Error('Run cancelled by user'));
```

Runner fetch、模型调用、截图和交付都必须接收同一 `AbortSignal`。

- [ ] **Step 4：移除 Agent 直接创建 OpenAI Client**

所有 Agent 通过 Runtime Registry 调用。Agent 文件只负责 Prompt、契约解析和领域逻辑。

- [ ] **Step 5：验证**

启动一个阻塞模型调用，执行取消后验证：

- 模型调用收到 abort。
- 后续节点没有开始。
- 没有生成新的截图和交付请求。
- Run 最终状态为 `cancelled`。

**Done:** 模型调用、Token、超时和取消由统一运行时管理。

---

### Task 9：完成运行持久化和 SSE 回放

**Files:**

- Modify: `apps/daemon/src/db/migrations/001_init.sql`
- Create: `apps/daemon/src/db/migrations/002_run_events.sql`
- Modify: `apps/daemon/src/db/repositories/runs.ts`
- Modify: `apps/daemon/src/db/repositories/run-artifacts.ts`
- Modify: `apps/daemon/src/db/repositories/node-calls.ts`
- Create: `apps/daemon/src/orchestrator/event-store.ts`
- Modify: `apps/daemon/src/orchestrator/index.ts`
- Modify: `apps/daemon/src/routes/runs.ts`
- Test: `apps/daemon/test/db/run-events.test.ts`
- Test: `apps/daemon/test/routes/sse-replay.test.ts`
- Test: `apps/daemon/test/orchestrator/recovery.test.ts`

- [ ] **Step 1：新增事件表**

```sql
CREATE TABLE run_events (
  event_id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (run_id) REFERENCES runs(id)
);
```

- [ ] **Step 2：事件先落盘再广播**

```typescript
await eventStore.append(runId, event);
emitter.emit('event', event);
```

事件写入失败时，运行进入失败状态，不能只广播内存事件。

- [ ] **Step 3：支持 Last-Event-ID**

SSE 客户端传入 `Last-Event-ID` 后，服务端先读取缺失事件，再订阅实时事件。

- [ ] **Step 4：实现启动恢复**

daemon 启动时：

- 已完成 Run 直接可读。
- running 状态但没有活动执行器的 Run 标记为 `interrupted`。
- 用户可以从最后一个安全阶段重新运行。

- [ ] **Step 5：验证**

测试运行中断、daemon 重建、SSE 重连和历史 artifact 读取。

**Done:** 运行记录不依赖内存 Map 存活。

---

### Task 10：建立 Dashboard Manifest 和发布版本

**Files:**

- Create: `packages/contracts/schemas/dashboard-manifest.schema.json`
- Create: `apps/daemon/src/services/dashboard-manifest.ts`
- Modify: `apps/daemon/src/agents/maker.ts`
- Modify: `apps/daemon/src/orchestrator/index.ts`
- Create: `apps/daemon/src/routes/published-dashboards.ts`
- Modify: `apps/daemon/src/routes/runs.ts`
- Test: `apps/daemon/test/services/dashboard-manifest.test.ts`
- Test: `apps/daemon/test/routes/published-dashboards.test.ts`

- [ ] **Step 1：定义 Manifest 契约**

```typescript
interface DashboardManifest {
  dashboardId: string;
  runId: string;
  title: string;
  factsetId: string;
  pages: Array<{
    pageId: string;
    title: string;
    layout: 'grid' | 'freeform';
    widgets: DashboardWidget[];
  }>;
  filters: DashboardFilter[];
  theme: {
    designSystemId: string;
    tokenVersion: string;
  };
}
```

- [ ] **Step 2：每个 Widget 绑定事实**

```typescript
interface DashboardWidget {
  widgetId: string;
  cardAnchor: string;
  kind: 'kpi' | 'chart' | 'table' | 'text';
  factIds: string[];
  chartSpec?: ChartSpec;
}
```

文本 Widget 如果包含业务数字，也必须声明 `factIds`。

- [ ] **Step 3：Maker 同时输出 HTML 和 Manifest**

Maker 输出使用结构化外壳：

```json
{
  "manifest": {},
  "html": "<!doctype html>..."
}
```

Gate 先验证 Manifest，再验证 HTML 绑定。

- [ ] **Step 4：实现发布版本**

发布操作生成不可变版本：

```text
published/<dashboardId>/<version>/manifest.json
published/<dashboardId>/<version>/index.html
```

取消发布只修改发布状态，不删除历史版本。

- [ ] **Step 5：限制导出路径**

删除外部自由传入 `outputPath` 的能力。导出路径由服务端根据 run 和格式生成。

- [ ] **Step 6：验证**

验证 Manifest 中的所有 Fact ID 存在，发布版本重启后可读取，外部路径写入请求被拒绝。

**Done:** 看板拥有稳定产品模型和不可变发布版本。

---

### Task 11：补齐 Web 工作台

**Files:**

- Create: `apps/web/src/app/dashboard/[runId]/page.tsx`
- Create: `apps/web/src/components/DatasetPanel.tsx`
- Create: `apps/web/src/components/DashboardToolbar.tsx`
- Create: `apps/web/src/components/RunHistoryPanel.tsx`
- Modify: `apps/web/src/components/ChatPanel.tsx`
- Modify: `apps/web/src/components/WorkspacePanel.tsx`
- Modify: `apps/web/src/components/WorkspaceShell.tsx`
- Modify: `apps/web/src/components/ProvenancePanel.tsx`
- Modify: `apps/web/src/components/MemoryPanel.tsx`
- Test: `apps/web/test/workspace.test.tsx`
- Test: `apps/web/test/dashboard-page.test.tsx`

- [ ] **Step 1：删除 demo 数据加载**

`ChatPanel` 只提交：

```typescript
{
  brief,
  role_id: roleId,
  dataset_ids: selectedDatasetIds,
  params: {}
}
```

- [ ] **Step 2：实现数据标签**

展示：数据集名称、格式、行数、画像状态、质量分数和缺陷。禁止展示服务器绝对路径。

- [ ] **Step 3：实现溯源标签**

用户点击事实后展示：

```text
Fact
→ Query ID
→ SQL 摘要
→ Metric 定义
→ Dataset
→ Filter 和时间窗口
```

- [ ] **Step 4：实现发布页**

`/dashboard/[runId]` 只读取已发布或明确允许预览的 artifact，不依赖 daemon 内存状态。

- [ ] **Step 5：实现工具栏**

提供：发布、取消发布、HTML/PDF/PPTX 导出、版本查看和复制链接。

- [ ] **Step 6：实现运行历史**

展示 Run 状态、阶段、耗时、是否可发布和历史版本。SSE 断线后使用事件回放恢复。

- [ ] **Step 7：验证**

```powershell
pnpm.cmd --filter web test
pnpm.cmd --filter web typecheck
pnpm.cmd --filter web build
```

使用浏览器验证首页、运行过程、看板发布页、移动端宽度和 iframe 保活。

**Done:** Web 从演示壳升级为真实数据工作台。

---

### Task 12：完成认证、权限和飞书交付

**Files:**

- Modify: `apps/daemon/src/server.ts`
- Create: `apps/daemon/src/security/auth-middleware.ts`
- Modify: `apps/daemon/src/security/feishu-auth.ts`
- Modify: `apps/daemon/src/routes/feishu-callback.ts`
- Modify: `apps/daemon/src/delivery/feishu-channel.ts`
- Modify: `apps/daemon/src/delivery/bitable-queue.ts`
- Create: `apps/daemon/src/delivery/token-manager.ts`
- Modify: `apps/daemon/src/routes/datasets.ts`
- Modify: `apps/daemon/src/routes/runs.ts`
- Test: `apps/daemon/test/security/auth-middleware.test.ts`
- Test: `apps/daemon/test/security/feishu-auth.test.ts`
- Test: `apps/daemon/test/routes/feishu-callback.test.ts`

- [ ] **Step 1：统一 Actor 模型**

```typescript
interface AuthenticatedActor {
  userId: string;
  tenantId: string;
  roles: string[];
  projectIds: string[];
  source: 'web' | 'feishu';
}
```

- [ ] **Step 2：所有项目接口强制权限校验**

数据集、运行、FactSet、Artifact、Memory、Export 和 Published Dashboard 必须校验 actor 是否拥有项目访问权。

- [ ] **Step 3：实现飞书三步免登**

```text
前端 code
→ 服务端换 user_access_token
→ 查询飞书用户
→ 映射 Bifrost Actor 和岗位
```

固定测试用户代码必须删除。

- [ ] **Step 4：实现回调验签**

回调进入业务逻辑前验证签名、时间戳和重放窗口。验签失败返回 `401`，不得入队。

- [ ] **Step 5：统一 Token 管理**

FeishuChannel 和 BitableQueue 共用一个 TokenManager，按过期时间缓存，刷新失败直接失败，不使用旧 Token 猜测重试。

- [ ] **Step 6：验证**

覆盖非法签名、跨项目访问、过期 Token、重复回调和岗位越权。

**Done:** Web 和飞书使用统一身份与权限边界。

---

### Task 13：建立真实端到端测试

**Files:**

- Create: `apps/e2e/package.json`
- Create: `apps/e2e/playwright.config.ts`
- Create: `apps/e2e/tests/real-data-flow.spec.ts`
- Create: `fixtures/e2e/production_daily.csv`
- Create: `fixtures/e2e/metrics.yml`
- Create: `fixtures/e2e/role.yml`
- Modify: `package.json`
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1：固定脱敏样例数据**

样例必须包含：正常值、空值、异常值、至少两个产线、至少两个时间周期和一个禁止字段。

- [ ] **Step 2：测试真实主链**

测试步骤：

```text
创建项目
→ 上传 CSV
→ 等待 Profile ready
→ 上传或初始化 metrics.yml
→ 发起 Run
→ 等待 FactSet
→ 等待看板和 Gate
→ 发布
→ 打开 /dashboard/:runId
→ 查看一个事实的溯源
→ 导出 HTML
```

禁止在测试中注入 Profile、FactSet 或 Agent 最终产物。

- [ ] **Step 3：增加关键失败链**

至少覆盖：

- 未声明指标。
- 未声明数据集。
- SQL 禁止函数。
- 数据断言失败。
- 岗位禁止字段。
- Gate 失败阻断发布。
- 取消运行后无后续副作用。
- 服务重启后恢复历史看板。

- [ ] **Step 4：增加根命令**

```json
{
  "scripts": {
    "test:e2e": "pnpm --filter @bifrost/e2e test",
    "verify": "pnpm typecheck && pnpm test && pnpm test:e2e"
  }
}
```

- [ ] **Step 5：验证**

```powershell
pnpm.cmd verify
```

预期：全仓类型检查、单元测试、集成测试和真实端到端测试全部通过。

**Done:** 项目第一次拥有真实全流程证明。

---

### Task 14：文档、部署和最终验收

**Files:**

- Modify: `README.md`
- Modify: `ARCHITECTURE.md`
- Modify: `.env.example`
- Modify: `STATE.md`
- Modify: `AUDIT_FINDINGS.md`
- Modify: `task_plan.md`
- Modify: `progress.md`
- Create: `docs/operations/deployment.md`
- Create: `docs/operations/troubleshooting.md`
- Create: `docs/demo/bifrost-demo-script.md`

- [ ] **Step 1：更新 README**

必须包含：功能简介、真实架构、本地运行、部署、测试命令、搜索记录、已完成能力和未完成事项。

- [ ] **Step 2：更新 ARCHITECTURE**

写清每个模块职责、调用关系、数据流、信任边界、运行恢复和发布版本模型。

- [ ] **Step 3：更新审计记录**

只关闭已经有测试证明的问题。代码存在但未接入主链的能力不能标记完成。

- [ ] **Step 4：编写演示脚本**

演示严格按真实用户路径执行，不手工改中间文件：

```text
上传数据
→ 提问
→ 查看分析过程
→ 查看事实溯源
→ 查看 Gate
→ 发布看板
→ 飞书交付
```

- [ ] **Step 5：最终验证**

```powershell
pnpm.cmd verify
pnpm.cmd build
git status --short
```

最终报告只记录：通过数量、失败数量、被阻塞的外部依赖和未关闭问题。

**Done:** 文档、代码、测试和演示描述一致。

## 四、阶段执行顺序

```text
Task 1
  ↓
Task 2
  ↓
Task 3
  ↓
Task 4
  ↓
Task 5
  ↓
Task 6
  ↓
Task 7 ──→ Task 8
  ↓          ↓
Task 9 ──────┘
  ↓
Task 10
  ↓
Task 11
  ↓
Task 12
  ↓
Task 13
  ↓
Task 14
```

允许并行的范围：

- Task 7 的 Narrative 契约与 Task 8 的 Runtime 基础包可以在接口冻结后并行。
- Task 11 的只读面板可以在 Task 10 的 API 契约确定后并行。
- Task 12 的飞书 TokenManager 可以与 Web 工作台并行。

禁止并行的范围：

- Dataset、Profile、Metrics 契约修改与 Runner 执行器修改。
- 数据库迁移与运行持久化。
- Dashboard Manifest 契约与 Maker 输出格式。

## 五、每个任务的统一验收

每个任务结束前必须依次执行：

1. Review 当前 diff，检查是否修改了任务范围外文件。
2. 检查是否存在吞错、静默跳过、默认通过和未受控路径。
3. 运行最小相关测试。
4. 运行受影响包类型检查。
5. 运行相邻集成测试。
6. 对照任务的 `Done` 条件逐条确认。
7. 更新 `progress.md`，但不提前宣称后续任务完成。

## 六、最终完成定义

只有同时满足以下条件，才能宣布后续开发完成：

- 前端不再加载 demo Profile、Role 和 Metrics。
- Run API 不再接受客户端提供的可信配置和 FactSet。
- Fact 阶段真实调用 Runner 并查询上传的数据文件。
- Fact Review、Narrative、Maker 和 Presentation Review 形成明确路由闭环。
- Dashboard Manifest、HTML 和发布版本全部存在。
- `/dashboard/:runId` 可以稳定访问。
- Run、Event、Artifact、Gate 和 Review 在重启后可恢复。
- 取消运行能终止外部调用和交付副作用。
- 飞书免登和回调验签使用真实逻辑。
- 全仓类型检查、测试、构建和真实端到端测试全部通过。
- README、ARCHITECTURE、STATE 和审计文档与代码一致。
