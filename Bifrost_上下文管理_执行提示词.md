# Bifrost 上下文管理改进方案执行提示词

> **目标受众**：Claude Code CLI / Claude Desktop  
> **执行模式**：分阶段 TDD 驱动实现  
> **预计时长**：Phase 1 (2-3 天) + Phase 2 (3-5 天)  

---

## 📋 执行前准备

### 1. 阅读背景材料

**必读文档**（按顺序）：
1. `docs/Bifrost_上下文管理改进方案_V1.md` — 完整技术方案（1212 行）
2. `docs/superpowers/plans/2026-08-04-bifrost-s0-foundation.md` — S0 地基实现计划
3. 记忆文件：
   - `.claude/memory/memory/bifrost_project.md` — 产品定位
   - `.claude/memory/memory/bifrost_tech_selection.md` — 技术选型
   - `.claude/memory/memory/opencode_context_study.md` — OpenCode 调研结论

### 2. 环境确认

```bash
# 确认当前目录
pwd  # 应该在 C:\Users\xuan\Desktop\桌面\比赛\歌尔

# 确认三服务健康（如果已搭建）
corepack pnpm dev  # daemon:8787, runner:8788, web:3000

# 确认 Python 环境
conda activate onetrans
python --version  # 应该是 3.12
```

### 3. 创建特性分支

```bash
git checkout -b feature/context-management-phase1
```

---

## 🎯 Phase 1: 快速见效（P0，预计 2-3 天）

### 目标

- Token 节省 60%（22K → 8K）
- Inception Messages 固化
- Skills PageRank 压缩
- 记忆检索优化

### Task 1: Inception Messages 固化

#### Step 1.1: 创建 Inception 文件结构

```bash
# 创建目录
mkdir -p packages/context/inception

# 创建四个核心文件
touch packages/context/inception/data-integrity.md
touch packages/context/inception/role-boundaries.md
touch packages/context/inception/review-standards.md
touch packages/context/inception/design-principles.md
```

**提示词**：
```
请根据改进方案 §3.1 的内容，将现有的 `apps/daemon/src/prompts/bifrost-core.md` 拆分为四个 inception 文件：

1. data-integrity.md — 数据可信铁律（IMMUTABLE）
   - 事实绑定强约束
   - 语义层唯一源
   - 溯源完整性
   - 六道 Gate 不可旁路

2. role-boundaries.md — 岗位权限边界（CRITICAL）
   - 厂长可见范围
   - 供应链负责人可见范围
   - 经营层脱敏规则

3. review-standards.md — 评审质量标准（PRESERVED）
   - must_fix 阻断规则
   - 视觉截图双验证
   - repair target 路由规则

4. design-principles.md — 设计美学原则（PRESERVED）
   - 安静、专业、适合重复扫描
   - 禁止列表（紫色渐变、slop emoji 等）
   - 圆角、图标规范

每个文件使用 Markdown 格式，清晰的段落结构，中文输出。
```

#### Step 1.2: 实现 Inception 加载器

**提示词**：
```
请创建 `packages/context/src/inception.ts`，实现以下功能：

1. 导出 INCEPTION_MESSAGES 对象：
   - immutable: string[] — 读取 data-integrity.md
   - critical: string[] — 读取 role-boundaries.md
   - preserved: string[] — 读取 review-standards.md + design-principles.md

2. 提供 loadInceptionMessages() 函数，返回格式化的 inception 内容

3. 参考改进方案附录 A.1 的代码示例

要求：
- 使用 TypeScript
- 使用 fs.readFileSync 同步读取
- 路径用 path.resolve(__dirname, '../inception/...')
- 错误处理：文件缺失时抛出 Error
```

#### Step 1.3: 修改 Prompt 组装器

**提示词**：
```
请修改 `apps/daemon/src/prompts/assemble.ts` 的 assemblePrompt() 函数：

1. 在第一个位置注入 inception messages：
   ```ts
   sections.push({
     type: 'inception',
     priority: 'immutable',
     content: INCEPTION_MESSAGES.immutable.join('\n\n---\n\n'),
   });
   ```

2. 在现有的"平台身份与全局纪律"之前插入

3. 保持其他段落顺序不变

4. 参考改进方案 §3.1 的实现示例
```

#### Step 1.4: 编写测试

**提示词**：
```
请创建 `packages/context/tests/inception.test.ts`，编写以下测试：

1. test('加载所有 inception 文件')
   - 验证 INCEPTION_MESSAGES.immutable 不为空
   - 验证包含"事实绑定强约束"关键词

2. test('inception 在任何场景下都存在')
   - 调用 assemblePrompt() 多次，不同 node 类型
   - 验证返回的 prompt 都包含"数据可信铁律"

3. test('文件缺失时抛出错误')
   - Mock fs.readFileSync 返回错误
   - 验证抛出清晰的错误信息

使用 Vitest 框架。
```

