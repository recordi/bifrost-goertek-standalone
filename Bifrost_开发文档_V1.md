# Bifrost 开发文档 V1

> 对应架构方案 **V3**（2026-08-04）· 面向实现，可直接据此建仓、拆工单、写代码
>
> **与架构文档的分工**：`Bifrost_完整架构方案_V3.md` 回答"为什么这么设计"，本文档回答"照着这个怎么写"。凡两者冲突，以架构文档的设计意图为准、以本文档的字段与接口定义为准。

## 目录

0. 文档约定
1. 技术栈与版本锁定
2. 仓库结构
3. 核心数据契约（本文档最重要的部分）
4. 模块划分与职责边界
5. Agent 节点实现规范
6. Gate 实现细节
7. 服务端 API
8. 持久化 schema
9. 前端工作台：整体照搬 open-design 外壳
10. 飞书集成实现
11. 开发环境搭建
12. 测试策略
13. 可观测性与审计
14. 安全实现
15. 工程规范
16. 任务分解（S0–S5 工单）
17. 附录

---

## 0. 文档约定

**术语。**"节点"指一次带特定系统提示、特定注入知识、特定输出契约的模型调用（架构文档 3.3）；"执行体"指承载模型调用的外部 code-agent CLI 或 API 端点；"产物"专指制作节点输出的自包含 HTML；"事实"指 FactSet 中的一条记录。

**标注。**`[P0]` 为主链路必需，缺了跑不通；`[P1]` 为完整体验必需；`[P2]` 为加分项，可延后。

**代码块中的省略。**`…` 表示省略同类字段，不表示可选。

**字段命名。**JSON 契约统一 `snake_case`（跨 Node/Python 两侧，避免转换层）；TypeScript 内部变量用 `camelCase`；HTML 属性用 `kebab-case` 且统一 `data-bf-*` 前缀（`data-fact` 除外，它高频出现，不加前缀以减少产物体积）。

---

## 1. 技术栈与版本锁定

### 1.1 双运行时的决定

Bifrost 是 **Node + Python 双进程**，不是纯 Node。原因是选型里两个不可替代的组件分属两个生态：DuckDB 的 Python 绑定成熟度与 `pandera` 的声明式断言在 Node 侧没有同等替代品，而 Agent 编排、SSE、产物 lint、Playwright 的生态在 Node 侧。硬凑成单一运行时的代价高于跨进程通信的代价。

分工是清晰的：**Node 侧（daemon）不碰数据，Python 侧（runner）不碰模型。**

```
apps/daemon  (Node)    编排 · Agent 调用 · SSE · 产物 lint · 截图 · 飞书 · API
      ↕ 本地 HTTP + HMAC 签名（仅 127.0.0.1 监听）
apps/runner  (Python)  DuckDB 执行 · profiling · pandera 断言 · FactSet 生成
```

这条边界同时是安全边界：生产环境下数据库凭据**只存在于 runner 进程**，daemon 与 Agent 执行体都拿不到（详见 14 章）。

### 1.2 版本表

| 组件 | 版本 | 用途 | 备注 |
| --- | --- | --- | --- |
| Node.js | 22 LTS | daemon / web | 用 `corepack` 固定 pnpm |
| pnpm | 9.x | monorepo | workspace 协议 |
| TypeScript | 5.6+ | 全 Node 侧 | `strict: true`，禁用 `any` 逃逸 |
| Express | 5.x | daemon HTTP | 与 open-design 对齐，便于参照其路由组织 |
| better-sqlite3 | 11.x | 持久化 | 同步 API，简化事务 |
| cheerio | 1.x | 产物 DOM 级 lint | 替代 open-design 的 grep 式实现 |
| Playwright | 1.6x | 截图 | 只装 chromium |
| Next.js | 16.x | 工作台 | App Router |
| React | 19.x | 工作台 | — |
| ECharts | 5.5+ | 交互版图表 | 离线版可不引 |
| Python | 3.12 | runner | — |
| uv | 最新 | Python 依赖管理 | 比 poetry 快，锁文件可复现 |
| FastAPI | 0.11x | runner HTTP | — |
| DuckDB (python) | 1.1+ | 计算引擎 | 直读 xlsx/csv/parquet/DB |
| pandera | 0.20+ | 数据断言 | 声明式 schema |
| pydantic | 2.x | runner 侧契约 | 由 JSON Schema 生成 |
| flint-chart | 0.4.x | **可选**图表 IR | 仅模板脚手架与编码校验，非必经通路 |

**锁定纪律：**`pnpm-lock.yaml` 与 `uv.lock` 必须提交；CI 用 `--frozen-lockfile` / `uv sync --locked`；任何依赖新增需在 PR 描述里写明许可证（见 15.4）。

---

## 2. 仓库结构

不 fork open-design，建独立仓库并沿用其目录约定（架构文档第九章）。

```
bifrost/
├── apps/
│   ├── daemon/                 # Node 编排服务
│   │   └── src/
│   │       ├── server.ts               # 路由注册与启动
│   │       ├── routes/                 # 按资源分文件
│   │       ├── agents/                 # 六个节点各一个文件
│   │       │   ├── governance.ts
│   │       │   ├── insight.ts
│   │       │   ├── query.ts
│   │       │   ├── fact-review.ts
│   │       │   ├── maker.ts
│   │       │   └── presentation-review.ts
│   │       ├── prompts/
│   │       │   ├── assemble.ts         # 注入顺序的唯一实现
│   │       │   └── contracts/          # 每个节点的输出契约文本
│   │       ├── runtimes/
│   │       │   ├── defs/               # 每种执行体一个描述文件
│   │       │   └── spawn.ts
│   │       ├── gates/                  # gate 1-6 编排（1-5 调 packages/gates）
│   │       ├── screenshot/             # Playwright 封装
│   │       ├── memory/                 # 三层记忆读写
│   │       ├── delivery/feishu/
│   │       ├── runner-client.ts         # 调 Python runner
│   │       └── db/                     # migrations + queries
│   ├── runner/                 # Python 数据服务
│   │   └── src/bifrost_runner/
│   │       ├── main.py                 # FastAPI 入口
│   │       ├── connectors/             # L0：xlsx/csv/parquet/mysql/pg/bitable
│   │       ├── profiling/              # L1
│   │       ├── semantic/               # L2：metrics.yml loader + SQL 白名单校验
│   │       ├── execute/                # QuerySet 执行 → FactSet
│   │       ├── assertions/             # pandera 断言集
│   │       └── security/               # 岗位过滤 · 脱敏 · 审计
│   └── web/                    # Next.js 工作台
├── packages/
│   ├── contracts/              # 唯一契约源：JSON Schema → TS + pydantic
│   │   ├── schemas/*.schema.json
│   │   └── generated/
│   ├── gates/                  # gate 1-5 纯函数实现（TS，可单测）
│   └── lint/                   # 15 条反 AI 味规则（移植改写）
├── knowledge/                  # 可运营的专家知识，不含代码
│   ├── design-systems/<slug>/{manifest.json,DESIGN.md,tokens.css}
│   ├── craft/                  # 移植 open-design 六个文件
│   ├── skills/<slug>/SKILL.md  # A/B/C/D 四类
│   ├── dashboard-templates/<slug>/  # 脚手架，非牢笼
│   └── roles/<slug>.yml        # 岗位画像
├── projects/<project-id>/      # 每项目工作区（运行时生成，不入库）
│   ├── metrics.yml
│   ├── memory/project.jsonl
│   └── runs/<run-id>/{plan.json,queryset.json,factset.json,artifact.html,review/*}
├── evals/                      # 评测集与打分脚本
├── e2e/
└── docs/
```

**`knowledge/` 与 `projects/` 的影子覆盖规则**（照学 open-design）：加载 skill/template/design-system 时，先查 `projects/<id>/knowledge/<同路径>`，命中则用项目版本；否则用仓库内置版本。**每次请求重新扫描，不缓存、不重启**——这是让业务专家能自己改规则的前提。

---

## 3. 核心数据契约

**这一章是整个项目的地基。**`packages/contracts/schemas/` 是唯一契约源，TS 类型与 pydantic 模型都由它生成，禁止手写重复定义：

```bash
pnpm --filter contracts gen   # json-schema-to-typescript + datamodel-code-generator
```

CI 检查生成物与 schema 一致（`git diff --exit-code`），防止两侧漂移。

### 3.1 Dataset 与 Profile `[P0]`

```json
{
  "dataset_id": "ds_a01_prod",
  "name": "A01线生产记录",
  "source": { "kind": "xlsx", "uri": "projects/p1/raw/prod.xlsx", "sheet": "2026W31" },
  "row_count": 10080,
  "columns": [
    {
      "name": "shift_yield",
      "dtype": "float64",
      "semantic": "ratio",
      "null_rate": 0.012,
      "distinct_count": 843,
      "min": 0.71, "max": 0.996, "p50": 0.934,
      "sample_values": ["0.934", "0.951"],
      "quality_flags": ["out_of_domain:3"]
    }
  ],
  "quality_score": 0.86,
  "defects": [
    { "type": "unit_inconsistent", "column": "oee", "severity": "high",
      "evidence": { "rows": [12, 87], "note": "同列混用 0-1 与 0-100" },
      "impact": "OEE 相关全部结论", "fix_cost": "low" }
  ],
  "profiled_at": "2026-08-04T11:20:00+08:00"
}
```

`semantic` 取值：`nominal | ordinal | quantitative | ratio | temporal | identifier | geo`。它是图表选型规则与 flint IR 的输入。

**六类缺陷（`defects[].type`）**：`missing_value` / `unit_inconsistent` / `duplicate_key` / `out_of_domain` / `temporal_gap` / `referential_broken`。D 类 skill 负责判定规则，此处只定义结构。

### 3.2 metrics.yml 语义层 `[P0]`

抄 dbt MetricFlow 的 schema 约定，自写 loader（不引 dbt 依赖）。**这是口径唯一事实源，查询节点只能引用这里定义的东西。**

```yaml
version: 3                      # 每次修改递增，被 definition_ref 引用
dimensions:
  - name: line
    type: categorical
    column: line_code
    values: [A01, A02, B01]
  - name: week
    type: time
    column: prod_date
    grain: week

metrics:
  - name: oee
    label: 设备综合效率
    type: ratio                 # simple | ratio | cumulative | derived
    type_params:
      numerator:   { expr: "sum(good_qty * ideal_cycle_time)" }
      denominator: { expr: "sum(planned_time)" }
    unit: "%"
    display: { format: "0.0%", precision: 1 }
    domain: { min: 0, max: 1 }
    filter: "status != 'test'"
    owner: 制造部
    definition_note: "含计划停机；与财务口径差异见 disputes"
    sensitivity: internal       # public | internal | confidential
    disputes:
      - with: finance
        note: "财务口径分母不含换型时间"
        resolved_by: "以制造部口径为准，看板注脚说明"

  - name: yield_first_pass
    label: 一次通过率
    type: ratio
    type_params:
      numerator:   { expr: "sum(case when rework=0 and scrap=0 then qty else 0 end)" }
      denominator: { expr: "sum(qty)" }
    unit: "%"
    display: { format: "0.00%", precision: 2 }
    sensitivity: internal
```

**`sensitivity` 与岗位画像联合决定字段可见性**，是 gate 3 的判定依据之一。`disputes` 段是"口径争议"的结构化落点，事实评审节点会读它——这解决了架构文档 3.4 提到的"记得财务口径和生产口径一直有争议"。

### 3.3 岗位画像 `[P0]`

```yaml
# knowledge/roles/plant_manager.yml
role_id: plant_manager
label: 厂长
decision_horizon: shift          # shift | week | month | quarter
questions_priority:
  - "今天哪条线拖了产出，卡在哪个工序"
  - "有没有需要我现在就介入的异常"
metrics_focus: [oee, yield_first_pass, downtime_top_reason, output_vs_target]
forbidden_fields: [unit_cost, gross_margin, supplier_price]   # gate 3 硬约束
max_sensitivity: internal
narrative:
  style: 结论先行，一屏可读完
  max_conclusions: 5
  require_action: true           # 每条结论必须带行动建议
layout_hint:
  density: high
  primary_viewport: [1440, 900]
  also_check: [390, 844]         # 手机端也要过呈现评审
```

