# Bifrost 上下文管理改进方案 V1

> **基于 OpenCode 最佳实践的完整改进方案**  
> 作者：Claude  
> 日期：2026-08-07  
> 版本：V1.0

---

## 一、执行摘要

### 1.1 背景

Bifrost 项目当前面临的核心挑战：

1. **Skills 注入无压缩**：15K tokens 全量注入，长会话中重复成本高
2. **记忆系统缺失**：无跨会话项目上下文保留，评审意见、业务异常等关键信息丢失
3. **上下文管理缺失**：长会话无压缩机制，token 消耗不可控
4. **Inception messages 缺失**：核心约束（如"不允许编造数值"）未固化

### 1.2 方案目标

借鉴 OpenCode 成熟机制，为 Bifrost 设计一套**轻量级、数据可信优先**的上下文管理系统：

- **Token 节省 60-70%**（Skills 15K→3K，记忆智能筛选）
- **跨会话记忆持久化**（四层架构：任务/项目/组织/永久规则）
- **Inception messages 固化**（数据可信铁律永不丢失）
- **后台压缩优化**（主 Agent 用 Opus，历史学家用 Haiku）

---

## 二、Bifrost 当前痛点分析

### 2.1 与 OpenCode 的场景差异

| 维度 | OpenCode | Bifrost |
|------|----------|---------|
| **核心场景** | 对话式编程助手 | 数据看板生成引擎 |
| **会话特征** | 长期迭代（100+ 轮） | 单次生成为主（6 节点链路） |
| **数据真实性** | 严格（执行真实代码） | **更严格**（事实集强绑定） |
| **压缩需求** | 高（避免 compaction） | 中（但 skills 压缩收益大） |
| **跨会话记忆** | 中等（项目上下文） | **高**（业务异常、口径争议必须记住） |

**关键洞察**：OpenCode 的"避免 compaction"哲学不适用 Bifrost，但其 **skills 压缩、四层记忆、inception messages** 三大机制高度适配。

### 2.2 当前实现的不足

#### 问题 1：Skills 全量注入，长会话成本高

**现状**（来自记忆 `bifrost_tech_selection.md`）：
```typescript
// apps/daemon/src/prompts/assemble.ts
async function loadSkills(node: string, context: { triggers?: string[] }) {
  const skillsDir = resolve(__dirname, '../../../..', 'skills');
  const files = await readdir(skillsDir);
  
  // 问题：匹配成功后直接添加完整内容
  for (const file of mdFiles) {
    if (matches) {
      matchedSkills.push(content);  // ❌ 15K tokens 全量
    }
  }
}
```

**后果**：
- 单次注入 15K tokens
- 评审重试 3 轮 × 15K = 45K tokens 浪费
- 与 OpenCode 社区插件报告的"skills 重复注入"同一类问题

#### 问题 2：记忆系统未实现跨会话持久化

**现状**：
```typescript
// apps/daemon/src/memory/store.ts
export class JsonlMemoryStore implements MemoryStore {
  private taskMemories = new Map<string, MemoryEntry[]>(); // ✅ 任务层
  
  async read(projectId: string): Promise<MemoryEntry[]> {
    // ✅ project 层：memory/project/<projectId>.jsonl
    // ✅ org 层：memory/org.jsonl
    // ❌ 缺失：跨会话检索策略
    // ❌ 缺失：相关性打分
    // ❌ 缺失：时间衰减
  }
}
```

**后果**：
- 项目记忆已持久化，但**检索策略缺失**
- 历史评审意见、业务异常无法自动注入
- 每次运行都像"第一次见到这个项目"

#### 问题 3：核心约束未固化为 Inception Messages

**现状**：
```typescript
// apps/daemon/src/prompts/assemble.ts:32
export async function assemblePrompt(opts: AssembleOptions): Promise<string> {
  const sections: string[] = [];
  
  // 1. 平台身份与全局纪律
  const corePrompt = await readFile(resolve(__dirname, 'bifrost-core.md'), 'utf-8');
  sections.push('# 1. 平台身份与全局纪律\n\n' + corePrompt);
  
  // ❌ 问题：没有标记为 inception，压缩时可能丢失
}
```

**后果**：
- "不允许编造数值"等铁律在长会话中可能被稀释
- 与 OpenCode 的 inception messages 机制缺乏互操作性

---

## 三、借鉴 OpenCode 的核心机制

### 3.1 Inception Messages（永久基石）

#### OpenCode 实现（Issue #4659）

```typescript
interface InceptionMessage {
  role: 'inception';
  content: string;
  priority: 'immutable' | 'critical' | 'preserved';
  categories: ['architecture', 'constraints', 'discoveries', 'preferences'];
}
```

**关键特性**：
- 所有压缩操作中永久保留
- 不参与相关性评分
- 存储在 `{session}/INCEPTION.md`

#### Bifrost 适配方案


**Bifrost Inception 清单**：

