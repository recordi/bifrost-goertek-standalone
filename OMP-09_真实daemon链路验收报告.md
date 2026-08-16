# OMP-09 真实 daemon 链路验收报告

## 结论

同学项目 daemon 的真实只读桥接已经通过输入侧和数据侧验证，当前阻塞在 daemon 自身的模型服务配置，状态为 **PARTIAL PASS / BLOCKED_EXTERNAL**。

## 已实际跑通

1. daemon 在 `127.0.0.1:8787` 健康运行。
2. runner 在 `127.0.0.1:8788` 健康运行。
3. BIFROST 只读桥接向公开 Run API 提交成功并取得真实 `runId`。
4. 真实岗位映射：`厂长 -> plant_manager`。
5. 真实测试项目：`demo_goertek_m6`。
6. 真实脱敏 fixture 数据集已注册，生成了 profile。
7. 项目级 `knowledge/metrics.yml` 已在隔离测试项目补齐。
8. daemon 已进入 `plan` 阶段，说明项目、角色、数据集、profile、指标口径和 runner 均已通过。

## 最终阻塞

真实 Run：`run_01KZYZ60X4PDS0P03CGD55GVCC`

```text
stage: plan
status: failed
code: E_STAGE_PLAN_FAILED
message: Plan stage failed after 3 attempts: Connection error.
```

原因是 daemon 需要自己的 OpenAI-compatible 模型配置：

```text
MODEL_API_BASE_URL
MODEL_API_KEY
MODEL_NAME
```

当前没有把任何真实模型密钥写入项目，也没有把 OMP 的 custom-grok 密钥暴露给 daemon；这是刻意保持的安全边界。OMP 的 `custom-grok/grok-4.6` 目前是命令行模型提供方，不等于一个可直接填入 daemon 的 HTTP API 地址。

## 兼容性结论

- 桥接协议兼容：PASS
- 角色映射兼容：部分通过；当前同学项目只提供 `executive`、`plant_manager`、`supply_chain_lead`，质量/设备/工艺/线长没有真实对应岗位，禁止伪造映射。
- 数据集与 profile 链路：PASS
- BIFROST 官方载荷是否被替换：未替换
- BIFROST Skill 是否被改写：未改写
- UI 是否被 daemon 接管：未接管
- 多智能体最终推理：BLOCKED_EXTERNAL（缺 daemon 模型服务）

## 下一步

只有在用户明确提供一个可用的 OpenAI-compatible endpoint（或允许把 OMP 封装成受限本地 HTTP adapter）后，才继续真实 plan/query/fact 全链路。否则保持当前安全状态：BIFROST 固定适配器正常运行，daemon 只作为已验证但暂未完成模型推理的可选 worker。