三个默认岗位：`executive`（经营层）/ `plant_manager`（厂长）/ `supply_chain_lead`（供应链负责人）。

### 3.4 AnalysisPlan `[P0]`

洞察节点的输出。**只描述"该看什么"，不含任何 SQL、不含任何数值。**

```json
{
  "plan_id": "pl_01J...",
  "run_id": "run_01J...",
  "role_id": "plant_manager",
  "questions": [
    {
      "qid": "q1",
      "text": "本周哪条产线 OEE 低于目标且恶化",
      "why_it_matters": "决定今晚是否调整排产",
      "metrics": ["oee"],
      "dims": ["line", "week"],
      "baselines": [
        { "kind": "target", "ref": "oee_target" },
        { "kind": "period_over_period", "offset": "-1week" }
      ],
      "depth": "drilldown",
      "drilldown_hint": { "method": "loss_tree", "skill": "oee-loss-tree" },
      "expected_shape": "ranked_comparison"
    }
  ],
  "skills_used": ["oee-loss-tree", "pareto-locate"],
  "memory_refs": ["mem_0x12"],
  "open_risks": ["A02 上周有 3 天数据缺失，结论需标注样本不足"]
}
```

`depth`：`snapshot | trend | comparison | drilldown | correlation`。
`expected_shape`：`single_kpi | trend | ranked_comparison | composition | distribution | correlation | flow`——它是 B 类图表选型 skill 的输入键。

### 3.5 QuerySet `[P0]`

查询节点的输出。**每条查询必须声明它引用了哪些指标与维度，声明与 SQL 实际内容不一致时 gate 3 硬阻断。**

```json
{
  "queryset_id": "qs_01J...",
  "plan_id": "pl_01J...",
  "metrics_version": 3,
  "queries": [
    {
      "query_id": "qy1",
      "qid": "q1",
      "purpose": "各产线本周与上周 OEE",
      "references": { "metrics": ["oee"], "dimensions": ["line", "week"] },
      "sql": "SELECT line_code AS line, date_trunc('week', prod_date) AS week, SUM(good_qty*ideal_cycle_time)/SUM(planned_time) AS oee FROM {{ds_a01_prod}} WHERE status != 'test' GROUP BY 1,2",
      "datasets": ["ds_a01_prod"],
      "emits_facts": [
        { "id_template": "oee.{line}.{week}", "value_column": "oee", "metric": "oee" }
      ],
      "assertions": ["row_count_gt:0", "no_null:oee", "in_domain:oee"]
    }
  ]
}
```

**`{{dataset_id}}` 占位符**由 runner 替换为实际表引用——模型不接触真实连接串、库名、文件路径。这是"生产环境模型只见 schema"的实现细节之一。

**`emits_facts.id_template`** 决定事实 id 的生成规则，模板变量必须来自 `SELECT` 的输出列。这让事实 id 可预测，制作节点才能在拿到 FactSet 索引后正确引用。

### 3.6 FactSet `[P0]`

runner 输出，**纯确定性，无模型参与**。这是 L4–L7 全部环节的唯一数值来源。

```json
{
  "factset_id": "fs_01J...",
  "queryset_id": "qs_01J...",
  "metrics_version": 3,
  "computed_at": "2026-08-04T11:20:00+08:00",
  "role_id": "plant_manager",
  "facts": [
    {
      "id": "oee.a01.2026-W31",
      "value": 0.723,
      "unit": "%",
      "display": "72.3%",
      "metric": "oee",
      "dims": { "line": "A01", "week": "2026-W31" },
      "definition_ref": "metrics.yml#oee@v3",
      "sql_hash": "a3f1c9e2",
      "row_count": 10080,
      "confidence": 0.92,
      "flags": []
    },
    {
      "id": "oee.a02.2026-W31",
      "value": 0.681, "unit": "%", "display": "68.1%",
      "metric": "oee", "dims": { "line": "A02", "week": "2026-W31" },
      "definition_ref": "metrics.yml#oee@v3", "sql_hash": "a3f1c9e2",
      "row_count": 4032,
      "confidence": 0.58,
      "flags": ["low_sample", "temporal_gap:3d"]
    }
  ],
  "series": [
    {
      "id": "oee.a01.trend.13w",
      "metric": "oee",
      "dims": { "line": "A01" },
      "x": { "name": "week", "semantic": "temporal",
             "values": ["2026-W19", "…", "2026-W31"] },
      "y": { "values": [0.71, "…", 0.723], "unit": "%" },
      "definition_ref": "metrics.yml#oee@v3",
      "sql_hash": "a3f1c9e2",
      "flags": []
    }
  ],
  "assertion_results": [
    { "assertion": "in_domain:oee", "passed": true, "checked_rows": 10080 }
  ],
  "provenance": {
    "datasets": [{ "dataset_id": "ds_a01_prod", "quality_score": 0.86, "row_count": 10080 }]
  }
}
```

**设计要点：**

- **`facts` 与 `series` 分开。**标量事实用于 KPI 卡与文案，序列用于图表。两者共用 `definition_ref` 与 `sql_hash`，所以图表和文案的口径天然一致。
- **`display` 由 runner 按 `metrics.yml` 的 `display` 段生成**，不由模型格式化。这消掉了一整类"同一个数在不同卡片精度不同"的事故。
- **`flags` 是评审的输入。**`low_sample`（`row_count` 低于指标声明阈值）、`temporal_gap`、`disputed_definition`、`stale`。事实评审节点看到 `low_sample` 就应要求结论加注脚，gate 5 看到 `low_sample` 仍给强结论则告警。
- **`role_id` 落在 FactSet 上**：runner 在生成阶段就按岗位画像剔除了越权字段，产物层拿不到不该有的数。gate 3 是第二道防线，不是唯一防线。
- **id 命名规范**：`<metric>.<dim值以点连接，小写>.<时间>`，序列加 `.trend.<窗口>`。禁止空格与中文，便于写进 HTML 属性。

#### ChartSpec：图表的数据映射契约 `[P0]`

模型手画图表时**必须**在元素上挂 `data-bf-chart-spec`（见 3.7），内容是这个结构。它不进 FactSet，由模型在制作节点写，gate 2 校验：

```ts
interface ChartSpec {
  kind: 'line' | 'bar' | 'area' | 'scatter';
  marks: 'path' | 'rect' | 'circle';        // 必须与 kind 匹配
  x: { series: string; field: 'period' | 'category' };
  y: {
    series: string;
    field: 'value';
    domain: [number, number];               // zeroBased:false 时必填
    zeroBased: boolean;                     // y 轴是否从 0 起
  };
  order: 'asc' | 'desc' | 'none';           // x 轴排序方向，须与序列实际顺序一致
  orientation?: 'vertical' | 'horizontal';  // bar 专用，默认 vertical
}
```

**为什么这份契约独立存在。**FactSet 回答"数值是多少"，ChartSpec 回答"这些数值被怎样映射到像素"。缺了后者，gate 只能数点数，拦不住"数据在涨、线画成跌"——点数一个不差就能蒙混过关。有了它，gate 才能把 SVG 坐标按 `domain` 反算回数值域做逐点比对（6.2 第 7 条），把图表也纳入"数字可信"的承诺范围。

`domain` 与 `zeroBased` 同时交给 gate 5 判断截断是否夸大差异——同一份声明服务两道 gate，模型只写一次。


### 3.7 产物 HTML 约定 `[P0]`

制作节点自由手写 HTML/SVG/CSS，但必须遵守五条结构约定——**这是"表达自由 + 数值可信"能共存的技术支点**。

**一、数据岛。**产物末尾必须有且仅有一个：

```html
<script type="application/json" id="bf-factset">
{"factset_id":"fs_01J...","facts":[...],"series":[...]}
</script>
```

由 daemon 在制作节点输出后**注入**（模型不写这段，只在 prompt 里拿到事实索引）。注入器同时计算并写入 `<html data-bf-factset-id="fs_01J..." data-bf-run-id="run_01J...">`。

**二、事实绑定。**页面上任何可见数字必须被 `data-fact` 包裹：

```html
<span data-fact="oee.a01.2026-W31">72.3%</span>
<span data-fact="oee.a01.2026-W31" data-fact-transform="delta:oee.a02.2026-W31">+4.2pp</span>
```

图表内的数值走 `data-fact-series`，并且**必须同时挂一份可静态解析的 `data-bf-chart-spec`**：

```html
<svg data-fact-series="oee.a01.trend.13w"
     data-bf-chart-spec='{"kind":"line","x":{"series":"oee.a01.trend.13w","field":"period"},
       "y":{"series":"oee.a01.trend.13w","field":"value","domain":[60,80],"zeroBased":false},
       "marks":"path","order":"asc"}'
     role="img" aria-label="A01 线 OEE 13 周趋势">…</svg>
<div data-bf-chart="echarts" data-fact-series="oee.a01.trend.13w"
     data-bf-chart-spec='{…}'
     data-bf-echarts-option='{"yAxis":{"min":60,"max":80},"series":[{"type":"line"}]}'></div>
```

**为什么必须有 chart-spec `[P0]`：**只比对点数拦不住"画反"。模型完全可以在数据上升时画一条下降的折线——13 个点、序列 13 个值，点数校验全绿。而误导性编码正是我们六道 gate 之一，这个洞不能开在这里。chart-spec 是一份**声明式的数据映射描述**，让 gate 4/5 无需执行页面脚本就能验证：序列引用是否存在、x/y 字段是否在 FactSet 里、坐标域是否截断（`zeroBased:false` 必须有 `domain` 且 gate 会核对截断幅度是否夸大差异）、排序方向是否与实际数据一致、marks 类型与 `kind` 是否匹配。

内联 SVG 还要额外过一道几何一致性检查：抽取 `<path>` 的坐标点，按 chart-spec 声明的 domain 反算回数值，与 `series` 的 `y.values` 逐点比对（容差 2%）。这才是真正能拦住"画反"的那一道——点数只是必要条件。

`data-bf-chart` 是渲染器标记（告诉宿主用 ECharts 挂载），`data-bf-chart-spec` 是数据契约，两者不是一回事，不要混用。

**ECharts 图必须再挂一份 `data-bf-echarts-option` `[P0]`**（值是 option 的 JSON，与 chart-spec 同一种"属性存 JSON"的写法；宿主统一用 `setOption(JSON.parse(el.dataset.bfEchartsOption))` 挂载，产物里不需要每图一段脚本）。

原因是 gate 5 §6.5 要求核对 `option.yAxis.min` 与 chart-spec 声明的下界——**spec 是给 gate 看的声明，option 才是真正渲染出来的东西**。两者若能各写各的，模型完全可以在 spec 里写一个规矩的 `zeroBased:true`，而 option 里照样把 `min` 设成 60：gate 全绿，图照样误导。而 option 若写在内联 `<script>` 里就是任意 JS，静态解析不了，整道误导编码检查对 ECharts 图等于不存在。缺失或不是合法 JSON 即 `E_MISSING_ECHARTS_OPTION`（block）。

确实需要写非事实数字（年份、序号、轴刻度标签）时必须显式豁免，且 gate 会统计豁免数量：

```html
<span data-num="literal" data-num-reason="axis-tick">80%</span>
```

**三、卡片锚点。**每个视觉区块必须有稳定 id，供评审路由与局部重写：

```html
<section data-bf-card="kpi-oee" data-bf-card-title="OEE 概览">…</section>
```

命名规范 `<类型>-<主题>`，同一产物内唯一，重写后必须保持不变（这样第二轮评审能对比同一张卡片）。

**四、自包含。**禁止外部 `<script src>` / `<link href>` / 远程图片；ECharts 等库以内联方式打包；字体用系统字体栈或内联 woff2 的 base64（中文字体体积大，默认走系统栈 + 明确的 fallback 链）。

