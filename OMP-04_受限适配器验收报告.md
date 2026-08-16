# OMP-04 受限适配器验收报告

## 结论

受限适配器已创建并通过验收。它不是新的业务 Skill，而是 OMP 与既有只读编排脚本之间的固定安全接口。

正式运行：**PASS**。

- 状态：`PASS`
- 事件：`EVT-OMP-03-GOLDEN-0001`
- 专业任务：3 个
- 六项回归检查：全部 PASS
- `source_write_performed=false`
- `actor_can_execute=false`
- `.omp/skills`、`test-inputs`、`vendor`、`apps`、`packages` 运行前后哈希不变

## 固定入口

```powershell
cd D:\Codex\智能体\workspaces\bifrost-goertek
D:\anaconda3\envs\langchain\python.exe .omp\integration\run_bifrost_adapter.py
```

适配器不接受任何参数；传入参数时已验证返回 `EXIT_CODE=2` 和 `status=blocked`。

## 安全边界

适配器只执行固定的 `.omp/integration/orchestration_test_entry.py`，只读取固定的 `orchestration_test_results.json`，只输出经过校验的 JSON。它拒绝任意脚本路径、任意输入文件、源数据写入、业务系统写入和高风险动作执行。

## 给 OMP 的使用方式

OMP 只需要获得这个固定入口的输出，不应获得全局 `yolo` 权限，也不应自行拼接 Python、Bash、Skill 函数名或 EvidenceRef。

本轮完成的是“固定适配器 + OMP 只读审查”的安全链路；未来接入真实企业数据时，只替换受控数据源适配器，不改变合同和权限门禁。