```markdown
# INCEPTION.md

## [IMMUTABLE] 数据可信铁律

1. **事实绑定强约束**：所有数值必须用 `data-fact` 绑定，未绑定数字直接阻断
2. **语义层唯一源**：只能引用 `metrics.yml` 白名单指标，禁止自造指标
3. **溯源完整性**：每个事实必须包含 `definition_ref`、`sql_hash`、`row_count`
4. **六道 Gate 不可旁路**：结构/绑定/口径/断言/误导/评审，任一失败即阻断

## [CRITICAL] 岗位权限边界

- 厂长：可见产线、设备、班次，**不可见**成本、利润
- 供应链负责人：可见物料、订单、库存，**不可见**设备状态
- 经营层：全局视图，但**必须**经过脱敏

## [PRESERVED] 评审质量标准

- must_fix 未清零不得发布
- 视觉截图必须桌面+手机双验证
- repair target 必须路由到稳定锚点

## [PRESERVED] 设计美学原则

- 安静、专业、适合重复扫描
- 禁止：紫色渐变、装饰光斑、slop emoji、lorem ipsum
- 圆角 ≤ 8px，图标使用 Lucide
```

**实现位置**：
```typescript
// packages/context/src/inception.ts
export const INCEPTION_MESSAGES = {
  immutable: [
    readFileSync(resolve(__dirname, '../inception/data-integrity.md'), 'utf-8'),
  ],
  critical: [
    readFileSync(resolve(__dirname, '../inception/role-boundaries.md'), 'utf-8'),
  ],
  preserved: [
    readFileSync(resolve(__dirname, '../inception/review-standards.md'), 'utf-8'),
    readFileSync(resolve(__dirname, '../inception/design-principles.md'), 'utf-8'),
  ],
};

// apps/daemon/src/prompts/assemble.ts 修改
export async function assemblePrompt(opts: AssembleOptions): Promise<string> {
  const sections: string[] = [];
  
  // ✅ 明确标记为 inception
  sections.push({
    type: 'inception',
    priority: 'immutable',
    content: INCEPTION_MESSAGES.immutable.join('\n\n---\n\n'),
  });
  
  // ... 其他动态内容
}
```

---

### 3.2 Skills 智能压缩（PageRank + Top-K）

#### OpenCode 痛点（来自调研）

- Skills 重复注入（Issue #5999）：`<available_skills>` 被注入两次，单次 6K tokens
- 社区插件 `opencode-plugin-preload-skills` 实现懒加载，但未压缩内容

#### Aider 的 Personalized PageRank（Apache-2.0 可复用）

**核心算法**（来自 `aider/repomap.py`）：

```python
def personalized_pagerank(graph, personalization, damping=0.85):
    """
    graph: {node: [outgoing_edges]}
    personalization: {node: weight}  # 种子节点权重
    """
    ranks = {node: 1.0 / len(graph) for node in graph}
    
    for _ in range(100):  # 迭代收敛
        new_ranks = {}
        for node in graph:
            inflow = sum(
                ranks[src] / len(graph[src]) 
                for src in graph if node in graph[src]
            )
            personal_weight = personalization.get(node, 1.0 / len(graph))
            new_ranks[node] = (1 - damping) * personal_weight + damping * inflow
        ranks = new_ranks
    
    return ranks
```

**Bifrost 适配**：

```typescript
// packages/skills-index/src/compress.ts
export function compressSkills(
  allSkills: SkillNode[],
  context: {
    triggers: string[];        // 用户诉求关键词
    mentionedSkills: string[]; // 明确提到的 skill
    node: string;              // 当前节点
    tokenBudget: number;       // 3000 tokens
  }
): SkillNode[] {
  // 1. 构建依赖图
  const graph = buildSkillGraph(allSkills);
  
  // 2. 计算个性化权重
  const personalization = new Map<string, number>();
  for (const skill of allSkills) {
    let score = 1.0;
    
    // 用户明确提到：50x
    if (context.mentionedSkills.includes(skill.name)) {
      score *= 50;
    }
    
    // 标题匹配：15x
    if (context.triggers.some(t => skill.name.toLowerCase().includes(t.toLowerCase()))) {
      score *= 15;
    }
    
    // frontmatter triggers 匹配：12x
    if (skill.triggers.some(st => context.triggers.some(t => 
      st.toLowerCase().includes(t.toLowerCase())
    ))) {
      score *= 12;
    }
    
    personalization.set(skill.name, score);
  }
  
  // 3. PageRank 排名
  const ranks = personalizedPageRank(graph, personalization);
  
  // 4. 按分数排序 + Top-K 截断
  const sorted = allSkills
    .map(skill => ({ skill, rank: ranks.get(skill.name) || 0 }))
    .sort((a, b) => b.rank - a.rank);
  
  const selected: SkillNode[] = [];
  let totalTokens = 0;
  
  for (const { skill } of sorted) {
    if (totalTokens + skill.tokenCount > context.tokenBudget) break;
    selected.push(skill);
    totalTokens += skill.tokenCount;
  }
  
  return selected;
}
```