**五、旗标脚注 `[P0]`。**当某条事实带 `FactFlag`（如 `low_sample`、`stale`）且卡片文案对它下了断言性结论时，卡片内必须有一条**显式声明对应旗标**的脚注：

```html
<p data-bf-footnote="low_sample">本周仅 37 条记录，低于该指标的样本量阈值，差异未必稳定。</p>
```

`data-bf-footnote` 的值是空白分隔的旗标名清单，必须与它要说明的 `FactFlag` 完全一致；元素文本不能为空。**为什么必须显式声明旗标而不是靠扫脚注文本猜**：扫关键词（"样本""偏低"）无法区分"这条脚注在说 low_sample"和"这条脚注在说别的事但恰好用了相近的词"，也无法覆盖同义表达，写不出可靠的负例测试。显式声明把这条规则钉成一个可精确验证的契约：gate 5 只需比对 `data-bf-footnote` 的值与 `FactFlag` 名称是否一致，不需要理解文案语义。缺该脚注即 `E_LOW_SAMPLE_STRONG_CLAIM`（block，见 §6.5）。

### 3.8 评审意见 `[P0]`

两个评审节点共用结构，`kind` 区分。

```json
{
  "review_id": "rv_01J...",
  "kind": "presentation",            // fact | presentation
  "run_id": "run_01J...",
  "round": 1,
  "verdict": "reject",               // pass | reject
  "scores": [
    { "dim": "readability", "score": 7, "evidence": "第二屏正文 11px，密度过高" },
    { "dim": "chart_fitness", "score": 9, "evidence": "排序条形图匹配 ranked_comparison" },
    { "dim": "hierarchy", "score": 6, "evidence": "次要指标与主 KPI 同字号" },
    { "dim": "role_fit", "score": 8, "evidence": "无越权字段，结论均带行动" },
    { "dim": "craft", "score": 5, "evidence": "kpi-oee 卡片右侧文字溢出容器" }
  ],
  "composite": 7.0,
  "findings": [
    {
      "finding_id": "f1",
      "severity": "must_fix",         // must_fix | should_fix
      "code": "E_OVERFLOW",
      "target": "data-bf-card:kpi-oee",
      "viewport": [390, 844],
      "problem": "数值文本溢出卡片右边界约 12px",
      "fix": "缩短标签或改为两行布局，不要缩小字号",
      "evidence_ref": "shots/run_01J/390x844.png#x=240,y=310,w=160,h=48"
    }
  ]
}
```

**四条硬规则：**

1. `must_fix` **只能**用于四类可客观判定的问题：口径违规、事实绑定失败、误导性编码、岗位越权。审美与措辞一律 `should_fix`。
2. 每条 `finding` **必须**有 `target`，指向 `data-bf-card` 锚点或 `data-fact` id。没有 target 的意见无法路由，视为无效并计入评审质量指标。
3. `composite` 由 **daemon 按契约权重重算**，模型自报只作参考，偏差 > 0.01 记 `composite_mismatch` 警告（学 open-design Design Jury 的这一点）。
4. 评审节点**不产出 HTML**。它没有写产物的能力，只有阻断发布的权力。

评分维度与权重写在 `packages/contracts/schemas/review.schema.json` 里，不写在提示词里：

```json
{
  "presentation": {
    "weights": { "readability": 0.25, "chart_fitness": 0.25, "hierarchy": 0.2, "role_fit": 0.15, "craft": 0.15 },
    "threshold": 8.0, "score_scale": 10, "max_rounds": 2,
    "fallback_policy": "block"
  },
  "fact": {
    "weights": { "coverage": 0.3, "definition_consistency": 0.3, "sample_adequacy": 0.2, "anomaly_judgment": 0.2 },
    "threshold": 8.0, "score_scale": 10, "max_rounds": 2,
    "fallback_policy": "block"
  }
}
```

**注意 `fallback_policy` 我们选 `block` 而不是 open-design 的 `ship_best`**：轮次耗尽仍有 `must_fix` 未清零时，不发布、转人工。理由见架构文档 3.3——评审不能阻断就只是一份没人读的报告。

### 3.9 记忆条目 `[P1]`

```json
{
  "mem_id": "mem_0x12",
  "layer": "project",              // task | project | org
  "kind": "business_exception",    // conclusion | business_exception | definition_dispute | rejected_proposal | preference
  "text": "A02 每月首个周一低 OEE 是计划换型，非异常",
  "scope": { "project_id": "p1", "dims": { "line": "A02" } },
  "created_by": "agent:insight",
  "confirmed_by": "user:zhang",    // org 层必须非空
  "created_at": "2026-07-02T09:00:00+08:00",
  "expires_at": null,
  "evidence_run": "run_01H..."
}
```

**红线的实现方式：**记忆条目**不允许**含 `value` 字段，schema 层面就没有这个键。需要数字就重新查——这条不靠纪律，靠契约（且 gate 2 是第二重保险）。

---

## 4. 模块划分与职责边界

### 4.1 依赖方向

```
web  →  daemon  →  runner
                ↘  执行体（CLI / API）
packages/{contracts,gates,lint}  ←  被 daemon 与 web 依赖
knowledge/  ←  被 daemon 在 prompt 组装时读取（每次重扫）
```

**禁止的依赖：**runner 不得反向调 daemon；`packages/gates` 不得引入网络与文件 IO（保持纯函数以便单测）；`packages/contracts` 不得依赖任何业务包。

### 4.2 daemon 模块职责

| 模块 | 职责 | 明确不做 |
| --- | --- | --- |
| `routes/` | HTTP/SSE 端点，参数校验 | 不写业务逻辑 |
| `agents/<node>.ts` | 单个节点：组装 prompt → 调执行体 → 校验输出契约 → 重试 | 不做跨节点编排 |
| `orchestrator.ts` | 串联六节点与两评审点，管状态机与重跑起点 | 不直接拼 prompt |
| `prompts/assemble.ts` | **注入顺序的唯一实现** | 不含节点特有文本（放 `contracts/`） |
| `runtimes/` | 执行体适配：spawn CLI / 调 API / 流解析 | 不感知业务语义 |
| `gates/` | 调 `packages/gates` 跑 1–5，编排 gate 6 | 不实现规则本身 |
| `screenshot/` | Playwright 多视口截图、字体就绪等待 | 不做评判 |
| `memory/` | 三层记忆读写与注入摘要 | 不存数值（schema 已禁止） |
| `runner-client.ts` | 调 runner，HMAC 签名，超时与重试 | 不解析业务结果 |
| `delivery/feishu/` | 卡片、H5 鉴权、多维表格写回、审批、任务 | 不做编排 |

### 4.3 runner 模块职责

| 模块 | 职责 |
| --- | --- |
| `connectors/` | 建立 DuckDB 视图；xlsx/csv/parquet 直读，MySQL/PG 走 `duckdb` 扩展或分页拉取，飞书多维表格走 SDK |
| `profiling/` | 生成 Profile（3.1），含六类缺陷探测 |
| `semantic/` | 加载 metrics.yml；**SQL 白名单校验器**（4.4）；`{{dataset}}` 占位符替换 |
| `execute/` | 执行 QuerySet → 组装 FactSet；计算 `sql_hash`、`display`、`flags` |
| `assertions/` | pandera schema 生成与执行，结果写入 `assertion_results` |
| `security/` | 按 `role_id` 剔除越权字段；脱敏；写审计日志 |

### 4.4 SQL 白名单校验器（runner 内，gate 3 的核心）`[P0]`

**这是"口径唯一"的执行机制**，没有它语义层只是一份没人遵守的文档。实现要点：

1. 用 `duckdb.sql` 的 `EXPLAIN`/`json_serialize_sql` 拿到解析树，**不用正则**。
2. 抽取所有列引用与表引用，比对 `metrics.yml` 的 `dimensions[].column` 与各 metric `type_params` 里出现的列集合，以及 QuerySet 声明的 `datasets`。
3. **拒绝**：引用未声明数据集；引用未在任何指标/维度定义中出现的列；声明的 `references.metrics` 与 SQL 实际计算的聚合表达式不匹配；出现 `metrics.yml` 之外的自定义聚合逻辑（如模型自己写了一个 `sum(a)/sum(b)` 但没有对应 ratio 指标）。
4. **拒绝**：DDL/DML（`CREATE`/`INSERT`/`UPDATE`/`DELETE`/`ATTACH`/`COPY`）、`read_csv`/`read_parquet` 等文件函数（数据集必须走 connector 注册）、`system()` 类函数。
5. 失败时返回结构化错误，**附上可用指标与维度清单**，供查询节点重试时用：

```json
{
  "code": "E_METRIC_UNDEFINED",
  "message": "SQL 计算了未定义的聚合：sum(rework_qty)/sum(qty)",
  "hint": "如需该指标请先在 metrics.yml 定义，或改用已有指标",
  "available_metrics": ["oee", "yield_first_pass", "downtime_top_reason"],
  "available_dimensions": ["line", "week", "shift", "process_step"]
}
```

这个"带可用清单的错误"设计很关键：它把一次失败变成一次有效的重试输入，而不是让模型盲猜。

---

## 5. Agent 节点实现规范

### 5.1 节点的统一形态

每个节点是一个纯函数式的调用单元，签名统一：

```ts
// apps/daemon/src/agents/types.ts
export interface NodeInput<T> {
  runId: string;
  projectId: string;
  roleId: string;
  payload: T;                    // 上游产物
  memory: MemoryDigest;          // 注入用的记忆摘要
  attempt: number;               // 1-based，重试时递增
  priorFindings?: Finding[];     // 重跑时上游 gate/评审的问题
}

export interface NodeOutput<R> {
  result: R;                     // 已通过 schema 校验
  raw: string;                   // 执行体原始输出，落盘留证
  usage: { inputTokens: number; outputTokens: number; ms: number };
  runtime: string;               // 实际使用的执行体
}

export type Node<T, R> = (input: NodeInput<T>) => Promise<NodeOutput<R>>;
```

**所有节点共享的四条实现纪律：**

1. **输出必须过 schema 校验**（`packages/contracts/generated` 的校验器），不通过则重试，最多 3 次，每次把校验错误作为 `priorFindings` 回灌。
2. **原始输出必须落盘**到 `runs/<run-id>/raw/<node>-<attempt>.txt`，用于调试与答辩回放。
3. **禁止节点间直接调用。**节点只认输入输出，串联由 `orchestrator.ts` 负责。
4. **禁止在节点内读文件系统。**所有知识注入由 `prompts/assemble.ts` 完成，节点拿到的是已组装好的字符串——这样注入顺序只有一个实现，可单测。

### 5.2 Prompt 组装顺序 `[P0]`

照学 open-design 的固定顺序注入（`apps/daemon/src/prompts/assemble.ts` 是唯一实现）：

```
1. 平台身份与全局纪律          bifrost-core.md（含"不许编数字"的总则）
2. 岗位画像                    roles/<role_id>.yml 渲染为文本
3. design system（仅制作节点）  DESIGN.md + tokens.css
4. craft 规则（仅制作/呈现评审） craft/*.md 六个文件
5. 本节点适用的 skill body      按 skill 的 triggers 与 applies_to 筛选
6. 上游产物                    Profile / Plan / QuerySet / FactSet 索引
7. 记忆摘要                    项目记忆 + 组织记忆（不含数值）
8. 输出契约                    contracts/<node>.md + JSON Schema 原文
9. 重试上下文（仅 attempt>1）   priorFindings 结构化列出
```

**为什么顺序固定：**靠后的内容对模型行为影响更强，把"输出契约"放在倒数第二、"重试上下文"放最后，是为了让格式要求与本轮要修的问题压过泛泛的风格指导。这个经验直接取自 open-design 的 `prompts/system.ts`。

**Token 预算控制：**FactSet 可能很大，注入时**只给索引不给全量**：

