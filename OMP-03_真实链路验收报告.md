# OMP-03 真实 OMP 链路验收报告

## 验收结论

本轮完成了 **Skill 适配器 → OMP 只读合同审查 → 六角色投影** 的真实链路。

最终 OMP 输出：`status=PASS`、`contract_review.status=PASS`、3 个任务、17 个 EvidenceRef，`source_write_performed=false`、`actor_can_execute=false`。

需要准确区分：三个专业分析结果由已验收的本地确定性 Skill 适配器产生，OMP 本轮真实执行的是读取结果、编排、合同审查和角色投影；尚未让 OMP 模型自主通过工具调用三个 Python Skill。后者因非交互工具审批和 Skill Python-only 入口仍需专门的受限适配器，不能用模型自然语言冒充完成。

## 真实执行链

```text
本地 Skill 适配器
  -> orchestration_test_results.json
  -> custom-grok / OMP 只读读取
  -> 合同审查
  -> 生产、质量、设备、工艺、供应链、厂长六角色投影
```

## 真实性检查

- OMP 输出中的 EvidenceRef 集合是适配器输出集合的子集，没有新增引用。
- OMP 没有使用此前发现的虚构 `query_overview_snapshot` 结果。
- OMP 没有生成 Cpk、MTBF 或 MTTR；缺失数据仍保留为 data_gap。
- 高风险生产动作仍要求人工确认。
- 供应证据不足场景仍保留 Skill 的 warning/blocked data_gap 语义。
- 输入文件和业务源数据未写入，代理不可直接执行。

## 过程中发现并拒绝的错误

一次 OMP 自主编排尝试输出了不存在的 Skill 函数、虚构 EvidenceRef、错误 OEE/Cpk/MTBF 数值，已被拒绝；随后通过“适配器真实结果唯一事实源 + 只读 OMP 审查”纠正。这证明监督验收是必要的。

## 复现材料

- 黄金事件清单：`.omp/integration/OMP-03_GOLDEN_EVENT_INPUT.json`
- Skill 编排结果：`.omp/integration/orchestration_test_results.json`
- OMP 审查提示：`.omp/integration/OMP-03_REAL_REVIEW_PROMPT.md`
- 本地编排脚本：`.omp/integration/orchestration_test_entry.py`

## 下一步

不要开启全局 `yolo` 工具权限。应编写一个受限的 `run_bifrost_adapter` 工具，只允许执行固定的本地适配器命令、读取固定结果文件，并由 OMP 读取该工具结果；再补跑一次完整的模型自主编排测试。