#### Step 1.5: 验收

```bash
# 运行测试
corepack pnpm --filter @bifrost/context test

# 验证 inception 内容
corepack pnpm --filter @bifrost/daemon build
node -e "const {assemblePrompt} = require('./apps/daemon/dist/prompts/assemble.js'); console.log(assemblePrompt({node:'insight'}))"

# 确认包含"数据可信铁律"
```

---

### Task 2: Skills PageRank 压缩

#### Step 2.1: 创建 Skills Index 包

```bash
# 创建目录结构
mkdir -p packages/skills-index/src
mkdir -p packages/skills-index/tests

touch packages/skills-index/package.json
touch packages/skills-index/tsconfig.json
```

**提示词**：
```
请创建 packages/skills-index/ 包的基础配置：

1. package.json：
   - name: @bifrost/skills-index
   - dependencies: typescript, vitest
   - scripts: test, build

2. tsconfig.json：
   - extends: ../../tsconfig.base.json
   - include: ["src/**/*"]
   - outDir: dist

参考 packages/contracts/ 的配置结构。
```

#### Step 2.2: 实现 PageRank 算法

**提示词**：
```
请根据改进方案附录 A.2 的完整代码，实现 `packages/skills-index/src/pagerank.ts`：

1. personalizedPageRank() 函数
   - 输入：graph（依赖图）、personalization（种子权重）
   - 输出：Map<string, number>（每个 skill 的排名分数）
   - 算法：迭代收敛，damping factor = 0.85

2. 关键参数：
   - maxIterations: 100
   - tolerance: 1e-6（收敛判断）

3. 使用 TypeScript，完整类型标注

4. 参考 Aider repomap.py 的逻辑（已在方案中翻译为 TS）
```

#### Step 2.3: 实现 Skills 压缩器

**提示词**：
```
请实现 `packages/skills-index/src/compress.ts`，核心函数 compressSkills()：

输入：
- allSkills: SkillNode[] — 所有 skills
- context: { triggers, mentionedSkills, node, tokenBudget: 3000 }

输出：
- SkillNode[] — 按 PageRank 排序后的 Top-K

步骤：
1. 构建依赖图（buildSkillGraph）
2. 计算个性化权重（改进方案 §3.2 的权重规则）：
   - 用户明确提到：50x
   - 标题匹配：15x
   - frontmatter triggers 匹配：12x
3. 调用 personalizedPageRank()
4. 按分数排序 + Token 预算截断

参考改进方案 §3.2 的完整实现。
```

#### Step 2.4: 修改 Skills 加载逻辑

**提示词**：
```
请修改 `apps/daemon/src/prompts/assemble.ts` 的 loadSkills() 函数：

现有逻辑：
```ts
for (const file of mdFiles) {
  if (matches) {
    matchedSkills.push(content);  // ❌ 全量
  }
}
```

修改为：
```ts
import { compressSkills } from '@bifrost/skills-index';

const allMatched = [];  // 先收集所有匹配
for (const file of mdFiles) {
  if (matches) {
    allMatched.push({ name: file, content, tokenCount: estimateTokens(content) });
  }
}

// 调用压缩器
const compressed = compressSkills(allMatched, {
  triggers: context.triggers,
  mentionedSkills: context.mentionedSkills || [],
  node: opts.node,
  tokenBudget: parseInt(process.env.MAX_SKILL_TOKENS || '3000'),
});

return compressed.map(s => s.content);
```

添加 token 估算函数（简单按 4 字符 = 1 token）。
```

#### Step 2.5: 编写测试

**提示词**：
```
请创建 `packages/skills-index/tests/compress.test.ts`：

1. test('PageRank 收敛')
   - 构造简单图：A → B, A → C, B → C
   - personalization: {A: 10, B: 1, C: 1}
   - 验证：ranks[A] > ranks[B] > ranks[C]

2. test('Token 预算截断')
   - 10 个 skills，每个 500 tokens
   - tokenBudget = 2000
   - 验证：返回 4 个 skills，总 tokens ≤ 2000

3. test('用户明确提到的 skill 权重最高')
   - mentionedSkills = ['oee-loss-tree']
   - 验证：即使其他 skill 关键词更匹配，oee-loss-tree 也排第一

使用 Vitest。
```

#### Step 2.6: 验收