```
可用事实（共 47 条）：
  oee.{a01|a02|b01}.2026-W31          OEE, %, 已格式化
  oee.{a01|a02|b01}.2026-W30          OEE, %, 已格式化
  yield_first_pass.{a01|a02}.2026-W31 一次通过率, %
序列（共 6 条）：
  oee.{a01|a02}.trend.13w             13 周趋势, temporal→ratio
带 flag 的事实（务必在文案中注明）：
  oee.a02.2026-W31  flags=[low_sample, temporal_gap:3d]
```

模型据此写 `data-fact` 引用，具体数值由注入器在产物生成后填入——**模型全程看不到真实数字**，这是"不许编数字"的结构性保证，而非提示词层面的请求。

### 5.3 六个节点的实现要点

#### 治理 Agent `[P1]`

- 输入 Profile，输出质量评分卡 + 治理提议清单，每条含 `impact` 与 `fix_cost`。
- 注入 D 类 skill（六类缺陷识别规则、假异常与业务例外识别）。
- **必须读项目记忆的 `business_exception` 与 `rejected_proposal`**：已被人驳回的提议不应重复提出，已确认的业务例外不应报为异常。这是记忆分层最直接的价值体现。
- 执行体：CLI（需要翻数据 profile 与规则文件）。

#### 洞察 Agent `[P0]`

- 输入业务诉求 + 岗位画像 + Profile + 记忆，输出 AnalysisPlan。
- 注入 A 类 skill（OEE 损失树、帕累托、SPC、归因框架等）。**这是"顶级数据工程师含量"最高的节点**，skill 质量直接决定洞察深度。
- 硬约束：Plan 中不得出现任何数值；`metrics` 字段只能引用 metrics.yml 已定义指标（否则查询节点必然失败，提前在此校验更省一次调用）。
- 执行体：CLI。

#### 查询 Agent `[P0]`

- 输入 AnalysisPlan + metrics.yml 全文 + 维度字典，输出 QuerySet。
- 注入内容里必须包含 **SQL 方言说明**（DuckDB 语法）与 `{{dataset_id}}` 占位符用法。
- 失败重试时把白名单校验器的结构化错误（含 `available_metrics`）作为 `priorFindings` 回灌。
- 执行体：CLI 或 API 均可；实测 API + JSON schema 强约束更稳（输出是纯结构化）。

#### 事实评审 Agent `[P0]`

- 输入 FactSet（**含 flags**）+ AnalysisPlan + 记忆里的 `definition_dispute`。
- 四个维度：`coverage`（业务问题是否被完整覆盖）、`definition_consistency`（是否把口径冲突的两个数并列）、`sample_adequacy`（`low_sample` 事实是否被恰当处理）、`anomaly_judgment`（异常是真业务异常还是数据问题）。
- **在制作之前跑**：内容错了画得再好也是错的，且改内容比改产物便宜一个数量级。
- 执行体：API（纯判定，需要结构化输出与并行能力）。

#### 制作 Agent `[P0]`

- 输入 FactSet 索引 + AnalysisPlan + design tokens + craft 规则 + 模板库 + 岗位画像，输出完整自包含 HTML。
- **两种模式**（架构文档 3.3）：

```ts
type MakerMode =
  | { kind: 'full' }                                    // 首次出稿，整页手写
  | { kind: 'patch'; targets: string[]; findings: Finding[] };  // 评审回灌，只重写指定卡片
```

`patch` 模式的实现：把现有产物的完整 HTML 与被点名卡片的片段一起给模型，要求**只返回替换后的 `<section data-bf-card="...">` 片段**，由 daemon 用 cheerio 做 DOM 级替换。这样既拿到增量效率，又避免 open-design 那种"每轮整篇重写且要求越写越短"的退化。

- 模板库的定位必须在 prompt 里写清楚：**起手式与质量基线，可整段替换、可只借骨架、可完全不用**。不要写成"必须遵循模板"。
- 执行体：CLI（需要多轮改文件、需要长输出）。

#### 呈现评审 Agent `[P0]`

- 输入多视口截图（图像）+ HTML 源码 + 岗位画像 + craft 规则。
- 五个维度见 3.8。**必须是多模态**——溢出、遮挡、重叠在源码里看不见。
- 输出的每条 finding 必须带 `target` 与 `viewport`；`must_fix` 限四类客观问题。
- 执行体：支持视觉输入的 API。**这里不能用纯文本 CLI**，是全系统唯一对执行体有硬能力要求的节点。

### 5.4 执行体适配层 `[P0]`

照学 open-design 的 runtime 描述文件模式，但**不继承它的流格式耦合问题**（它的 Design Jury 只支持 plain-stream，用 claude-stream-json 会被绕过）。我们的做法是所有执行体统一归一化到同一个事件流：

```ts
// apps/daemon/src/runtimes/defs/example.ts
export const def: RuntimeDef = {
  id: 'claude-cli',
  kind: 'cli',
  command: 'claude',
  args: (ctx) => ['-p', ctx.promptFile, '--output-format', 'stream-json'],
  streamFormat: 'claude-stream-json',       // 由 parsers/ 归一化
  capabilities: { vision: true, longOutput: true, fileEdit: true },
  env: (ctx) => ({ /* 生产环境不注入任何数据库凭据 */ }),
};

// 归一化后的统一事件
type RuntimeEvent =
  | { type: 'text'; delta: string }
  | { type: 'tool'; name: string; status: 'start' | 'end' }
  | { type: 'done'; raw: string }
  | { type: 'error'; code: string; message: string };
```

**选择逻辑：**节点声明所需 capability（如呈现评审要 `vision`），适配层选第一个满足且可用的执行体，都不满足则报错并明确提示缺什么。禁止静默降级——静默降级会导致"评审看起来跑了但其实没看图"。

---

## 6. Gate 实现细节

前五道在 `packages/gates/`，**纯函数、无 IO、可单测**；gate 6 在 daemon（需要 Playwright 与模型调用）。

```ts
// packages/gates/src/types.ts
export interface GateResult {
  gate: 1 | 2 | 3 | 4 | 5 | 6;
  passed: boolean;
  findings: Finding[];       // severity: block | warn
  stats?: Record<string, number>;
  ms: number;
}
```

### 6.1 Gate 1 · 产物结构 `[P0]`

cheerio 解析，检查项与错误码：

| 检查 | 错误码 | 级别 |
| --- | --- | --- |
| 存在外部 `<script src>` / `<link href>` / 远程图片 | `E_EXTERNAL_RESOURCE` | block |
| 数据岛缺失或 JSON 不可解析 | `E_DATA_ISLAND` | block |
| 存在 `<section>` 无 `data-bf-card` | `E_MISSING_ANCHOR` | block |
| `data-bf-card` 值重复 | `E_DUPLICATE_ANCHOR` | block |
| 产物体积 > 2 MB | `E_TOO_LARGE` | block |
| 内联 base64 图片单个 > 300 KB | `W_HEAVY_ASSET` | warn |
| 缺 `<html lang>` / `<title>` | `W_META` | warn |

**注意 `E_MISSING_ANCHOR` 是 block 而非 warn**——open-design 把它放成 P2 提示，结果评审无处可路由（架构文档 2.4）。我们把它提为硬约束。

### 6.2 Gate 2 · 事实绑定 `[P0]`

**全系统最关键的一道 gate。**算法：

1. cheerio 取 `body` 文本，**移除**所有 `[data-fact]`、`[data-fact-series]`、`[data-num="literal"]` 子树。
2. 在剩余文本上跑数字正则：`/-?\d[\d,._]*\s*(%|pp|万|千|亿|元|台|件|小时|分钟|秒)?/g`。
3. 命中即 `E_UNBOUND_NUMBER`，block，并给出上下文片段与所在卡片。
4. 对每个 `data-fact` 值：id 必须存在于数据岛；元素文本必须等于 `display`，或落在**允许的格式化差异白名单**内。
5. 对每个 `data-fact-series`：id 必须存在于 `series`；**必须挂 `data-bf-chart-spec`**，缺失即 `E_MISSING_CHART_SPEC`（block）——没有它后面几道图表校验全部失效。
6. 解析 `data-bf-chart-spec`（`JSON.parse` 失败即 `E_BAD_CHART_SPEC`，block），校验：`x.series` / `y.series` 必须存在于数据岛；`x.field` / `y.field` 必须是该序列的合法字段；`kind` 与 `marks` 必须匹配（`line`→`path`、`bar`→`rect`、`scatter`→`circle`）。
7. **内联 SVG 的几何一致性检查**（真正拦"画反"的一道）：抽取 `marks` 声明的元素坐标，先比对点数与 `y.values` 长度（防止画了 13 个点但序列只有 9 个值），再按 `y.domain` 把像素坐标反算回数值域，与 `y.values` 逐点比对，**相对容差 2%**。任一点超差即 `E_CHART_GEOMETRY_MISMATCH`（block）。
8. 统计 `data-num="literal"` 数量，超过 15 个记 `W_MANY_LITERALS`——豁免太多说明有人在钻空子。

**第 7 条为什么不能省。**只比点数拦不住最危险的一类错误：数据在涨、图画成跌，点数一个不差、gate 全绿。SVG 是模型手画的，坐标就是它自由发挥的地方，这里不设防等于把"数字可信"的承诺留了个后门。反算需要 `y.domain`，这也是 chart-spec 里 `domain` 在 `zeroBased:false` 时**必填**的原因（截断幅度是否夸大差异由 gate 5 判断，此处只做数值还原）。

ECharts 渲染的图表不走几何检查（DOM 由库生成，不是模型手写），但 chart-spec 的字段与域校验照做——模型仍可能声明一个把数据映射错的 spec。

**允许的格式化差异白名单**（否则误报会淹没真问题）：

```ts
const ALLOWED_TRANSFORMS = {
  thousands:  (d: string) => d.replace(/,/g, ''),        // 72,300 ≡ 72300
  unitScale:  ['%↔pp', '元↔万元', '件↔万件'],            // 需 data-fact-transform 声明
  precision:  (a: number, b: number, p: number) => Math.abs(a - b) < 5 * 10 ** -(p + 1),
  sign:       (d: string) => d.replace(/^\+/, ''),        // +4.2 ≡ 4.2
  cjkNumeral: false,                                      // 中文数字不允许，歧义太大
};
```

`data-fact-transform` 声明的派生值（如 `delta:`、`ratio:`）由 gate 在数据岛上**重算验证**，不接受模型自己算的结果。

### 6.3 Gate 3 · 口径与权限 `[P0]`

分两半，一半在 runner（SQL 白名单，见 4.4），一半在此：

| 检查 | 错误码 |
| --- | --- |
| FactSet 中 `definition_ref` 指向的指标版本与当前 metrics.yml 不一致 | `E_STALE_DEFINITION` |
| 产物引用的事实其 `metric` 的 `sensitivity` 超出岗位 `max_sensitivity` | `E_SENSITIVITY` |
| 产物出现岗位 `forbidden_fields` 中的字段名或其中文标签 | `E_FORBIDDEN_FIELD` |
| 同一产物内并列了 `disputes` 中互相冲突的两个指标且无注脚 | `W_DISPUTED_PAIR` |

`E_FORBIDDEN_FIELD` 要同时匹配英文字段名与 metrics.yml 里的 `label`，否则模型写"毛利率"就绕过了对 `gross_margin` 的检查。

### 6.4 Gate 4 · 数据断言 `[P0]`

在 runner 侧于 FactSet 生成时同步执行，结果随 FactSet 返回；daemon 侧只做判定。断言集：

```python
# apps/runner/src/bifrost_runner/assertions/standard.py
STANDARD = {
  "row_count_gt":   lambda df, n: len(df) > n,
  "no_null":        lambda df, col: df[col].notna().all(),
  "in_domain":      lambda df, col, lo, hi: df[col].between(lo, hi).all(),
  "unique_key":     lambda df, cols: not df.duplicated(cols).any(),
  "temporal_dense": lambda df, col, grain: no_gap(df[col], grain),
  "sum_reconcile":  lambda df, part, total, tol=1e-6: abs(df[part].sum() - total) < tol,
}
```

