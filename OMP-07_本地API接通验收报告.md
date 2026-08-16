# OMP-07 本地 API 接通验收报告

## 结论

本地 UI、只读适配器和 AI API 桥接已经接通。API 现在直接调用已经验证可用的 OMP CLI，复用 OMP 的网络栈与 `custom-grok` 配置：

- OMP CLI：`D:\Codex\智能体\oh-my-pi\omp-windows-x64.exe`
- 配置文件：`C:\Users\zhr12\.omp\agent\models.yml`（与运行时配置内容一致）
- Provider：`custom-grok`
- Model：`grok-4.6`
- 密钥：仅由服务端读取环境变量，浏览器和载荷均不可见

## 已通过

1. `GET /api/health` 返回 `status=ok`。
2. `ai_provider_configured=true`、`adapter_available=true`。
3. UI 运行包继续使用已批准的 Overview/Event 载荷；两个 SHA256 未改变。
4. `?mode=adapter-test` 仍可加载动态适配器测试数据。
5. AI 请求先执行固定只读适配器；适配器不通过时不会调用模型。
6. API 响应明确标记 `readonly=true`、`source_write_performed=false`、`actor_can_execute=false`。
7. 高风险请求只允许模型生成待人工确认草稿，不开放写入动作。

## 当前阻塞

此前 Python 直连 Provider 受到网络路径影响。服务端现已改为调用 OMP CLI；你在 PowerShell 中验证 `CONNECTION_OK` 后，需重启桥接服务以加载此变更。

OMP 最小连接测试也未能在 120 秒内得到响应；因此当前阻塞是外部端点网络路径/代理或密钥状态，不是前端代码。桥接已把单次模型等待缩短为 12 秒，并会显示具体错误。修复外网代理或更新有效密钥后，重新启动服务即可复测；在此之前 UI 不会伪造 AI 回复。

## 启动命令

```powershell
cd D:\Codex\智能体\workspaces\bifrost-goertek
D:\anaconda3\envs\langchain\python.exe .omp\integration\serve_bifrost_ui.py --port 4173
```

浏览器地址：`http://127.0.0.1:4173/?mode=adapter-test`