```bash
# 运行测试
corepack pnpm --filter @bifrost/skills-index test

# 验证压缩效果
export MAX_SKILL_TOKENS=3000
corepack pnpm --filter @bifrost/daemon build

# 手动触发一次 prompt 组装，检查 token 数
```

---

### Task 3: 记忆检索优化

#### Step 3.1: 实现相关性打分

**提示词**：
```
请实现 `packages/memory/src/retrieval.ts`，核心函数 scoreRelevance()：

输入：
- mem: MemoryEntry
- context: { planMetrics, planDims, roleId }

输出：
- number（相关性分数）

打分规则（改进方案 §3.3 Layer 3）：
1. Metrics 交集 × 2.0
2. Dims 交集 × 1.0
3. Kind 优先级：
   - business_exception: 2.0
   - definition_dispute: 1.5
   - rejected_proposal: 1.0
   - review_finding: 1.0
   - preference: 0.5
4. 时间衰减：-0.1 per month（最多 -3）

返回：max(0, score)

参考改进方案附录 A.3 的完整实现。
```

#### Step 3.2: 实现 Top-K 检索

**提示词**：
```
请在 `packages/memory/src/retrieval.ts` 中实现 retrieveRelevantMemory()：

输入：
- context: { planMetrics, planDims, roleId, projectId }
- options: { maxCount: 20, minRelevanceScore: 0.5 }

输出：
- MemoryEntry[]（按相关性排序的 Top-K）

步骤：
1. 加载候选记忆（core + project 层）
2. 为每条记忆计算 scoreRelevance()
3. 过滤低分（< minRelevanceScore）
4. 排序 + 截断（Top-K）

参考改进方案 §3.3。
```

#### Step 3.3: 实现 Token 预算控制

**提示词**：
```
请实现 `packages/memory/src/budget.ts` 的 buildMemoryDigest()：

输入：
- entries: MemoryEntry[]（已排序）
- tokenBudget: 1000

输出：
- string（格式化的记忆摘要）

格式：
```markdown
## 项目记忆

### business_exception
- [mem_001] A02 换型非异常 [line_code=A02, shift=night]

### rejected_proposals
- [mem_002] 增加良率预警阈值到 95%
```

逻辑：
- 按 kind 分组
- 逐条添加，累加 tokens
- 超过 budget 时停止

参考改进方案 §3.3 Layer 4。
```

#### Step 3.4: 修改 Prompt 组装器

**提示词**：
```
请修改 `apps/daemon/src/prompts/assemble.ts`：

现有逻辑：
```ts
const memory = await loadProjectMemory(opts.projectId);
sections.push('## 项目记忆\n\n' + formatMemory(memory));
```

修改为：
```ts
import { retrieveRelevantMemory, buildMemoryDigest } from '@bifrost/memory';

const relevantMemory = retrieveRelevantMemory(
  {
    planMetrics: opts.payload.metrics || [],
    planDims: opts.payload.dims || {},
    roleId: opts.roleId,
    projectId: opts.projectId,
  },
  {
    maxCount: parseInt(process.env.MEMORY_MAX_COUNT || '20'),
    minRelevanceScore: parseFloat(process.env.MEMORY_MIN_RELEVANCE_SCORE || '0.5'),
  }
);

const digest = buildMemoryDigest(
  relevantMemory,
  parseInt(process.env.MAX_MEMORY_TOKENS || '1000')
);

sections.push(digest);
```
```

#### Step 3.5: 编写测试

**提示词**：
```
请创建 `packages/memory/tests/retrieval.test.ts`：

1. test('Metrics 交集高的记忆排前面')
   - mem1: metrics = ['oee', 'availability']
   - mem2: metrics = ['cost']
   - context.planMetrics = ['oee', 'performance']
   - 验证：mem1 分数 > mem2

2. test('时间衰减生效')
   - mem1: created_at = 30 天前
   - mem2: created_at = 1 天前
   - 其他条件相同
   - 验证：mem2 分数 > mem1

3. test('Token 预算不超标')
   - 10 条记忆，每条 150 tokens
   - tokenBudget = 1000
   - 验证：返回的 digest tokens ≤ 1000

使用 Vitest + fixtures。
```

#### Step 3.6: 验收

```bash
# 运行测试
corepack pnpm --filter @bifrost/memory test -- retrieval

# 配置环境变量
export MAX_MEMORY_TOKENS=1000
export MEMORY_MIN_RELEVANCE_SCORE=0.5
export MEMORY_MAX_COUNT=20

# 验证实际效果
corepack pnpm --filter @bifrost/daemon build
```

---

### Task 4: 集成测试与验收