`in_domain` 的 `lo/hi` 取自 metrics.yml 的 `domain`，不在断言里硬编码。任一 block 级断言失败 → 整个 run 停在 L3，不进制作——**用错的数画图是纯浪费**。

### 6.5 Gate 5 · 误导编码 `[P0]`

对内联 SVG 与 ECharts option 双路检查。**这是最需要写好的一道 gate，也是最能体现"数据专业性"的地方。**

| 规则 | 判定 | 级别 |
| --- | --- | --- |
| y 轴截断 | 条形/面积图 `ChartSpec.zeroBased` 为 false | block |
| 双轴 | 同一图两个 y 轴且量纲不同 | block（除非 `data-bf-dual-axis-justified` 显式声明理由） |
| 面积编码放大 | 气泡/圆用半径而非面积映射数值 | block |
| 时间间隔不等 | temporal 轴刻度间距与实际时间差不成比例 | block |
| 饼图类别过多 | 扇区 > 6 | warn |
| 样本不足仍给强结论 | 引用了 `low_sample` 事实的卡片文案含"显著/明显/大幅"等词且无注脚 | block |
| 色彩对比不足 | 前景/背景对比 < 4.5:1（正文）或 3:1（大字） | warn |
| 色盲不安全 | 仅用红绿区分语义 | warn |
| 排序缺失 | `ranked_comparison` 未按值排序 | warn |

**实现方式：**y 轴截断直接读 3.6 的 `ChartSpec`——`zeroBased:false` 且 `kind` 为 `bar`/`area` 即 block；`line` 允许截断，但 gate 会核对**放大倍数**，超过 4 倍记 `W_AXIS_EXAGGERATION`（放大微小差异是最常见的误导手法）：

```
放大倍数 = max(|domain[0]|, |domain[1]|) / (domain[1] - domain[0])
```

读法是"如果这张图从 0 画起，同样的波动会缩小多少倍"。分母是 **domain 跨度**而不是数据自身的极差——读者感知到的放大程度只由 domain 决定：`domain:[0,100]` 配一条在 72.1~72.4 之间的线，看上去就是平的，没有任何夸大。上面 3.7 的示例 `domain:[60,80]` 算出 80/20 = 4.0，恰好不告警，是这个阈值的校准点；`zeroBased:true` 时式子恒等于 1，自动不告警。

（本条原先写的是"`domain` 跨度与数据实际波动幅度的比值"，与它自己声明要拦的"放大微小差异"方向相反：domain 跨度大于数据波动幅度是把线**压平**。已按上式更正，来龙去脉见 findings.md。）

ECharts 产物额外读 `option.yAxis.min` 与 spec 交叉验证，两者不符即 `E_BAD_CHART_SPEC`；option 必须挂在 `data-bf-echarts-option` 属性上（见 3.7），缺失即 `E_MISSING_ECHARTS_OPTION`。

**这里原本要求模型另写一个 `data-bf-axis` 声明，已撤销**——它和 ChartSpec 的 `y.domain` / `zeroBased` 是同一件事，让模型写两遍只会增加不一致的机会。**模型只声明一次数据映射，两道 gate 共用**，这也是 ChartSpec 值得作为独立契约的原因之一。

对比度检查用 `tokens.css` 解析出的实际颜色值，不靠猜。

### 6.6 Gate 6 · 呈现评审 `[P1]`

流程：

```
产物落盘 → Playwright 起本地静态服务 → 多视口截图（岗位 layout_hint 指定）
  → 等待字体就绪（document.fonts.ready + 200ms 稳定期）
  → 截图落 runs/<run-id>/shots/<w>x<h>.png
  → 调呈现评审节点（图 + 源码）
  → composite 服务端重算 → 判定
  → must_fix 非空 → 制作节点 patch 模式重跑（最多 2 轮）
  → 轮次耗尽仍有 must_fix → 不发布，转人工（fallback_policy: block）
```

**中文字体一致性**必须显式处理：容器内装 `Noto Sans CJK SC`，并在截图前断言 `document.fonts.check('12px "Noto Sans CJK SC"')`，否则不同环境截图差异会让评审结论不可复现。

### 6.7 反 AI 味 lint `[P1]`

`packages/lint/` 移植改写 open-design 的十五条规则（架构文档 2.4 末段），**实现改为 cheerio DOM 级**而非 grep：

```ts
export const RULES = [
  'purple-gradient', 'trust-gradient', 'ai-default-indigo', 'emoji-in-heading',
  'left-accent-card', 'sans-display-face', 'invented-marketing-number',
  'filler-copy', 'all-caps-no-tracking', 'external-placeholder-image',
  'raw-hex-outside-root', 'accent-overuse', 'scroll-into-view',
  'heading-skip-level', 'icon-only-button-no-label',
] as const;
```

全部 `warn` 级别，进 Verify 面板不阻断。**分工要写在代码注释里讲清楚：移植来的规则管"好不好看"，六道 gate 管"对不对"。**

`ai-default-indigo` 等颜色规则必须先 `stripTokenBlocks()` 排除 `:root` 里的合法 token 声明，否则设计系统自己定义主色就会误报（这个坑 open-design 已经踩过并解决，直接照搬它的处理）。

---

## 7. 服务端 API

### 7.1 REST 端点

```
# 项目与数据
POST   /api/projects                        创建项目
POST   /api/projects/:id/datasets           注册数据集（上传或连接串）
GET    /api/projects/:id/datasets/:dsid/profile
GET    /api/projects/:id/metrics             读 metrics.yml
PUT    /api/projects/:id/metrics             改 metrics.yml（version 自动递增）
POST   /api/projects/:id/metrics/validate    只校验不保存

# 运行
POST   /api/projects/:id/runs                发起 run（body: brief, role_ids[]）
GET    /api/runs/:runId                      run 状态与各阶段产物索引
GET    /api/runs/:runId/events               SSE 事件流
POST   /api/runs/:runId/rerun                从指定阶段重跑（body: from）
POST   /api/runs/:runId/cancel

# 产物
GET    /api/runs/:runId/artifact              HTML
GET    /api/runs/:runId/artifact/preview      沙箱 iframe 用（CSP 收紧）
GET    /api/runs/:runId/factset
GET    /api/runs/:runId/gates                 六道 gate 结果
GET    /api/runs/:runId/reviews               两个评审点意见
GET    /api/runs/:runId/provenance/:factId    溯源检查器数据
POST   /api/runs/:runId/params                参数面板调参（不重跑模型）
POST   /api/runs/:runId/publish               发布（gate 未过则 409）

# 知识与记忆
GET    /api/knowledge/skills                  含影子覆盖来源标注
GET    /api/knowledge/design-systems
GET    /api/projects/:id/memory
PUT    /api/projects/:id/memory/:memId
DELETE /api/projects/:id/memory/:memId
POST   /api/projects/:id/memory/:memId/promote  项目记忆升组织记忆（需人确认）

# 交付
POST   /api/runs/:runId/deliver/feishu
POST   /api/runs/:runId/export                body: { format: html|pdf|pptx }
```

### 7.2 SSE 事件 `[P0]`

工作台的生成过程时间线（架构文档第六章）靠这条流驱动。事件类型：

```ts
type RunEvent =
  | { t: 'stage'; stage: Stage; status: 'start'|'done'|'fail'; ms?: number }
  | { t: 'node'; node: NodeId; attempt: number; status: 'start'|'done'|'retry'|'fail' }
  | { t: 'token'; node: NodeId; delta: string }         // 制作节点的流式输出
  | { t: 'artifact'; produced: 'plan'|'queryset'|'factset'|'html'; ref: string }
  | { t: 'gate'; gate: number; passed: boolean; blockCount: number; warnCount: number }
  | { t: 'review'; kind: 'fact'|'presentation'; round: number; verdict: string; composite: number }
  | { t: 'patch'; targets: string[] }                    // 局部重写了哪些卡片
  | { t: 'memory'; action: 'read'|'write'; memId: string }
  | { t: 'done'; runId: string; publishable: boolean };

type Stage = 'profile'|'plan'|'query'|'fact'|'fact_review'|'make'|'verify'|'deliver';
```

**每个事件都要能在 UI 上展开看中间产物**——这既是调试工具，也是答辩时最有说服力的部分（能看到系统拦下自己的错误）。

### 7.3 Runner 内部 API

只监听 `127.0.0.1`，请求带 HMAC 签名（共享密钥来自环境变量，daemon 与 runner 各自读取）：

```
POST /internal/profile      { dataset }                → Profile
POST /internal/validate-sql { queryset, metrics_yml }   → { ok, errors[] }
POST /internal/execute      { queryset, role_id }       → FactSet
POST /internal/preview      { sql, limit }              → 分页结果（仅开发/预生产环境启用）
```

`/internal/preview` **在生产环境必须关闭**（通过 `BIFROST_ENV` 判定），否则它会成为绕过岗位过滤看明细数据的后门。

---

## 8. 持久化 schema

SQLite（better-sqlite3），迁移文件放 `apps/daemon/src/db/migrations/NNN_*.sql`，只增不改。

```sql
CREATE TABLE projects (
  id TEXT PRIMARY KEY, name TEXT NOT NULL,
  env TEXT NOT NULL DEFAULT 'dev',          -- dev | staging | prod
  created_at TEXT NOT NULL
);

CREATE TABLE datasets (
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
  name TEXT NOT NULL, source_json TEXT NOT NULL,
  profile_json TEXT,                         -- Profile 快照
  quality_score REAL, row_count INTEGER,
  created_at TEXT NOT NULL
);

CREATE TABLE runs (
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
  role_id TEXT NOT NULL, brief TEXT NOT NULL,
  stage TEXT NOT NULL, status TEXT NOT NULL,  -- running | blocked | done | failed | cancelled
  metrics_version INTEGER NOT NULL,
  publishable INTEGER NOT NULL DEFAULT 0,
  started_at TEXT NOT NULL, ended_at TEXT
);

CREATE TABLE run_artifacts (               -- 五个中间产物的索引
  run_id TEXT NOT NULL REFERENCES runs(id),
  kind TEXT NOT NULL,                      -- plan | queryset | factset | html | shots
  path TEXT NOT NULL, input_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (run_id, kind)
);

CREATE TABLE node_calls (                  -- 每次模型调用，成本与性能分析用
  id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
  node TEXT NOT NULL, attempt INTEGER NOT NULL,
  runtime TEXT NOT NULL, mode TEXT,        -- maker: full | patch
  input_tokens INTEGER, output_tokens INTEGER, ms INTEGER,
  status TEXT NOT NULL, raw_path TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE gate_results (
  run_id TEXT NOT NULL REFERENCES runs(id), round INTEGER NOT NULL,
  gate INTEGER NOT NULL, passed INTEGER NOT NULL,
  findings_json TEXT NOT NULL, ms INTEGER,
  PRIMARY KEY (run_id, round, gate)
);

CREATE TABLE reviews (
  id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
  kind TEXT NOT NULL, round INTEGER NOT NULL,
  verdict TEXT NOT NULL,
  composite_reported REAL, composite_recomputed REAL,   -- 两者都存，便于查 mismatch
  scores_json TEXT NOT NULL, findings_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE memories (
  id TEXT PRIMARY KEY, project_id TEXT REFERENCES projects(id),
  layer TEXT NOT NULL, kind TEXT NOT NULL, text TEXT NOT NULL,
  scope_json TEXT, created_by TEXT NOT NULL, confirmed_by TEXT,
  evidence_run TEXT, created_at TEXT NOT NULL, expires_at TEXT
  -- 注意：没有 value 列。记忆不存数值，见 3.9
);

CREATE TABLE audit_log (                   -- 生产环境合规必需
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at TEXT NOT NULL, actor TEXT NOT NULL,   -- user:<id> | agent:<node> | system
  action TEXT NOT NULL, target TEXT,
  role_id TEXT, sql_hash TEXT, row_count INTEGER,
  detail_json TEXT
);
```

**`memories` 表没有 `value` 列是刻意的**——记忆红线在 schema 层面就被固化，不靠开发者自觉。