**效果预估**：
- 原始：15K tokens（全量）
- 压缩后：3K tokens（Top-K）
- **节省 80%**

---

### 3.3 四层记忆架构（跨会话持久化）

#### OpenCode 社区方案（`opencode-working-memory`）

```
┌─────────────────────────────────────┐
│ Layer 1: Persistent Core Memory    │  ← ~/.bifrost/memory/core.jsonl
│ (architecture, business rules)      │
├─────────────────────────────────────┤
│ Layer 2: Session Working Memory    │  ← 当前运行的活跃信息
│ (current findings, retry context)   │
├─────────────────────────────────────┤
│ Layer 3: Smart Pruning             │  ← 相关性打分 + 时间衰减
│ (BM25 + vector search)             │
├─────────────────────────────────────┤
│ Layer 4: Pressure Monitoring       │  ← Token 预算管理
│ (auto-compact when near limit)     │
└─────────────────────────────────────┘
```

#### Bifrost 实现方案

**数据结构**：

```typescript
// packages/memory/src/types.ts
export interface MemoryEntry {
  mem_id: string;
  layer: 'core' | 'project' | 'session' | 'task';
  kind: 
    | 'business_exception'      // 不应报为异常的业务规则
    | 'rejected_proposal'       // 被驳回的提议
    | 'definition_dispute'      // 口径争议
    | 'review_finding'          // 评审问题模式
    | 'preference';             // 用户偏好
  
  scope: {
    project_id?: string;
    metrics?: string[];          // 涉及的指标
    dims?: Record<string, string>; // 涉及的维度
  };
  
  text: string;
  embedding?: number[];          // 768-dim (Phase 3 可选)
  created_at: string;
  expires_at?: string;
  confirmed_by?: string;         // 升级到 core 需要人确认
}
```

**Layer 1: Persistent Core Memory**（永久规则）

```typescript
// 存储位置：~/.bifrost/memory/core.jsonl
// 典型内容：
{
  "mem_id": "core_001",
  "layer": "core",
  "kind": "business_exception",
  "text": "A02 产线夜班换型停机属于计划内，不应标记为异常",
  "scope": { "metrics": ["availability", "oee"], "dims": { "line_code": "A02", "shift": "night" } },
  "confirmed_by": "user@goertek.com",
  "created_at": "2026-07-15T10:30:00+08:00"
}
```

**Layer 2: Project Memory**（项目级持久化）

```typescript
// 存储位置：~/.bifrost/memory/project/<project_id>.jsonl
// 自动写入，人可编辑
{
  "mem_id": "proj_goertek_042",
  "layer": "project",
  "kind": "definition_dispute",
  "text": "OEE 口径与三率复算不一致，需以多维表格字段字典为准",
  "scope": { "project_id": "goertek", "metrics": ["oee", "availability", "performance", "quality"] },
  "created_at": "2026-08-03T14:22:00+08:00"
}
```

**Layer 3: Smart Pruning**（相关性打分）

```typescript
// packages/memory/src/retrieval.ts
export function retrieveRelevantMemory(
  context: {
    planMetrics: string[];
    planDims: Record<string, string[]>;
    roleId: string;
  },
  options: {
    maxCount: number = 20;
    minRelevanceScore: number = 0.5;
  }
): MemoryEntry[] {
  const allMemories = [
    ...loadCoreMemory(),
    ...loadProjectMemory(context.projectId),
  ];
  
  const scored = allMemories.map(mem => ({
    entry: mem,
    score: scoreRelevance(mem, context),
  }));
  
  return scored
    .filter(s => s.score >= options.minRelevanceScore)
    .sort((a, b) => b.score - a.score)
    .slice(0, options.maxCount)
    .map(s => s.entry);
}

function scoreRelevance(mem: MemoryEntry, context: Context): number {
  let score = 0;
  
  // 1. Metrics 交集（权重 2.0）
  const metricsOverlap = intersection(mem.scope.metrics, context.planMetrics).length;
  score += metricsOverlap * 2.0;
  
  // 2. Dims 交集（权重 1.0）
  for (const [key, values] of Object.entries(mem.scope.dims || {})) {
    if (context.planDims[key]?.some(v => values.includes(v))) {
      score += 1.0;
    }
  }
  
  // 3. Kind 优先级
  const kindBonus = {
    business_exception: 2.0,
    definition_dispute: 1.5,
    rejected_proposal: 1.0,
    review_finding: 1.0,
    preference: 0.5,
  };
  score += kindBonus[mem.kind] || 0;
  
  // 4. 时间衰减（-0.1 per month）
  const ageMonths = (Date.now() - new Date(mem.created_at).getTime()) / (30 * 24 * 3600 * 1000);
  score -= Math.min(ageMonths * 0.1, 3);
  
  return Math.max(0, score);
}
```

**Layer 4: Pressure Monitoring**（Token 预算）

