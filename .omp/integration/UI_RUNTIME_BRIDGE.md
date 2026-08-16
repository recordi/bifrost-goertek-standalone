# UI 运行包桥接说明

固定构建命令：

```powershell
cd D:\Codex\智能体\workspaces\bifrost-goertek
D:\anaconda3\envs\langchain\python.exe .omp\integration\prepare_ui_runtime.py
```

输出目录：`output/bifrost-ui-runtime/`

这个目录包含 UI 基线 v3.2.1，以及 UI 当前固定读取的：

- `artifacts/BIFROST_OVERVIEW_PAYLOAD_v2.1.json`
- `artifacts/BIFROST_EVENT_PAYLOAD_v1.4.json`

当前桥接模式是 `approved_payload_smoke_test`：验证 UI 与载荷合同、页面导航和事件详情可以运行，但不把 OMP 适配器结果冒充成 Overview/Event 企业载荷。`omp_adapter_connected=false` 是刻意保留的事实标记。