**`reviews` 同时存 `composite_reported` 与 `composite_recomputed`**，因为二者偏差是评审质量的直接信号（学 open-design 的 `composite_mismatch`）。

---

## 9. 前端工作台：整体照搬 open-design 外壳

### 9.1 原则：不重新设计 UI

**工作台的布局、交互、切换、流式输出、设置弹出方式全部照搬 open-design，不自己设计。**理由很直接：这些是它迭代了几十个版本磨出来的东西，我们在这上面自创只会更差，而且这不是 Bifrost 的差异化所在。我们的差异化在数据可信度，不在窗口怎么摆。

本章记录的是 **2026-08-04 对 `apps/web` 的源码级核实结果**（版本 0.16.1，sparse-checkout `apps/web`，535 个 ts/tsx 文件、23 MB），可以直接照着写。凡本章与架构文档第六章的描述冲突，以本章为准——架构文档那段是从架构层面推的，有三处不符实情，见 9.2 末尾。

### 9.2 真实布局：不是三栏，是「标签条 + 可折叠对话分栏」

**外层 `.workspace-shell`**（`styles/shell.css:19`）是两行栅格，没有第三栏：

```css
.workspace-shell {
  --workspace-tabs-chrome-height: 44px;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  grid-template-rows: 44px minmax(0, 1fr);   /* 标签条 + 主体 */
  height: 100vh; overflow: hidden;
}
.workspace-shell__body > .app { height: 100%; min-height: 0; }
.app {                                       /* 主体内的项目视图 */
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  grid-template-rows: auto 1fr;
  height: 100vh; overflow: hidden;
}
.app > .split { grid-row: 2; }
```

**独立的顶栏被删掉了**（`.app` 上方 `shell.css:1-9` 的注释写明）：原来的 chrome header 行内容被拆进了对话栏（项目标题、设计系统选择器）与 Design Files 标签行（设置 / 交付 / 演示 / 分享 / 头像）。`auto 1fr` 的第一行如今是零高的预留行，`.split` 保留显式 `grid-row: 2` 只为布局兼容。这是个值得学的决定——少一行常驻 chrome，看板预览区就多一行高度。

**内层 `.split`**（`shell.css:2269`）才是分栏，而且是**三轨但只有两块可见内容**：

```css
.split {
  --project-chat-panel-width: 460px;
  --project-chat-handle-width: 8px;
  --project-workspace-panel-track: minmax(400px, 1fr);
  display: grid;
  grid-template-columns:
    var(--project-chat-panel-width)      /* 1 对话栏 */
    var(--project-chat-handle-width)     /* 2 拖拽手柄 */
    var(--project-workspace-panel-track);/* 3 工作区 */
  transition:
    --project-chat-panel-width 200ms cubic-bezier(0.23, 1, 0.32, 1),
    --project-chat-handle-width 200ms cubic-bezier(0.23, 1, 0.32, 1);
}
.split.split-focus {          /* 专注模式：折叠对话栏 */
  --project-chat-panel-width: 0px;
  --project-chat-handle-width: 0px;
  --project-workspace-panel-track: minmax(0, 1fr);
  transition: … 140ms cubic-bezier(0.23, 1, 0.32, 1);
}
```

三个细节都要抄：

**一、宽度用 `@property` 注册成可动画的 `<length>`**（`shell.css:2255-2268`，`initial-value: 460px` / `8px`）。CSS 变量默认不可过渡，注册后才能逐帧插值。

**二、折叠永不降级为单列。**注释写得很清楚：前两轨过渡到 `0`，而不是改 `grid-template-columns` 的轨数——因为工作区那一轨是普通 `1fr`/`minmax` 份额（未注册长度），只有保持轨数不变才能逐帧平滑地把释放出来的空间收回去。**展开 200ms、折叠 140ms**，两个方向不同速，收起比展开快。

**三、拖拽期间挂 `.is-resizing-chat`**（`shell.css:2297`）：`transition: none`（否则面板跟不上光标）、`cursor: col-resize`、`user-select: none`、`iframe { pointer-events: none }`，并给 `.workspace` / `.viewer` 加 `contain: layout paint` 限制重排范围。对我们尤其重要——我们的工作区里就是个 iframe 装看板。

**对话栏宽度的持久化**（`components/ProjectView.tsx:649-768`）：

| 常量 | 值 |
| --- | --- |
| `CHAT_PANEL_WIDTH_STORAGE_KEY` | `open-design.project.chatPanelWidth` |
| `DEFAULT_CHAT_PANEL_WIDTH` | 460 |
| `MIN_CHAT_PANEL_WIDTH` | 345 |
| `MAX_CHAT_PANEL_WIDTH` | 720 |
| 工作区最小宽 | 400（`MIN_WORKSPACE_PANEL_WIDTH`） |

上限还要按视口再夹一次（`clampChatPanelWidth(width, maxWidth)`），保证 `对话栏 + 8 + 工作区最小宽` 不超视口。还有一条容易漏的降级：视口窄于 `MIN_CHAT_PANEL_WIDTH + 8 + 400` 时，`workspacePanelMinWidthForSplit()` 把工作区最小宽直接降到 `0`（`ProjectView.tsx:753`）——小窗口下宁可挤扁工作区也不让对话栏破下限。拖拽时 `applySplitChatPanelWidth()` 每帧直接写 CSS 变量到 DOM，不走 React state——这是它能拖得不卡的原因，照抄。

**架构文档第六章的三处纠错：**① 不是"左中右三栏"，是"对话栏 + 工作区"两块，我原先说的左栏（数据源树/技能库/历史）在 open-design 里其实是**标签页与弹层**，不是常驻栏；② 时间线不是独立区域，是**对话栏内的消息流**；③ 右栏检查器也不是常驻栏，是按需唤出的面板。

### 9.3 标签体系与扩展点

工作区顶部是标签条（`WorkspaceTabsBar.tsx`，1788 行），标签 id 用**前缀约定**而非枚举类型（`FileWorkspace.tsx:433-439`）：

| 标签 id 形态 | 含义 |
| --- | --- |
| `__design_files__` | 文件面板（`DESIGN_FILES_TAB`，常驻首位） |
| `__design_system__` | 设计系统面板（`DESIGN_SYSTEM_TAB`） |
| `__browser__:<n>` | 内嵌浏览器（`BROWSER_TAB_PREFIX` + 自增序号） |
| `chat:<id>` | 侧边对话（`workspace/SideChatTab.tsx`） |
| `terminal:<id>` | 终端（`workspace/TerminalViewer.tsx`） |

**`+` 号启动器是新建标签的唯一入口**，注册表在 `workspace/tab-launcher.ts`，源码注释直接给出了扩展成本：

> Adding a tab kind is therefore a two-line change: register an action below, and add a render branch in the `.ws-body` switch of `FileWorkspace.tsx`.

`LauncherAction` 结构 = `{ id, iconName, labelKey, descriptionKey?, run(ctx) }`，`LauncherContext` 提供 `projectId` / `openTab(tabId)` 与各类 `createXxx()`。职责分离写得很干净：`tab-launcher.ts` 只管**能创建什么**，`TabLauncherMenu.tsx` 只管**怎么渲染下拉**，`FileWorkspace.tsx` 只管**提供上下文与渲染分支**。

**两个功能开关是产品决策的落点**，值得学这种写法：`ENABLE_TERMINAL_WORKSPACE_ENTRYPOINT = false`、`ENABLE_BLANK_PAGE_WORKSPACE_ENTRYPOINT = false`。后者注释写了原因（2026-07-27 产品决定：页面应当来自对话/生成流程，手工建空白页是死路）并说明"翻回 true 即可恢复，PageCreatorDialog 接线保持完整"，连测试都 `skipIf` 同一个开关。

**Bifrost 落地**：`__datasets__`（数据源树）、`__provenance__`（溯源）、`__verify__`（验证）、`__memory__`（记忆）四个标签走同一套注册表；看板预览沿用 `__design_files__` 那条通路。都是两行改动。

### 9.4 iframe 保活池（必抄，血泪教训）

`FileWorkspace.tsx:439-449` 两个上限常量与注释，是我们最容易踩坑的地方：

```ts
const BROWSER_KEEPALIVE_CAP = 3;      // 每个 <webview> 是独立 Chromium 进程
const HTML_VIEWER_KEEPALIVE_CAP = 3;  // 已打开的 HTML 预览保活 LRU
```

浏览器标签的理由是内存/CPU 随标签数线性增长，所以只保活最近激活的 3 个，切回被淘汰的标签就重挂（重载）。HTML 预览的理由更隐蔽：

> Moving an iframe between a visible host and the global parking pool makes Chromium navigate it again even when `src` is byte-identical, so tab A → tab B → tab A used to refetch both artifacts and briefly return to a blank/loading preview.

实现是 `.iframe-keep-alive-pool { display: none }` + `.pooled-iframe-host { display: contents }`（`shell.css:50-57`）。**对 Bifrost 直接命中**：我们的看板产物是单文件自包含 HTML，可能几百 KB 带内联 ECharts，来回切标签重载会明显闪白。照抄这套 LRU 与 `display: contents` 寄主。

### 9.5 对话与流式输出

`ChatPane.tsx`（4951 行）+ `AssistantMessage.tsx`（4144 行）。SSE 解析在 `providers/sse.ts`，`parseSseFrame()` 处理 `event:` / `data:` / `id:` / `:comment` 四类行，多行 `data` 用 `\n` 拼接后 `JSON.parse`，解析失败返回 `null` 而不抛——照抄这个签名：

```ts
export type ParsedSseFrame =
  | { kind: 'event'; event: string; data: Record<string, unknown>; id?: string }
  | { kind: 'comment'; comment: string }
  | { kind: 'empty' };
```

**四个流式渲染的处理值得整体照搬：**

**一、工具输入的增量流。**`ChatPane.tsx:588` 维护"live-only streaming tool-input partials keyed by tool-use id"，用来在完整 `tool_use` 事件到达前就实时显示正在写的内容。`AssistantMessage` 的 memo 比较**故意排除** streaming 字段（`:470-473`），只把 partial 传给正在流的那一行，否则 memo 会吞掉 `tool_input_delta`、卡片只在最终事件才更新。

**二、消息分组。**`AssistantMessage.tsx:494-497`：thinking 块可折叠；**连续同名工具调用合并成一张分组卡片**，而不是刷一屏同样的行。我们的六节点流水线更需要这个——一次运行会有大量 gate 检查事件。

**三、尾部占位与滚动锚定。**`ChatPane.tsx:1730-1748`：流式回复需要生长空间，所以插一个 tail spacer 占位；一轮结束就无条件收掉。滚动跟随由每条消息子元素上的 `ResizeObserver` 驱动（`:2034`），不是轮询。

**四、流式期间不做 DOM 依赖的解析。**`:1806-1809` 遇到内容里有 form 标签但 DOM 元素还没就绪时，`if (streaming) return` 直接跳过。

**Bifrost 的事件流照此渲染**：plan / query / fact / make / verify 五阶段事件复用同一套分组卡片，gate 结果就是"连续同名工具"的天然分组场景。

### 9.6 设置的弹出方式

**单一 `SettingsDialog`（9116 行）+ 一个 section 联合类型**，不是多个独立设置窗口。`SettingsDialog.tsx:215` 的 `SettingsSection` 有 22 个 token：`general` / `execution` / `workspace` / `instructions` / `media` / `composio` / `orbit` / `routines` / `integrations` / `mcpClient` / `language` / `appearance` / `critiqueTheater` / `notifications` / `pet` / `designSystems` / `projectLocations` / `memory` / `privacy` / `library` / `about`。

**两个设计值得学：**

**一、别名折叠表。**部分 token（`language` / `appearance` / `notifications` / `pet` / `projectLocations`）的内容被并进了别的 section，于是有一张映射表把请求的 token 归到"真正拥有导航项的那个 section"。这样调用方不必知道 UI 怎么分组，`openSettings('appearance')` 永远能落到正确位置。

