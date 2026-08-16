# OMP-04 受限适配器调用提示

这是 BIFROST 的只读整机测试。你只能消费受限适配器的标准输出。

适配器固定入口：

```text
D:\anaconda3\envs\langchain\python.exe .omp\integration\run_bifrost_adapter.py
```

硬规则：

1. 不传任何参数。
2. 不执行其他 Python、Bash、PowerShell、Node 命令。
3. 不直接调用 Skill 函数，不访问外部网络，不写项目文件。
4. 适配器返回 `status=blocked` 时，立即输出阻断原因，不得猜测或补造结果。
5. 适配器返回 `status=PASS` 后，才允许基于输出完成合同审查和六角色投影。
6. 不新增业务数值、EvidenceRef、Cpk、MTBF、MTTR、任务或确认记录。

最终输出必须明确：

- 适配器状态
- 事件状态
- 三个 TaskID 与 AgentID
- 合同审查结果
- EvidenceRef 是否来自适配器
- 人工确认门禁
- `source_write_performed` 和 `actor_can_execute`