**提示词**：
```
请创建 `apps/daemon/tests/integration/context-assembly.test.ts`：

1. test('完整 prompt 组装流程')
   - 调用 assemblePrompt() 完整流程
   - 验证包含 inception messages
   - 验证 skills 数量 ≤ 配置的上限
   - 验证记忆摘要不为空
   - 验证总 tokens < 10K（相比优化前的 22K）

2. test('Token 预算配置生效')
   - 设置 MAX_SKILL_TOKENS=2000, MAX_MEMORY_TOKENS=500
   - 验证实际 tokens 符合预算

3. test('零功能回归')
   - 运行现有的所有 daemon 测试
   - 验证全部通过

使用 Vitest。
```

**验收清单**：

```bash
# 1. 所有单元测试通过
corepack pnpm test

# 2. Token 节省达标
# 手动检查：assemblePrompt() 输出从 ~22K 降至 ~8K

# 3. CI 通过
git add .
git commit -m "feat(context): phase 1 - inception, skills compression, memory retrieval"
git push origin feature/context-management-phase1

# 4. 创建 PR
gh pr create --title "Context Management Phase 1" --body "参考 Bifrost_上下文管理改进方案_V1.md"
```

---

## 🎯 Phase 2: 跨会话记忆强化（P1，预计 3-5 天）

### 目标

- 业务异常、口径争议自动记住
- 记忆面板可视化管理
- 与 Claude Code 互操作

### Task 5: Core Memory 层实现

**提示词**：
```
请实现 `packages/memory/src/core-store.ts`：

1. 数据结构：MemoryEntry（已有）
   - 新增 layer: 'core' 选项
   - 新增 confirmed_by: string（必填）

2. 存储位置：~/.bifrost/memory/core.jsonl

3. 核心方法：
   - loadCoreMemory(): MemoryEntry[]
   - saveCoreMemory(entry: MemoryEntry): void
   - promoteToCoreMemory(projectMemId: string, confirmedBy: string): void

4. 升级规则：
   - 只有 project 层记忆可升级到 core
   - 必须人工确认（confirmed_by 不为空）
   - 升级后 project 层保留原记录，标记 promoted_to_core: true

参考改进方案 §3.3 Layer 1。
```

### Task 6: 自动写入规则

**提示词**：
```
请在 `apps/daemon/src/orchestrator/` 各节点中添加自动写入逻辑：

1. review-node.ts：
   - 评审发现的 must_fix 自动写入 project 层
   - kind = 'review_finding'
   - scope 从 finding.target 提取

2. governance-node.ts：
   - 检测到的业务异常自动写入 project 层
   - kind = 'business_exception'
   - scope 从异常上下文提取

3. insight-node.ts：
   - 检测到的口径争议自动写入 project 层
   - kind = 'definition_dispute'
   - scope.metrics 从争议指标提取

示例：
```ts
import { writeMemory } from '@bifrost/memory';

if (finding.severity === 'must_fix') {
  await writeMemory({
    layer: 'project',
    kind: 'review_finding',
    scope: { project_id: opts.projectId, metrics: extractMetrics(finding) },
    text: finding.description,
  });
}
```
```

### Task 7: 记忆管理 UI

**提示词**：
```
请在 Next.js 工作台添加记忆面板：

1. 创建 `apps/web/components/memory-panel.tsx`：
   - 显示 project 层记忆列表
   - 支持编辑、删除
   - 支持"提升到组织记忆"按钮（需人工确认对话框）

2. 布局参考 open-design 的 MemoryHooksPanel：
   - 右侧抽屉式面板
   - Tab 切换：Project / Core
   - 每条记忆显示：kind 图标 + text + scope + 操作按钮

3. API 路由：
   - GET /api/memory/project/:projectId
   - PUT /api/memory/project/:memId
   - DELETE /api/memory/project/:memId
   - POST /api/memory/promote （升级到 core）

参考改进方案 §4.2 Phase 2。
```

### Task 8: Claude Code 互操作

**提示词**：
```
请实现 `packages/memory/src/claude-compat.ts`：

1. 支持读取 ~/.claude/memory/*.md 格式：
   ```markdown
   # Project: Bifrost Dashboard
   
   ## Core Architecture
   - Multi-agent system with Aily integration
   
   ## Key Decisions
   - 2026-08-07: Rejected open-design generation engine
   ```

2. 转换逻辑：
   - Markdown 段落 → MemoryEntry
   - ## 标题 → kind（architecture/decisions/preferences）
   - 列表项 → text

3. 双向同步：
   - Bifrost 写入时同步到 ~/.claude/memory/
   - 定期扫描 ~/.claude/memory/ 更新（可选）

参考改进方案 §3.3 与 Claude Code 互操作。
```