**二、`openSettings(section)` 是唯一入口。**`App.tsx:4637` 顶层只挂一个 `<SettingsDialog>`，全应用任何地方要打开设置都调这一个函数并带上 section。连不属于对话框的 `library`（由 EntryShell 路由承载）也复用这个入口——源码注释还自我批评了这点并留了 reconcile follow-up，说明他们清楚这是个妥协。

**Bifrost 需要的 section**：`general` / `execution`（执行体配置）/ `workspace` / `instructions` / `integrations`（飞书）/ `language` / `appearance` / `memory` / `privacy` / `about`，另加数据场景专有的 `dataSources`（连接器与凭据）/ `metrics`（口径与语义层）/ `roles`（岗位画像）/ `review`（两个评审点的权重阈值，对应它的 `critiqueTheater`）。**它已经有 `memory` 与 `critiqueTheater` 两个 section**，我们的记忆管理与评审配置直接落在对应位置，不新造导航。

### 9.7 我们唯一新增的东西

除下面三个组件外，工作台不做任何自创设计。而且核实后发现，它们在 open-design 的结构里都有现成的挂载位置：

**溯源检查器。**预览 iframe 注入轻量脚本，捕获 `[data-fact]` 点击 → `postMessage` 给宿主 → 宿主调 `/provenance/:factId` → 弹出面板：事实 id、数据集、过滤与聚合路径、`definition_ref`、`sql_hash`、`row_count`、数据集 `quality_score`、`flags`。**照 `ManualEditPanel` 的唤出方式**（选中元素后出面板），不新造交互。这是整个产品最强的说服力来源，答辩应作为核心演示动作。

**Verify 面板。**六道 gate 红黄绿 + 被拦截并修正过的记录 + 两评审点的 must_fix / should_fix。挂在 `__verify__` 标签。要显式展示"系统拦下过自己的错误"，这比声称从不出错可信得多。

**记忆面板。**项目记忆条目可编辑、可删除、可升级为组织记忆（二次确认）。open-design 已有 `MemoryHooksPanel` / `MemoryProfilePanel` 与 settings 的 `memory` section，**改写它们的内容即可，布局与唤出方式不动**。

### 9.8 沙箱与 CSP `[P0]`

预览 iframe 必须 `sandbox="allow-scripts"`（**不给 `allow-same-origin`**，两者同给等于没有沙箱）。产物自包含，所以 CSP 可以收得很紧：

```
default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline';
img-src data:; font-src data:; connect-src 'none'; frame-ancestors 'self'
```

`connect-src 'none'` 很关键：产物即使被注入恶意代码也无法外传数据。注意这条与 9.4 的保活池叠加时，iframe 复用不改变 CSP 归属，安全性不打折。

### 9.9 参数面板：区分筛选性与结构性 `[P0]`

调参分两类，**处置完全不同**。这是个容易写错的地方——早期版本这里写的是"一律不重跑模型"，那是错的，见下。

**筛选性参数：即时刷新，不动模型。**条件是**不改变事实形状**——事实与序列的 id 集合不变、序列长度不变，只是数值变了。典型是切换时间范围内的具体周次、切换产线（同构维度值）、切换对比基准。

```ts
// 前端：调 /params → 拿新 factset → postMessage 给 iframe
//      → 脚本重写所有 [data-fact] 文本 + 按 ChartSpec 重绘序列
```

**结构性参数：必须重跑模型。**换指标、换颗粒度（13 周 → 13 月）、增删维度、改图表类型——这些会改变事实 id 集合或序列长度。

**为什么不能偷懒即时刷新。**产物里的 SVG 是模型手画的：13 个点的折线画死在 `<path>` 里。用户把颗粒度切到 13 月,序列变成 12 个值,即时注入只会得到一张点数对不上的图——而 6.2 第 7 条的几何一致性检查正好会拦下它。**即时刷新在这里不是"更快",是"产出一个必然被自己 gate 拦截的东西"。**这两个机制必须一致,否则 S1-4 会照着错的实现。

判定规则写死在 daemon，不靠人工分类：

```ts
// 拿新旧 FactSet 比对，任一为真即走重跑模型
function needsRemake(prev: FactSet, next: FactSet): boolean {
  const idsEqual = setEqual(prev.facts.map(f => f.id), next.facts.map(f => f.id));
  const seriesShapeEqual = prev.series.every(s => {
    const n = next.series.find(x => x.id === s.id);
    return n && n.y.values.length === s.y.values.length;
  });
  return !idsEqual || !seriesShapeEqual
      || prev.series.length !== next.series.length;
}
```

**配色与密度是第三类**：纯样式，连 runner 都不用重跑，改 `tokens.css` 变量即可。

即便如此，筛选性调参仍是"从生成器变成工作台"最直观的体现（架构文档 3.7），也是 FactSet 设计带来的红利——open-design 改任何参数都要重新生成,我们至少在这一类上不用。但要诚实:这不是免费的,它的边界由事实形状划定。

### 9.10 明确不抄的部分

品牌系统（`Brand*` 十余个组件）、媒体后端（图/视频/语音 providers）、Figma 导入、桌面宠物（`desktop-pet`）、社区模板市场、协作与邀请（`collab/`、`InviteDialog`）、AMR 计费相关（`Amr*`）。这些是 open-design 的产品面，与数据看板无关，照抄只会拖慢 S3。

`edit-mode/`（Studio 画布手动微调）列为 P2：概念上对我们有用（人工微调看板），但它与品牌/设计系统耦合较深，等主链路稳了再评估。

---

## 10. 飞书集成实现

能力边界已实测核对（架构文档第五章），此处只写实现约束。

### 10.1 看板宿主：网页应用 H5 `[P0]`

- 免登：前端 `requestAccess` 拿 code → 后端换 `user_access_token` → 取用户 → 映射到 `role_id` → 决定可见 FactSet 子集。
- **岗位鉴权必须在服务端做**，H5 只是宿主。前端拿到的 FactSet 已经是过滤后的。
- 首次上架需管理员审核，**权限申请在 S0 就并行发起**（周期不可控）。

### 10.2 消息卡片 `[P1]`

- 卡片 JSON 2.0，承载"结论 + 关键数字 + 跳转看板 + 建任务"。
- **`card.action.trigger` 必须 3 秒内响应且不得返回 3xx**：回调里只做入队与即时 toast，重算放后台。
- 卡片更新 token 有效 30 分钟、最多用 2 次 → 超时后走"重新推送新卡片"而非更新旧卡片。

### 10.3 多维表格读写 `[P1]`

- `batch_create` / `batch_update` 单次上限 1000 条 → 自己实现分批 + 指数退避。
- **频控不可提额** → 写回设计成异步队列，不在请求链路里同步写。
- 记录变更事件需先配置云文档事件订阅；**公式字段变化不触发事件** → 不要依赖公式列做触发器。
- 读写需双身份（应用身份 / 用户身份）不同权限范围，client 要分开管。

### 10.4 Aily 定位 `[P2]`

**只作可选自然语言入口，不做编排层。**Aily Workflow 的 HTTP 节点把请求转给 `/api/projects/:id/runs`，八层链路在 Bifrost 服务端跑完，成品推回会话。Aily 不可用时降级为 Web 入口，产品不停摆。

**平台限制：**机器人消息不触发另一个机器人 → "Aily 回复触发 Bifrost 推送"走不通，跨机器人协作必须服务端直连。

---

## 11. 开发环境搭建

```bash
# 前置：Node 22 + pnpm 9 + Python 3.12 + uv
git clone <repo> bifrost && cd bifrost
corepack enable && pnpm install --frozen-lockfile
cd apps/runner && uv sync --locked && cd ../..
pnpm exec playwright install chromium

cp .env.example .env     # 填 BIFROST_ENV=dev / 模型端点 / RUNNER_HMAC_SECRET
pnpm dev                 # 并起 daemon:8787 / runner:8788 / web:3000
```

`.env` 关键项：

```
BIFROST_ENV=dev                  # dev | staging | prod，决定数据可见性档位（14 章）
RUNNER_URL=http://127.0.0.1:8788
RUNNER_HMAC_SECRET=<random>
MODEL_ENDPOINT=<OpenAI 兼容端点>
MODEL_API_KEY=<key>
DEFAULT_RUNTIME=claude-cli
FEISHU_APP_ID= / FEISHU_APP_SECRET=
```

**样例数据：**`fixtures/goertek/` 放脱敏样例（含 05 注错集），`pnpm seed` 一键建演示项目。**注错集是治理准确率评测的基准，必须版本化管理**，不能随手改。

---

## 12. 测试策略

### 12.1 分层

| 层 | 范围 | 工具 | 要求 |
| --- | --- | --- | --- |
| 单元 | `packages/gates`、`packages/lint`、SQL 白名单校验器、FactSet 组装 | vitest / pytest | **gate 逻辑覆盖率 ≥ 90%** |
| 契约 | schema 与生成物一致；样例产物过全部 gate | vitest | CI 必跑 |
| 集成 | runner 端到端（数据 → Profile → FactSet） | pytest | 用 fixtures |
| 链路 | 六节点串联，模型调用打桩 | vitest | 桩返回预录制的真实输出 |
| 视觉回归 | 截图与基线对比 | Playwright | 差异阈值 0.5% |
| E2E | 从上传数据到发布看板 | Playwright | 每日一跑 |

### 12.2 模型调用的可测性

模型输出不确定，所以**测试边界放在 FactSet 层而不是产物层**（架构文档第十章的风险对策）：

- **FactSet 完全确定性** → 可写严格回归测试：同样输入必须得到 byte-identical 的 FactSet（`sql_hash` 与 `computed_at` 除外）。
- **产物层用 gate 与截图基线做回归**，不断言 HTML 内容相等。
- **节点调用打桩**：`fixtures/node-outputs/<node>-<case>.txt` 存真实录制的输出，链路测试重放它们。这样能测编排、重试、gate 联动，不花模型钱。

### 12.3 必须有的负例测试

这些是"系统真的在拦错"的证明，也是答辩材料：

```ts
describe('gate 2 事实绑定', () => {
  it('拦下裸数字', ...)                    // <span>72.3%</span> 无 data-fact
  it('拦下不存在的 fact id', ...)
  it('拦下数值与 display 不符', ...)
  it('放过千分位差异', ...)
  it('放过声明豁免的轴刻度', ...)
  it('重算并拦下伪造的 delta', ...)
});

describe('gate 2 图表映射', () => {
  it('拦下缺 data-bf-chart-spec 的图表', ...)      // E_MISSING_CHART_SPEC
  it('拦下无法解析的 chart-spec', ...)             // E_BAD_CHART_SPEC
  it('拦下引用不存在序列的 chart-spec', ...)
  it('拦下 kind 与 marks 不匹配', ...)             // line 却用 <rect>
  it('拦下 SVG 点数与序列长度不符', ...)           // 13 个点 vs 9 个值
  it('拦下趋势画反', ...)                          // ★ 核心：点数相符、数据递增但坐标递减
  it('拦下单点严重偏离', ...)                      // 12 点对、1 点超 2% 容差
  it('放过 2% 容差内的取整误差', ...)
  it('拦下 zeroBased:false 却没给 domain', ...)
  it('ECharts 图表跳过几何检查但仍校验 spec', ...)
});

describe('SQL 白名单', () => {
  it('拒绝未定义指标的自造聚合', ...)
  it('拒绝 DDL 与文件函数', ...)
  it('错误里带 available_metrics', ...)
});

describe('岗位权限', () => {
  it('厂长看板不含 unit_cost 及其中文标签', ...)
});
```

---

## 13. 可观测性与审计

**结构化日志**（pino）字段统一：`run_id` / `project_id` / `node` / `stage` / `attempt` / `role_id`。

**必须记录的指标**（对应架构文档第八章评测体系）：