```typescript
// packages/memory/src/budget.ts
export function buildMemoryDigest(
  entries: MemoryEntry[],
  tokenBudget: number = 1000
): string {
  let digest = '## 项目记忆\n\n';
  let tokens = 0;
  
  for (const entry of entries) {
    const snippet = `- [${entry.mem_id}] ${entry.text}\n`;
    const snippetTokens = estimateTokens(snippet);
    
    if (tokens + snippetTokens > tokenBudget) break;
    
    digest += snippet;
    tokens += snippetTokens;
  }
  
  return digest;
}
```

---

### 3.4 后台压缩（magic-context 启发）

#### OpenCode 的 magic-context 插件

**核心创新**：
```
主 Agent (Opus) 继续工作
  ↓
后台模型 (Haiku) 异步压缩旧对话
  ↓
压缩结果自动注入回主 context
```

**成本优势**：
- Opus 压缩 100K tokens：100K × $15/1M = $1.50
- Haiku 后台压缩：100K × $0.25/1M = $0.025（**60倍节省**）

#### Bifrost 场景适配

**问题**：Bifrost 是单次生成，没有"长会话"，后台压缩意义何在？

**答案**：**评审重试轮次中的历史压缩**

```typescript
// apps/daemon/src/orchestrator/maker-node.ts
async function runMakerWithRetry(
  attempt: number,
  priorFindings: Finding[]
): Promise<MakerOutput> {
  if (attempt > 1) {
    // ❌ 当前：将完整的 priorFindings 注入
    // ✅ 优化：后台 Haiku 压缩前两轮的冗长错误描述
    
    const compressed = await compressInBackground({
      model: 'claude-3-5-haiku-20241022',
      input: priorFindings.slice(0, -1),  // 压缩除最新一轮外的所有
      prompt: '提取核心问题和修复方向，丢弃冗长描述',
    });
    
    // 只保留最新一轮的完整 findings + 压缩后的历史
    const context = {
      latestFindings: priorFindings[priorFindings.length - 1],
      historySummary: compressed,
    };
  }
}
```

**效果**：
- 第 3 轮重试时，前两轮的 findings 从 5K tokens 压缩到 500 tokens
- 节省 4.5K × $15/1M = $0.0675 per run

---

## 四、完整改进方案

### 4.1 架构总览

```
┌─────────────────────────────────────────────────────────┐
│                   Bifrost Prompt Assembly                │
└─────────────────────────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ↓                    ↓                    ↓
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Inception   │    │   Skills     │    │   Memory     │
│  Messages    │    │  Compressor  │    │  Retrieval   │
│              │    │              │    │              │
│ • 数据可信   │    │ • PageRank   │    │ • 4-layer    │
│ • 岗位权限   │    │ • Top-K      │    │ • Smart      │
│ • 评审标准   │    │ • 15K→3K     │    │   pruning    │
└──────────────┘    └──────────────┘    └──────────────┘
        │                    │                    │
        └────────────────────┼────────────────────┘
                             ↓
                  ┌─────────────────────┐
                  │  Background         │
                  │  Compression        │
                  │  (Haiku for history)│
                  └─────────────────────┘
```

### 4.2 实施路线图（3 个 Phase）

#### Phase 1: 快速见效（P0，2-3 天）

**目标**：Token 节省 60%，零破坏性变更

**任务清单**：

1. **Inception Messages 固化**
   - [ ] 创建 `packages/context/inception/` 目录
   - [ ] 拆分 `bifrost-core.md` 为四个文件（data-integrity / role-boundaries / review-standards / design-principles）
   - [ ] 在 `assemblePrompt()` 中标记 `type: 'inception'`
   - [ ] 编写单元测试：验证 inception 内容在任何场景下都存在

2. **Skills PageRank 压缩**
   - [ ] 实现 `packages/skills-index/src/pagerank.ts`
   - [ ] 实现 `packages/skills-index/src/compress.ts`
   - [ ] 修改 `apps/daemon/src/prompts/assemble.ts` 的 `loadSkills()` 调用压缩器
   - [ ] 配置 `MAX_SKILL_TOKENS=3000`
   - [ ] 编写测试：验证 token 预算不超标

3. **记忆检索优化**
   - [ ] 实现 `packages/memory/src/retrieval.ts` 的相关性打分
   - [ ] 配置 `MAX_MEMORY_TOKENS=1000`、`MEMORY_MIN_RELEVANCE_SCORE=0.5`
   - [ ] 修改 `assemblePrompt()` 的记忆注入逻辑
   - [ ] 编写测试：验证高相关性记忆优先注入

**验收标准**：
- ✅ 单次 prompt 从 20K tokens 降至 8K tokens（60% 节省）
- ✅ CI 全部通过
- ✅ 现有功能零回归


#### Phase 2: 跨会话记忆强化（P1，3-5 天）

**目标**：业务异常、口径争议、评审模式自动记住

**任务清单**：

1. **四层记忆完整实现**
   - [ ] 实现 `packages/memory/src/core-store.ts`（core layer，~/.bifrost/memory/core.jsonl）
   - [ ] 扩展 `packages/memory/src/store.ts`（已有 project/task 层）
   - [ ] 实现自动写入规则：review_finding 自动写 project 层
   - [ ] 实现升级规则：用户确认后从 project 提升到 core

