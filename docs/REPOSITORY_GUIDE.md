# BIFROST 仓库使用与整理说明

本文档给协作开发者使用。仓库中保留可运行源码、固定测试数据、契约和必要文档；服务运行产生的日志、数据库、虚拟环境和调试快照均属于本地状态，不进入版本库。

## 1. 先看哪些目录

| 目录 | 用途 | 是否提交 |
| --- | --- | --- |
| `apps/web` | 业务看板前端 | 提交 |
| `apps/daemon` | 编排、事件、任务和治理接口 | 提交源码；数据库文件留在本地 |
| `apps/runner` | 数据读取、分析和事实集服务 | 提交 |
| `packages/contracts` | 前后端统一数据契约 | 提交 |
| `packages/gates` | 确定性校验与交付门禁 | 提交 |
| `.omp/integration` | BIFROST 与外部运行时的只读适配层 | 提交源码和固定夹具 |
| `.omp/workstreams` | 数据编译、视图投影、业务解释 | 提交源码和测试 |
| `.omp/skills` | 数据映射、质量检查、规则执行技能 | 提交 |
| `output/bifrost-ui-runtime` | 可独立启动的 BIFROST 演示运行时 | 提交 |
| `test-inputs` | 两份可复现测试数据 | 提交 |
| `docs` | 架构、验收、复现和协作说明 | 提交 |
| `knowledge` | 指标口径、业务知识和治理规则 | 提交 |

以下路径只在本机产生：`.omp/runner-venv`、`.omp/runtime-home*`、`.omp/ui-review`、`*.log`、`*.db`、`projects`、`experiments`、`runs-e2e`。`.gitignore` 已覆盖这些路径。

## 2. 两条可复现运行路径

### 2.1 完整三服务链路

在仓库根目录执行：

```powershell
corepack pnpm install --frozen-lockfile
corepack pnpm dev
```

打开 `http://127.0.0.1:3000`。默认服务端口为：daemon `8787`、runner `8788`。

### 2.2 BIFROST 看板运行时

这条路径直接读取 `test-inputs`，适合展示三产线、多角色、数据治理和事件详情：

```powershell
cd D:\Codex\智能体\workspaces\bifrost-goertek
$env:BIFROST_TEST_INPUT_ROOT = (Resolve-Path '.\test-inputs').Path
D:\anaconda3\envs\langchain\python.exe .omp\integration\serve_bifrost_ui.py --port 4173
```

打开 `http://127.0.0.1:4173/`。停止服务使用 `Ctrl+C`。

## 3. 测试数据

仓库内的两份数据用途不同：

1. `test-inputs/BIFROST_飞书导入数据包_v3_P0修复版_SIM-v2.2.xlsx`：BIFROST 外部测试数据，包含三条产线、班次 OEE、停机、告警、物料和质量冻结等数据。
2. `test-inputs/歌尔可脱敏企业测试数据集.xlsx`：企业命题格式的五类跨域数据，用于检验字段映射和跨表关联。

使用者无需修改源码。切换数据时，只需把 `BIFROST_TEST_INPUT_ROOT` 指向包含测试文件的目录，并重新启动看板运行时。

## 4. 页面操作顺序

1. **看板中心**：选择角色（厂长、线长、质量、设备、工艺、供应链），选择时间范围，勾选需要比较的产线。
2. **产线下钻**：点击产线卡片或排行条目，查看该线的 OEE、可用率、性能率、良率和趋势。
3. **事件中心**：打开黄金事件，查看影响范围、证据引用、子任务、决策草稿和人工确认状态。
4. **数据治理**：查看缺失、重复、异常值、格式、逻辑和时效六类问题；点“查看”展开证据与影响字段。
5. **管理配置**：查看指标口径、阈值和角色权限。试算只生成草稿，规则发布和高风险动作需要人工确认。
6. **AI 助手**：从左侧或顶部“问 AI”进入。当前演示模式显示上下文和快捷问题；接入真实 Aily 后，再发送自然语言问题和任务指令。

## 5. 协作提交规则

- 每个功能使用独立分支，分支名称采用 `feature/<topic>` 或 `fix/<topic>`。
- 提交前执行：

  ```powershell
  corepack pnpm test
  corepack pnpm typecheck
  git status --short
  ```

- 提交内容只包括源码、契约、固定测试夹具和说明文档；日志、数据库、虚拟环境和截图缓存保持本地。
- 合并前在 README 或变更说明中写清：改动文件、验证命令、数据版本、是否影响前端载荷。
- 协作者从 `main` 或指定功能分支开始工作，不在临时运行目录直接开发。

## 6. 本次整理记录

- 真实源码、固定测试数据、前端载荷和复现文档均保留在仓库内。
- 本地运行产物已移至仓库外的可恢复隔离目录 `D:\Codex\智能体\repo-quarantine`；仍被运行中进程占用的日志仅通过 `.gitignore` 排除，停止服务后可手动移走。
- 远程仓库发布前，应先在干净工作区确认 `git status --short` 只显示预期源码、文档和数据变更。