### Task 9: Phase 2 验收

```bash
# 1. 单元测试
corepack pnpm test

# 2. 手动测试记忆面板
corepack pnpm dev
# 访问 http://localhost:3000，打开记忆面板
# 创建、编辑、提升记忆

# 3. 验证自动写入
# 触发一次评审重试，检查 project 记忆是否自动写入

# 4. 验证 Claude Code 互操作
ls ~/.claude/memory/
cat ~/.claude/memory/bifrost.md

# 5. 提交
git add .
git commit -m "feat(context): phase 2 - cross-session memory"
```

---

## 🔧 配置与调优

### 环境变量

创建 `.env.local`：

```bash
# ===== Context Management =====
ENABLE_INCEPTION=true
ENABLE_SKILLS_COMPRESSION=true
ENABLE_SMART_MEMORY=true

MAX_SKILL_TOKENS=3000
MAX_MEMORY_TOKENS=1000
MEMORY_MIN_RELEVANCE_SCORE=0.5
MEMORY_MAX_COUNT=20

# ===== Debugging =====
LOG_CONTEXT_ASSEMBLY=false
LOG_MEMORY_RETRIEVAL=false
LOG_SKILLS_COMPRESSION=false
```

### 回滚开关

如果出现问题，可以临时关闭：

```bash
# 关闭 Skills 压缩
export ENABLE_SKILLS_COMPRESSION=false

# 增加预算（紧急情况）
export MAX_SKILL_TOKENS=15000
```

---

## 📊 监控指标

实施后应监控的指标：

1. **Token 使用量**：
   - 单次 prompt 的 input tokens
   - 目标：< 10K（优化前 22K）

2. **Skills 覆盖率**：
   - 压缩后的 skills 是否覆盖用户诉求
   - 目标：用户满意度 > 90%

3. **记忆召回率**：
   - 相关记忆是否被正确检索
   - 目标：Recall@20 > 80%

4. **评审问题重复率**：
   - 相同问题在下次运行中是否规避
   - 目标：重复率 < 10%

---

## 🚨 常见问题与解决

### Q1: Skills 压缩后遗漏关键 skill

**症状**：用户抱怨某个必需的 skill 没有被注入

**解决**：
1. 检查 skill 的 frontmatter triggers 是否匹配用户诉求
2. 增加 MAX_SKILL_TOKENS 预算（临时）
3. 让用户明确提到 skill 名称（会获得 50x 权重）

### Q2: 记忆相关性打分不准

**症状**：无关记忆排在前面，相关记忆被过滤

**解决**：
1. 调整权重参数（metrics × 2.0, dims × 1.0）
2. 降低 MEMORY_MIN_RELEVANCE_SCORE（0.5 → 0.3）
3. Phase 3 引入向量检索

### Q3: Token 节省不达标

**症状**：实际 tokens 仍然很高

**解决**：
1. 检查 MAX_SKILL_TOKENS 和 MAX_MEMORY_TOKENS 配置
2. 检查是否有其他未压缩的大段内容
3. 使用 LOG_CONTEXT_ASSEMBLY=true 调试

---

## ✅ 最终验收标准

### Phase 1（P0）

- [ ] Token 节省 ≥ 60%（22K → 8K）
- [ ] Inception messages 在所有场景下都存在
- [ ] Skills 压缩后 token 不超过 3K
- [ ] 记忆检索相关性 > 80%
- [ ] 所有单元测试通过
- [ ] 零功能回归

### Phase 2（P1）

- [ ] 评审问题自动写入 project 记忆
- [ ] 记忆面板可用且操作直观
- [ ] 可提升记忆到 core 层
- [ ] 与 Claude Code 互操作验证通过
- [ ] 业务异常在下次运行中自动规避

---

## 📚 参考资料

### 核心文档

- [Bifrost_上下文管理改进方案_V1.md](../docs/Bifrost_上下文管理改进方案_V1.md) — 完整技术方案
- [OpenCode 调研结论](../.claude/memory/memory/opencode_context_study.md)
- [Bifrost 技术选型](../.claude/memory/memory/bifrost_tech_selection.md)

### 外部参考

- [OpenCode V2 Compaction Internals](https://dev.to/antonio_zhu_e726fd856cd86/opencode-v2-compaction-internals-2a5d)
- [Aider repomap.py](https://github.com/paul-gauthier/aider/blob/main/aider/repomap.py)
- [opencode-working-memory](https://github.com/sdwolf4103/opencode-working-memory)

---

**执行愉快！如遇阻塞，随时查阅改进方案或询问。** 🚀