| 指标 | 来源 |
| --- | --- |
| 各节点 token 与耗时、重试次数 | `node_calls` |
| 各 gate 拦截率与逃逸率 | `gate_results` + 人工抽检 |
| 评审 must_fix 中经复核确属真问题的比例 | `reviews` + 人工标注 |
| `composite_reported` 与 `recomputed` 偏差分布 | `reviews` |
| 端到端墙钟时长（目标 ≤ 10 分钟） | `runs` |
| 岗位越权次数（红线，必须为 0） | `audit_log` |

**审计日志**在生产环境必须完整：每次 SQL 执行记 `sql_hash` / `row_count` / `role_id` / 发起者；每次产物发布记谁在什么时间发给了哪些人。这一条在企业客户尽调时会被直接问到。

---

## 14. 安全实现

### 14.1 分环境数据可见性 `[P0]`

架构文档 3.6 的三档，落到代码是一个开关加三条策略：

```ts
// apps/daemon/src/security/env-policy.ts
export const POLICY = {
  dev:     { modelSeesDetail: true,  cliHasDbCreds: true,  auditRequired: false, previewApi: true  },
  staging: { modelSeesDetail: false, cliHasDbCreds: false, auditRequired: true,  previewApi: true  },
  prod:    { modelSeesDetail: false, cliHasDbCreds: false, auditRequired: true,  previewApi: false },
} as const;
```

**生产环境的三条硬约束：**

1. **执行体环境变量里不注入任何数据库凭据**（`runtimes/defs/*.ts` 的 `env()` 在 prod 下返回白名单外为空）。凭据只存在于 runner 进程。
2. **模型只见 schema 与 profile**：列名、类型、基数、空值率、极值，**不含明细行**。`sample_values` 在 prod 下不注入。
3. **查询由 runner 代执行**，结果按岗位画像过滤后回传。

第 2 条与"模型不写数字"是同一件事的两面：模型看不到明细，就没有能力编造一个"看起来对"的数字。**安全约束与可信约束在这里合流，不需要两套机制**——这是架构文档 3.6 的核心洞察，实现时不要拆成两套配置。

### 14.2 其他

- **CLI 高权限运行的收敛**：dev 下允许 `--yolo` 类高权限，但工作目录限制在 `projects/<id>/runs/<run-id>/`；prod 下禁用文件写权限之外的一切能力。
- **SSRF**：模型端点 `baseUrl` 校验，拦私网地址（照学 open-design 的 daemon 策略）。
- **产物 XSS**：产物在沙箱 iframe 内且 CSP `connect-src 'none'`（9.3）；发布到飞书 H5 时同样注入 CSP 头。
- **HMAC**：daemon → runner 全部请求签名，防止本机其他进程调 `/internal/execute` 拖数据。
- **密钥**：一律走环境变量，禁止进仓库；CI 加 secret 扫描。

---

## 15. 工程规范

### 15.1 分支与提交

`main` 保护；功能分支 `feat/<scope>-<slug>`；提交用 Conventional Commits（`feat(gates): ...`）。PR 必须过 CI + 一人 review。

### 15.2 CI 流水线

```yaml
jobs:
  contracts:   # schema → 生成物一致性（git diff --exit-code）
  lint:        # eslint + prettier + ruff + mypy
  unit:        # vitest + pytest，gate 覆盖率门槛 90%
  integration: # runner 端到端
  chain:       # 六节点打桩链路
  visual:      # Playwright 截图回归
  license:     # 许可证审计（15.4）
```

### 15.3 代码风格

TS 严格模式、禁 `any`（必要处 `unknown` + 收窄）；Python 全量类型注解 + mypy；不写"解释代码做什么"的注释，只写"为什么这样"的注释；契约字段的语义写在 JSON Schema 的 `description` 里，不写在代码注释里（单一来源）。

### 15.4 许可证审计 `[P0]`

**这一条在企业客户尽调时会被直接问到，必须进 CI。**

```
允许：MIT / Apache-2.0 / BSD / ISC
禁止直接引入：
  - anthropics/skills           LICENSE 明确禁止复制、衍生、分发 → 只能读，一个字不能抄
  - nimrodfisher/data-analytics-skills  无 LICENSE = 保留全部权利 → 只吸收分类法，文字全部重写
  - WrenAI                      非标准自定义许可
  - Lightdash 的 ee/ 目录        商业许可
  - soda-core                    Elastic License 2.0
```

CI 脚本扫 `package.json` / `pyproject.toml` 的依赖树许可证 + 扫源码里是否出现禁止清单仓库的特征字符串。移植 open-design 代码的文件头必须保留版权与 NOTICE 并注明变更（Apache-2.0 要求）。

---

## 16. 任务分解

对应架构文档第七章分期。每个工单标注依赖与验收标准。

### S0 地基（3 天）`[P0]`

**关键路径，不要压缩。**FactSet Schema 与 metrics.yml 决定整个项目的上限。

| # | 工单 | 依赖 | 验收 |
| --- | --- | --- | --- |
| S0-1 | monorepo 骨架 + 双运行时起得来 + CI 空跑 | — | `pnpm dev` 三个服务就绪 |
| S0-2 | `packages/contracts` 全部 schema 定稿 + 生成器 | — | TS/pydantic 生成物一致，CI 校验通过 |
| S0-3 | connectors 读 xlsx/csv + profiling | S0-1 | 样例数据出 Profile |
| S0-4 | `09_字段字典` → metrics.yml + loader | S0-2 | 加载并校验通过 |
| S0-5 | **数据岛注入器** | S0-2 | 给定 HTML + FactSet 注入成功 |
| S0-6 | **gate 2 事实绑定**（含 12.3 全部负例） | S0-5 | 负例测试全绿 |
| S0-7 | 一套数据场景 design tokens | — | tokens.css 可加载 |
| **交付物** | 一份真实数据驱动、每个数字可点开溯源的单卡片 | | |

S0-5 与 S0-6 提前到 S0 是 V3 的调整：**它们才是"模型自由发挥但数字可信"的技术支点，必须最早验证**（V2 那版这里是 Dashboard Spec Schema，已撤销）。

### S1 主链路（1 周）`[P0]`

| # | 工单 | 依赖 |
| --- | --- | --- |
| S1-1 | 洞察节点 + A 类 skill 前 3 个 | S0-4 |
| S1-2 | 查询节点 + **SQL 白名单校验器** | S0-4 |
| S1-3 | FactSet 生成（含 flags、display、sql_hash） | S1-2 |
| S1-4 | 制作节点 full 模式 + 模板库 2 套 + B 类 skill 前 3 个 | S0-5, S0-7 |
| S1-5 | gate 1/3/4/5 | S0-6 |
| S1-6 | orchestrator 状态机 + SSE + 重跑起点 | S1-1..5 |
| S1-7 | 执行体适配层（CLI + API 各一种） | — |
| **交付物** | 单岗位（厂长）全链路可信 HTML 看板 + Verify 面板雏形 | |

### S2 千人千面与治理（1 周）`[P1]`

三岗位画像与路由、gate 3 权限颗粒度、治理节点 + D 类 skill、05 注错集实测准确率、项目记忆写入与注入、记忆面板。
**交付物**：三份看板 + 治理准确率实测数字（F1 ≥ 0.9，高危召回 100%）。

### S3 双评审与视觉闭环（1 周）`[P0]`

事实评审节点、Playwright 多视口截图 + 中文字体就绪断言、呈现评审节点（多模态）、`composite` 服务端重算、repair target 路由、制作节点 patch 模式、**工作台外壳照搬 open-design**（第 9 章：`.split` 分栏 + 标签注册表 + iframe 保活池 + 设置对话框）、溯源检查器。
**交付物**：评审打回并自动修正的案例回放（这是答辩最有力的一段演示）。

### S4 飞书融合（1 周）`[P1]`

H5 宿主 + 免登岗位鉴权、多维表格读写（分批退避）、消息卡片（异步回调）、审批 v4、任务 v2、Aily 入口。
**交付物**：飞书内端到端——一句话到三份看板到岗位推送。

### S5 打磨与加分（1 周）`[P2]`

Studio 手改、更多 design system、PDF/PPTX 导出、反 AI 味 lint 十五条、**对比实验**（Bifrost vs 通用大模型 vs 人工，专家盲评）、演示脚本。
**交付物**：盲评对比结果 + 答辩演示流程。

### 并行事项

**飞书权限申请在 S0 第一天就发起**（应用可用范围变更需版本审核，周期不可控，不能等到 S4）。

---

## 17. 附录

### 17.1 错误码表

| 码 | 含义 | 处置 |
| --- | --- | --- |
| `E_SCHEMA_INVALID` | 节点输出不合契约 | 重试，最多 3 次 |
| `E_METRIC_UNDEFINED` | SQL 引用未定义指标 | 退回查询节点，附 available_metrics |
| `E_SQL_FORBIDDEN` | DDL/DML/文件函数 | 退回查询节点 |
| `E_ASSERTION_FAILED` | 数据断言失败 | 停在 L3，不进制作 |
| `E_UNBOUND_NUMBER` | 裸数字未绑定事实 | 退回制作节点 patch |
| `E_FACT_NOT_FOUND` | 引用了不存在的 fact id | 退回制作节点 patch |
| `E_FACT_MISMATCH` | 显示值与 display 不符 | 退回制作节点 patch |
| `E_MISSING_CHART_SPEC` | 图表缺 data-bf-chart-spec | 退回制作节点 patch |
| `E_BAD_CHART_SPEC` | chart-spec 解析失败或字段非法 | 退回制作节点 patch |
| `E_CHART_GEOMETRY_MISMATCH` | 手绘 SVG 坐标与序列数值不符（画反/画错） | 退回制作节点 patch |
| `E_EXTERNAL_RESOURCE` | 产物不自包含 | 退回制作节点 |
| `E_MISSING_ANCHOR` | 卡片缺 data-bf-card | 退回制作节点 |
| `E_SENSITIVITY` / `E_FORBIDDEN_FIELD` | 岗位越权 | **红线，不重试，直接失败告警** |
| `E_MISLEADING_ENCODING` | 误导性图表编码 | 退回制作节点 patch |
| `E_REVIEW_BLOCKED` | 轮次耗尽仍有 must_fix | 不发布，转人工 |
| `E_RUNTIME_CAPABILITY` | 无可用执行体满足 capability | 明确报缺什么，不静默降级 |

### 17.2 关键设计决定速查

供后续讨论时快速对齐，不要重新论证：

| 决定 | 理由 |
| --- | --- |
| 模型手写 HTML，不走规格渲染 | 渲染器代码会写死看板上限，做不到"媲美顶级数据工程师" |
| FactSet 由代码生成，模型只见索引 | 模型手上没有数字 = 结构上无法编造 |
| `memories` 表无 `value` 列 | 记忆红线固化在 schema，不靠自觉 |
| `fallback_policy: block`（非 ship_best） | 评审不能阻断就只是没人读的报告 |
| `E_MISSING_ANCHOR` 为 block | open-design 设为 P2 导致评审无处可路由 |
| composite 服务端重算 | 不信任模型的自我评价 |
| 制作节点不拆骨架/卡片 | 分卡并行必然拼贴感，而拼贴感是 AI 味主要来源 |
| 双运行时（Node + Python） | DuckDB/pandera 与 Agent/Playwright 生态分属两边 |
| 不 fork open-design | 上游 11 天一版；我们要改的正是它的核心假设 |
| 测试边界在 FactSet 层 | 模型输出不确定，但 FactSet 完全确定 |

### 17.3 与架构文档的对应关系

| 开发文档章节 | 架构文档出处 |
| --- | --- |
| 3.6 FactSet | 2.2、3.2 |
| 3.7 产物 HTML 约定 | 2.2 三条约束 |
| 3.8 评审意见 | 3.3 两个评审点与权限边界 |
| 3.9 记忆条目 | 3.4 记忆分层 |
| 4.4 SQL 白名单 | 3.2 第二段 |
| 6.x 六道 gate | 3.5 gate 表 |
| 6.7 反 AI 味 lint | 2.4 末段 |
| 14.1 分环境策略 | 3.6 |
| 16 任务分解 | 第七章分期 |
