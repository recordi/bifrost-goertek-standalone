# OMP-08 同学 daemon 只读桥接验收报告

## 结论

桥接层已完成，当前状态为 **PASS（本地模拟链路）/ BLOCKED_EXTERNAL（真实 daemon）**。

这一步没有替换 BIFROST 的官方载荷、没有修改 Skill、没有接管 UI，也没有执行任何写入动作。BIFROST 仍是指标、证据、角色投影和决策动作的权威来源；同学项目 daemon 只作为可选分析 worker。

## 已验证内容

1. 请求只发送 daemon 公开合同字段：`brief`、`role_id`、`dataset_ids`。
2. 不发送 BIFROST 原始指标、事件载荷、factset 或 `params`。
3. 只调用 `GET /health`、`POST /api/projects/:id/runs`、`GET /api/runs/:runId`、`GET /reviews`、`GET /gates`。
4. 不调用发布、重跑、取消或任何写入决策的接口。
5. daemon 结果统一标记为 `non_authoritative=true`、`read_only=true`。
6. 未完成状态只映射为 `warning`，不会伪装成成功；连接失败映射为 `blocked`。
7. 本地模拟 HTTP daemon 全链路测试通过：请求字段、轮询、评论、门禁结果和安全边界均符合预期。

## 测试结果

```text
test_peer_daemon_bridge.py       4/4 PASS
test_peer_skill_adapters.py      5/5 PASS
test_governance_precheck.py      3/3 PASS
test_ui_peer_overlay.py          5/5 PASS
```

## 当前外部阻塞

在验收时 `127.0.0.1:8787/health` 无 daemon 进程，真实调用返回：

```json
{"status":"blocked","reason":"peer_daemon_unavailable","read_only":true}
```

这表示桥接器的失败处理正常，不表示同学 daemon 已经完成真实运行验证。

## 下一道闸门

启动同学仓库 daemon，并在其项目配置中注册一个只读测试项目与数据集 ID；随后用同一个桥接器执行一次真实 Run。只有在真实返回 `runId`、终态、reviews、gates 后，才允许把它接入适配器测试模式；正式 Overview/Event 载荷仍不得被覆盖。

## 显式测试入口

真实 daemon 启动后使用独立命令，不改变原有固定适配器：

```powershell
python .omp/integration/run_peer_daemon.py `
  --project-id bifrost-goertek `
  --role 厂长 `
  --dataset-id <已注册的数据集ID>
```

没有 daemon 时该命令应返回 `status=blocked`，而不是伪造成功；这也是当前环境的预期结果。