2. **记忆管理 UI**
   - [ ] 在 Next.js 工作台添加"记忆面板"（参考 open-design 的 MemoryHooksPanel）
   - [ ] 支持查看、编辑、删除 project 记忆
   - [ ] 支持"提升到组织记忆"操作（需人工确认）

3. **与 Claude Code 互操作**
   - [ ] 支持读写 `~/.claude/memory/*.md` 格式
   - [ ] 实现双向同步：Bifrost ↔ Claude Code

**验收标准**：
- ✅ 评审发现的问题在下次运行中自动规避
- ✅ 业务异常规则跨项目生效
- ✅ 记忆面板可用且操作直观

#### Phase 3: 向量检索增强（P2，5-7 天，可选）

**目标**：大规模记忆（1000+ 条）下仍高效检索

**任务清单**：

1. **Embedding 存储**
   - [ ] 选型：LanceDB（轻量） / Milvus（生产级）
   - [ ] 实现 `packages/memory/src/vector-store.ts`
   - [ ] 为所有记忆生成 embedding（text-embedding-3-small）

2. **混合检索**
   - [ ] 实现 BM25 关键词检索（现有）
   - [ ] 实现向量相似度检索
   - [ ] 实现 RRF（Reciprocal Rank Fusion）重排序

3. **降级策略**
   - [ ] 向量索引失败时自动降级为 BM25
   - [ ] 监控检索延迟，超过 200ms 告警

**验收标准**：
- ✅ 1000 条记忆下检索延迟 < 200ms
- ✅ 混合检索 Recall@10 > 0.85
- ✅ 向量索引故障不影响系统可用性

---

### 4.3 后台压缩实现（可选优化）

**适用场景**：评审重试 3 轮时，前两轮的 findings 压缩

```typescript
// packages/compression/src/background.ts
export async function compressInBackground(opts: {
  model: 'claude-3-5-haiku-20241022';
  input: Finding[];
  prompt: string;
}): Promise<string> {
  const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
  
  const response = await client.messages.create({
    model: opts.model,
    max_tokens: 1024,
    messages: [{
      role: 'user',
      content: `${opts.prompt}\n\n${JSON.stringify(opts.input, null, 2)}`,
    }],
  });
  
  return response.content[0].text;
}

// apps/daemon/src/orchestrator/maker-node.ts 调用
if (attempt > 2) {
  const historySummary = await compressInBackground({
    model: 'claude-3-5-haiku-20241022',
    input: priorFindings.slice(0, -1),
    prompt: '提取核心问题类型、修复方向和反复出现的模式。丢弃冗长描述和重复信息。',
  });
  
  context.priorFindings = [
    { summary: historySummary, compressed: true },
    ...priorFindings.slice(-1),  // 保留最新一轮完整
  ];
}
```

**成本节省**：
- 每次压缩节省：4.5K tokens × ($15 - $0.25) / 1M = $0.066
- 1000 次运行累计节省：$66

---

## 五、与 open-design 的协同

### 5.1 UI 层：照搬 open-design

**已确认方案**（来自记忆 `bifrost_ui_decision.md`）：

- 布局：对话栏 + 拖拽手柄 + 工作区（两栏）
- 折叠动画：`@property` 注册 CSS 变量，200ms/140ms 不对称过渡
- 标签系统：`tab-launcher.ts` 注册表 + 前缀约定
- iframe 保活：LRU 上限 3，`.pooled-iframe-host{display:contents}`
- 设置弹出：单一 SettingsDialog + 22 个 section token

### 5.2 Skill 注入：对齐 open-design 格式

**open-design 的 skill frontmatter**：

```yaml
---
od:name: live-dashboard
od:description: Create interactive HTML dashboards with real-time data
od:triggers:
  - dashboard
  - live data
  - real-time
---
```

**Bifrost 的 frontmatter**（当前）：

```yaml
---
applies_to:
  - insight
  - maker
phase: analysis
triggers:
  - OEE
  - 损失树
---
```

**对齐方案**：

```yaml
---
# Bifrost 自有字段
applies_to: [insight, maker]
phase: analysis

# 兼容 open-design（未来互操作）
od:name: oee-loss-tree-analysis
od:triggers: [OEE, 损失树, 六大损失]
---
```

### 5.3 不照搬的部分

| 机制 | open-design | Bifrost | 原因 |
|------|-------------|---------|------|
| **数值生成** | 允许编造 | 事实集强绑定 | 数据可信是核心差异 |
| **Compaction** | 无或轻量级 | 主动压缩 | Skills 15K→3K 收益大 |
| **评审机制** | 五维评分报告 | must_fix 阻断 | 需要硬阻断能力 |
| **CLI spawn** | 25 种 code-agent | 无，纯 Node/Python | 不需要外部执行体 |

---

