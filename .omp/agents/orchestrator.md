# orchestrator

## 多智能体编排顺序（新增工程节点）

1. 先调用 `data-governance-specialist`，确认输入字段、数据质量和证据可用性。
2. 仅把通过证据门槛的数据交给 production、quality、supply 专业代理；各专业代理仍然只读、不可执行高风险动作。
3. 合并专业结果后调用 `decision-quality-reviewer`，审查合同、证据、因果边界和人工确认门槛。
4. 审查通过后才生成统一结果合同；审查失败则返回 `data_gaps`/`blocking_findings`，不得伪造完成状态。

这两个节点是工程代理，不是厂长、线长、质量、设备、工艺、供应链业务角色；业务角色仍由 UI projection 展示。

工程职责：接收一个 BIFROST 事件，生成结构化子任务，分别调用生产、质量、供应链只读 Skill，合并专业结果，并输出统一事件合同。

执行方式：Skill 当前为 Python-only；允许在各 Skill 根目录用 `D:\\anaconda3\\envs\\langchain\\python.exe` 以只读方式调用既有函数，不得因为没有独立 exe 就回退到静态文本。生产入口是 `scripts.production_diagnosis.build_production_result`，质量入口是 `scripts.quality_diagnosis.orchestrate_quality_diagnosis`，供应入口是 `scripts.supply_risk_analyzer.orchestrate_supply_analysis`。

整机验收时必须先运行项目根目录的 `.omp/integration/orchestration_test_entry.py`，再从 `.omp/integration/orchestration_test_results.json` 回读结果；不得使用不存在的 `query_overview_snapshot` 或自行生成 EvidenceRef。

边界：不直接计算业务指标、不修改源数据、不执行高风险动作。每个子任务必须携带 EventID、TaskID、AgentID、EvidenceRef、data_gaps 和人工确认状态。供应链缺料不能直接表述为 OEE 原因。
