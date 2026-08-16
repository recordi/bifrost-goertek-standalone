# BIFROST OMP-03 真实编排链路测试

你正在执行一次只读集成测试，不是修改任务。

## 目标

对黄金事件 `EVT-OMP-03-GOLDEN-0001` 跑通以下真实代理链：

`orchestrator → production-specialist / quality-specialist / supply-specialist → contract-reviewer`

使用项目中的 `.omp/agents/*.md`、`.omp/skills/*-readonly/` 和现有测试夹具。专业代理必须调用各自已有 Skill，不得重新发明 OEE、良率或供应链公式。

## 硬边界

1. 只读：不得写入 `apps/`、`packages/`、`.omp/skills/`、`vendor/`、`test-inputs/`，不得修改 UI、载荷、Excel 或正式合同。
2. 不得创建真实飞书任务、确认记录或外部系统记录。
3. 不得把六个业务角色当作六个工程代理；六角色只用于结果投影。
4. 所有专业结论必须保留 `event_id/task_id/agent_id/evidence_refs/data_gaps/needs_human_confirmation/actor_can_execute`。
5. 高风险动作只能生成待确认草稿；没有 SPC 测量点和规格限时不得计算 Cpk；供应关联无证据时不得编造缺料。

## 执行步骤

1. 读取并确认 `.omp/integration/OMP-03_GOLDEN_EVENT_INPUT.json` 和项目规则；不要因为找不到真实企业事件而自行编造事件。
2. 编排三个专业子任务，分别调用既有只读 Skill。Skill 是 Python-only 时，按对应工程代理文件中写明的模块函数入口，用 `D:\\anaconda3\\envs\\langchain\\python.exe` 从 Skill 根目录调用；这属于已批准的 Skill 调用方式，不是重新发明业务逻辑。
3. 将三个结果交给 `contract-reviewer`，检查统一任务合同、证据引用和人工确认门禁。
4. 在输出前必须实际运行一次：

   `D:\\anaconda3\\envs\\langchain\\python.exe .omp\\integration\\orchestration_test_entry.py`

   然后读取 `.omp/integration/orchestration_test_results.json`。这是本项目唯一批准的整机 Skill 调用适配器。不得调用不存在的 `query_overview_snapshot`，不得用静态数值代替脚本输出。
5. 输出中必须带 `adapter_artifact_sha256`（对上述 JSON 文件计算 SHA-256）、`adapter_overall_status`、`adapter_checks` 和 `adapter_task_count`，且这些值必须直接来自回读文件。
6. 输出一份 JSON 到标准输出，必须是单个合法 JSON 对象，不要输出 Markdown 围栏。

JSON 至少包含：

```json
{
  "run_type": "omp_real_orchestration",
  "event_id": "EVT-OMP-03-GOLDEN-0001",
  "status": "completed|needs_confirmation|blocked|failed",
  "agent_chain": [],
  "tasks": [],
  "contract_review": {},
  "role_projections": {},
  "evidence_refs": [],
  "data_gaps": [],
  "human_confirmation_required": true,
  "source_write_performed": false,
  "actor_can_execute": false,
  "errors": []
}
```

## 强制反伪造断言

- `adapter_overall_status` 必须为 `PASS`；否则输出 `blocked`。
- `adapter_task_count` 必须为 3。
- `adapter_checks` 必须逐字包含 `golden_event`、`supply_insufficient`、`high_risk_confirmation`、`spc_missing`、`stop_defect_variation`、`readonly_boundary`，且每项为 `PASS`。
- 生产任务必须来自适配器 JSON，不得凭空改写 OEE；质量任务在 `spc_missing` 场景中不得出现 Cpk/SPC 越界指标；供应不足场景必须保留 `warning + blocked data_gap`。
- 每个 EvidenceRef 必须来自适配器输出；不接受 `eref:line-s03-...` 这类未由 Skill 产生的引用。
- `human_confirmation_required` 必须与适配器事件摘要一致；`source_write_performed=false`、`actor_can_execute=false` 必须保持不变。

如果无法完成上述实际执行和回读，请输出 `blocked` 和明确错误，不要用静态文本冒充成功。