## 六、风险与缓解

### 6.1 风险矩阵

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| **PageRank 压缩过度，遗漏关键 skill** | 高 | 中 | 允许用户明确指定必需 skills（50x 权重） |
| **记忆相关性打分不准** | 中 | 中 | Phase 3 引入向量检索 + 混合重排 |
| **后台压缩延迟影响重试** | 低 | 低 | 设置 5s 超时，超时则跳过压缩 |
| **与 open-design 互操作性差** | 低 | 低 | Frontmatter 双格式兼容 |
| **Inception messages 被意外修改** | 高 | 低 | CI 中加 immutability 测试 |

### 6.2 回滚策略

所有改进都设计为**可独立开关**：

```typescript
// packages/context/src/config.ts
export const CONTEXT_CONFIG = {
  enableInception: process.env.ENABLE_INCEPTION !== 'false',  // 默认开启
  enableSkillsCompression: process.env.ENABLE_SKILLS_COMPRESSION === 'true',  // Phase 1 开启
  enableSmartMemory: process.env.ENABLE_SMART_MEMORY === 'true',  // Phase 2 开启
  enableVectorRetrieval: process.env.ENABLE_VECTOR_RETRIEVAL === 'true',  // Phase 3 开启
  enableBackgroundCompression: process.env.ENABLE_BG_COMPRESSION === 'true',  // 可选
  
  maxSkillTokens: parseInt(process.env.MAX_SKILL_TOKENS || '3000'),
  maxMemoryTokens: parseInt(process.env.MAX_MEMORY_TOKENS || '1000'),
};
```

**回滚命令**：

```bash
# 关闭 Skills 压缩
export ENABLE_SKILLS_COMPRESSION=false

# 增加 Skills 预算（紧急情况）
export MAX_SKILL_TOKENS=15000
```

---

## 七、成本效益分析

### 7.1 Token 节省预估

| 优化项 | 当前 | 优化后 | 节省 |
|--------|------|--------|------|
| **Skills 注入** | 15K tokens | 3K tokens | **80%** |
| **记忆摘要** | 2K tokens（全量） | 1K tokens（Top-K） | **50%** |
| **重试历史** | 5K tokens × 2 轮 | 0.5K tokens（压缩） | **90%** |
| **总节省** | ~22K tokens | ~4.5K tokens | **~80%** |

**单次运行成本**（Opus 3.5）：
- 优化前：22K input × $15/1M = $0.33
- 优化后：4.5K input × $15/1M = $0.068
- **节省 $0.262 per run**

**1000 次运行**：节省 **$262**

### 7.2 开发成本

| Phase | 人日 | 优先级 |
|-------|------|--------|
| Phase 1（快速见效） | 2-3 天 | **P0** |
| Phase 2（跨会话记忆） | 3-5 天 | **P1** |
| Phase 3（向量检索） | 5-7 天 | P2（可选） |
| **总计** | 10-15 天 | - |

**ROI**：
- 成本节省：$262/1000 次
- 开发投入：~12 人日
- **预计 5000 次运行后回本**

---

## 八、验收标准

### 8.1 Phase 1 验收（P0）

- [ ] **Token 节省达标**：单次 prompt 从 20K 降至 8K（60%）
- [ ] **Inception 固化**：数据可信铁律在任何场景下都存在
- [ ] **Skills 压缩有效**：Top-K 选择的 skills 覆盖用户诉求
- [ ] **记忆检索准确**：高相关性记忆排在前列
- [ ] **零功能回归**：现有测试全部通过
- [ ] **CI 通过**：新增 150+ 行测试覆盖

### 8.2 Phase 2 验收（P1）

- [ ] **跨会话记忆生效**：评审问题模式在下次运行中自动规避
- [ ] **记忆面板可用**：用户可查看、编辑、提升记忆
- [ ] **Claude Code 互操作**：~/.claude/memory/ 格式兼容
- [ ] **记忆质量**：人工抽查 50 条，相关性 > 80%

### 8.3 Phase 3 验收（P2，可选）

- [ ] **检索性能**：1000 条记忆下延迟 < 200ms
- [ ] **检索准确性**：Recall@10 > 0.85
- [ ] **降级可用**：向量索引故障时自动降级
- [ ] **监控完善**：检索延迟、命中率纳入 Grafana

---

## 九、下一步行动

### 9.1 立即行动（本周）

1. **技术评审**：与团队评审本方案，确认优先级
2. **Phase 1 启动**：创建 `feature/context-management-p1` 分支
3. **编写测试**：先写失败测试，TDD 驱动实现

### 9.2 决策点

**需要确认的关键决策**：

1. **Phase 3 是否实施**？
   - 如果记忆条目 < 200，Phase 2 的 BM25 + 打分足够
   - 如果预期 > 500 条，建议直接上向量检索

2. **后台压缩是否启用**？
   - 如果评审重试很少（< 10% 场景），收益有限
   - 如果经常 3 轮重试，强烈建议启用

