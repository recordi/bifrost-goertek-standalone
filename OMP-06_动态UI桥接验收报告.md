# OMP-06 动态 UI 桥接验收报告

## 结论

已完成动态桥接第一版。UI 运行包现在支持两种明确模式：

| 模式 | 访问方式 | 数据来源 | 用途 |
|---|---|---|---|
| 批准载荷模式 | `/` | 已批准 Overview v2.1 + Event v1.4 | 默认展示与回归 |
| 适配器测试模式 | `/?mode=adapter-test` | 受限适配器生成的独立测试载荷 | 验证 OMP/Skill 结果能否被 UI 消费 |

## 验收结果

8/8 检查通过：

- 默认 Overview 哈希保持批准值
- 默认 Event 哈希保持批准值
- 动态载荷标记 `runtime_mode=adapter-test`
- 动态 Event 包含 6 个业务角色切片
- 动态事件保留 `adapter_event_id=EVT-OMP-03-GOLDEN-0001`
- 动态载荷保留只读标志
- UI 数据层存在模式切换
- UI 测试模式显示明确的“适配器测试模式”提示

动态测试 OEE 复算值来自适配器专业结果：`0.605230821`。该值只出现在测试模式，不覆盖默认事件的 `0.4591115012`。

## 运行

```powershell
cd D:\Codex\智能体\workspaces\bifrost-goertek\output\bifrost-ui-runtime
D:\anaconda3\envs\langchain\python.exe -m http.server 4173
```

浏览器地址：

- 默认：`http://localhost:4173/`
- 动态测试：`http://localhost:4173/?mode=adapter-test`

## 重要边界

这不是把 OMP 结果写回企业载荷，也不是接入真实生产数据。动态文件是独立的 `adapter-test` 载荷，默认模式不会读取它。AI 输入框仍是 UI 原有入口，尚未连接到 OMP 受限工具；下一步应单独设计“前端请求 → 受限运行 → 新测试载荷 → 页面刷新”的 API/本地服务接口。
