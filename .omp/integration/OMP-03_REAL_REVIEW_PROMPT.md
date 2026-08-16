# BIFROST OMP-03 真实结果编排与合同审查

这是一个只读合同审查阶段。专业 Skill 已经由本地确定性适配器执行，真实结果在随本提示附带的 `orchestration_test_results.json` 中。

你必须把附带 JSON 当作唯一事实来源，完成 `orchestrator → contract-reviewer`：

1. 读取 `overall_status`、`tasks`、`event`、`checks` 和 `role_projections`。
2. 检查三个任务是否都具备统一合同字段，且 `actor_can_execute=false`、`source_write_performed=false`。
3. 检查 `checks` 六项是否全部 PASS；供应不足必须是 warning 且 data_gap 的 value_consumption_status=blocked；SPC 缺失不能生成 Cpk/SPC 越界指标；高风险动作必须人工确认。
4. 生成一个统一事件合同和六个业务角色投影。角色是视图，不是工程代理。
5. 严禁补写任何 JSON 数值、EvidenceRef、MTBF/MTTR、Cpk 或业务事实；只复制附带 JSON 中已有内容。

输出单个合法 JSON，不要 Markdown 围栏，字段至少包含：

`run_type,event_id,status,agent_chain,tasks,contract_review,role_projections,evidence_refs,data_gaps,human_confirmation_required,source_write_performed,actor_can_execute,errors`

其中 `contract_review.status` 只能是 `PASS` 或 `FAIL`；若任一断言无法从附带 JSON 验证，输出 `FAIL`，不要猜测。