3. **与 Claude Code 互操作的优先级**？
   - 如果团队同时使用 Claude Code CLI，高优先级
   - 如果只用 Bifrost，可延后

### 9.3 里程碑

- **Week 1**：Phase 1 完成，Token 节省 60%
- **Week 2**：Phase 2 完成，跨会话记忆可用
- **Week 3**（可选）：Phase 3 完成，向量检索上线

---

## 十、参考资料

### 10.1 OpenCode 核心资源

- [OpenCode V2 Compaction Internals](https://dev.to/antonio_zhu_e726fd856cd86/opencode-v2-compaction-internals-2a5d)
- [OpenCode CONTEXT.md](https://github.com/anomalyco/opencode/blob/dev/CONTEXT.md)
- [Issue #4659: Inception Messages](https://github.com/anomalyco/opencode/issues/4659)
- [opencode-working-memory](https://github.com/sdwolf4103/opencode-working-memory)
- [magic-context](https://github.com/cortexkit/magic-context)
- [opencode-plugin-preload-skills](https://github.com/juhas96/opencode-plugin-preload-skills)

### 10.2 Aider 算法参考

- [Aider repomap.py](https://github.com/paul-gauthier/aider/blob/main/aider/repomap.py)（Apache-2.0）
- Personalized PageRank 论文：Page et al. 1998

### 10.3 open-design 参考

- [nexu-io/open-design](https://github.com/nexu-io/open-design)（Apache-2.0）
- Skills 注入机制：`apps/daemon/src/prompts/system.ts`
- UI 布局实现：`apps/web/components/split-layout.tsx`

---

## 附录 A：关键代码示例

### A.1 Inception Messages 完整实现

```typescript
// packages/context/inception/data-integrity.md
/**
 * [IMMUTABLE] 数据可信铁律
 * 
 * 以下规则在任何情况下都不可违反：
 * 
 * 1. 事实绑定强约束
 *    - 所有数值必须用 `data-fact="<fact_id>"` 绑定
 *    - 未绑定数字直接阻断发布
 *    - 豁免需明确 `data-num-reason` 枚举
 * 
 * 2. 语义层唯一源
 *    - 只能引用 metrics.yml 白名单指标
 *    - 禁止自造指标名称
 *    - 口径定义以 metrics.yml 为准
 * 
 * 3. 溯源完整性
 *    - 每个事实必须包含 definition_ref
 *    - 每个事实必须包含 sql_hash
 *    - 每个事实必须包含 row_count
 * 
 * 4. 六道 Gate 不可旁路
 *    - 结构校验 / 事实绑定 / 口径权限 / 数据断言 / 误导编码 / 呈现评审
 *    - 任一 Gate 失败即阻断
 *    - must_fix 未清零不得发布
 */

// packages/context/src/assemble.ts
import { INCEPTION_MESSAGES } from './inception.js';

export async function assemblePrompt(opts: AssembleOptions): Promise<Message[]> {
  const messages: Message[] = [];
  
  // 1. Inception Messages（永久保留）
  messages.push({
    role: 'system',
    content: INCEPTION_MESSAGES.immutable.join('\n\n---\n\n'),
    metadata: { type: 'inception', priority: 'immutable' },
  });
  
  messages.push({
    role: 'system',
    content: INCEPTION_MESSAGES.critical.join('\n\n---\n\n'),
    metadata: { type: 'inception', priority: 'critical' },
  });
  
  // 2. 动态内容（可压缩）
  // ...
  
  return messages;
}
```

### A.2 Skills PageRank 完整实现

```typescript
// packages/skills-index/src/pagerank.ts
export function personalizedPageRank(
  graph: Map<string, Set<string>>,
  personalization: Map<string, number>,
  dampingFactor: number = 0.85,
  maxIterations: number = 100,
  tolerance: number = 1e-6
): Map<string, number> {
  const nodes = Array.from(graph.keys());
  const n = nodes.length;
  
  // 初始化
  let ranks = new Map(nodes.map(node => [node, 1.0 / n]));
  
  for (let iter = 0; iter < maxIterations; iter++) {
    const newRanks = new Map<string, number>();
    let maxDelta = 0;
    
    for (const node of nodes) {
      // 计算入流
      let inflow = 0;
      for (const [src, outgoing] of graph.entries()) {
        if (outgoing.has(node)) {
          inflow += ranks.get(src)! / outgoing.size;
        }
      }
      
      // PageRank 公式
      const personalWeight = personalization.get(node) || (1.0 / n);
      const newRank = (1 - dampingFactor) * personalWeight + dampingFactor * inflow;
      
      newRanks.set(node, newRank);
      maxDelta = Math.max(maxDelta, Math.abs(newRank - ranks.get(node)!));
    }
    
    ranks = newRanks;
    
    // 收敛判断
    if (maxDelta < tolerance) break;
  }
  
  return ranks;
}
```

### A.3 记忆检索完整实现

```typescript
// packages/memory/src/retrieval.ts
export class MemoryRetriever {
  private bm25Index: BM25Index;
  private vectorStore?: VectorStore;  // Phase 3 可选
  
  async retrieve(
    context: RetrievalContext,
    options: RetrievalOptions = {}
  ): Promise<MemoryEntry[]> {
    const {
      maxCount = 20,
      minRelevanceScore = 0.5,
      useVectorSearch = false,
    } = options;
    
    // 1. 加载候选记忆
    const candidates = await this.loadCandidates(context);
    
    // 2. 相关性打分
    const scored = candidates.map(entry => ({
      entry,
      score: this.scoreRelevance(entry, context),
    }));
    
    // 3. 过滤 + 排序
    const filtered = scored
      .filter(s => s.score >= minRelevanceScore)
      .sort((a, b) => b.score - a.score);
    
    // 4. Phase 3: 混合检索（可选）
    if (useVectorSearch && this.vectorStore) {
      const vectorResults = await this.vectorStore.search(
        context.query,
        { topK: maxCount }
      );
      
      // RRF 重排序
      return this.reciprocalRankFusion([
        filtered.map(s => s.entry),
        vectorResults,
      ]).slice(0, maxCount);
    }
    
    // 4. 返回 Top-K
    return filtered.slice(0, maxCount).map(s => s.entry);
  }
  
  private scoreRelevance(mem: MemoryEntry, context: RetrievalContext): number {
    let score = 0;
    
    // Metrics 交集
    const metricsOverlap = intersection(
      mem.scope.metrics || [],
      context.planMetrics
    ).length;
    score += metricsOverlap * 2.0;
    
    // Dims 交集
    for (const [key, values] of Object.entries(mem.scope.dims || {})) {
      if (context.planDims[key]?.some(v => values.includes(v))) {
        score += 1.0;
      }
    }
    
    // Kind 优先级
    const kindBonus: Record<MemoryKind, number> = {
      business_exception: 2.0,
      definition_dispute: 1.5,
      rejected_proposal: 1.0,
      review_finding: 1.0,
      preference: 0.5,
    };
    score += kindBonus[mem.kind] || 0;
    
    // 时间衰减
    const ageMonths = (Date.now() - new Date(mem.created_at).getTime()) 
      / (30 * 24 * 3600 * 1000);
    score -= Math.min(ageMonths * 0.1, 3);
    
    return Math.max(0, score);
  }
  
  private reciprocalRankFusion(
    rankedLists: MemoryEntry[][],
    k: number = 60
  ): MemoryEntry[] {
    const scores = new Map<string, number>();
    
    for (const list of rankedLists) {
      list.forEach((entry, rank) => {
        const rrf = 1.0 / (k + rank + 1);
        scores.set(entry.mem_id, (scores.get(entry.mem_id) || 0) + rrf);
      });
    }
    
    return Array.from(scores.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([memId]) => 
        rankedLists.flat().find(e => e.mem_id === memId)!
      );
  }
}
```

---

## 附录 B：配置示例

### B.1 环境变量配置

```bash
# .env.example

# ===== Context Management =====
# Inception Messages（默认开启）
ENABLE_INCEPTION=true

# Skills Compression（Phase 1）
ENABLE_SKILLS_COMPRESSION=true
MAX_SKILL_TOKENS=3000

# Smart Memory Retrieval（Phase 2）
ENABLE_SMART_MEMORY=true
MAX_MEMORY_TOKENS=1000
MEMORY_MIN_RELEVANCE_SCORE=0.5
MEMORY_MAX_COUNT=20

# Vector Retrieval（Phase 3，可选）
ENABLE_VECTOR_RETRIEVAL=false
VECTOR_DB_TYPE=lancedb  # lancedb | milvus
VECTOR_DB_PATH=~/.bifrost/vectors

# Background Compression（可选）
ENABLE_BG_COMPRESSION=false
BG_COMPRESSION_MODEL=claude-3-5-haiku-20241022
BG_COMPRESSION_TIMEOUT_MS=5000

# ===== Debugging =====
LOG_CONTEXT_ASSEMBLY=false
LOG_MEMORY_RETRIEVAL=false
LOG_SKILLS_COMPRESSION=false
```

### B.2 CI 配置

```yaml
# .github/workflows/test-context.yml
name: Context Management Tests

on: [push, pull_request]

jobs:
  test-context:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '22'
      
      - name: Install dependencies
        run: corepack pnpm install
      
      - name: Test Inception Messages
        run: corepack pnpm --filter @bifrost/context test -- inception
      
      - name: Test Skills Compression
        run: corepack pnpm --filter @bifrost/skills-index test -- compress
      
      - name: Test Memory Retrieval
        run: corepack pnpm --filter @bifrost/memory test -- retrieval
      
      - name: Verify Token Budget
        run: corepack pnpm verify:token-budget
```

---

**方案完成！** 🎉

接下来请确认：
1. Phase 优先级是否认可（P0/P1/P2）？
2. 是否需要调整 Token 预算（3K skills / 1K memory）？
3. 是否需要补充其他细节？

