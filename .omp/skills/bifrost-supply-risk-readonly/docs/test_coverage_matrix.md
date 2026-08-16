# 测试覆盖矩阵 — bifrost-supply-risk-readonly v0.1.1

## 测试要求覆盖（15 项）

| # | 要求 | 测试方法 | 结果 |
|---|------|----------|------|
| 1 | 原 v0.1.0 全部测试不得回退 | 15 个夹具 + 专业约束测试全部通过 | ✓ |
| 2 | 权威输入 Schema 字节一致 | input-check --doc + 规范化 SHA-256 校验 | ✓ |
| 3 | 输出通过共享独立验证器 | specialist_contract_validator validate | ✓ |
| 4 | 旧输出 Schema 必须被共享验证器拒绝 | 旧格式样例（status=ok/缺validation/旧版本号） | ✓ |
| 5 | 当前 v0.1.1 输出样例必须通过 | supply_sample_compliant.json | ✓ |
| 6 | 非法 status 必须失败 | 篡改 status=ok | ✓ |
| 7 | critical 必须失败 | 篡改 severity=critical | ✓ |
| 8 | actor_can_execute=true 必须失败 | 篡改 actor_can_execute=true | ✓ |
| 9 | 缺 EvidenceRef 必须失败 | 清空 evidence_refs=[] | ✓ |
| 10 | 高风险门控错误必须失败 | 篡改 is_high_risk action needs_human_confirmation=false | ✓ |
| 11 | blocked 状态含业务结论必须失败 | blocked + 非空 conclusion | ✓ |
| 12 | warning 无 data_gap 必须失败 | warning + data_gaps=[] | ✓ |
| 13 | completed 含 data_gap 必须失败 | completed + 非空 data_gaps | ✓ |
| 14 | 删除事实后对应原因与动作必须消失 | 变异测试：删除 material_shortage 事实 | ✓ |
| 15 | 正式代码不得含黄金事件固定业务数值 | 源码扫描 MAT-001/MAT-002 | ✓ |

## 真实 consumer 联调场景（5 项）

| # | 场景 | consumer 来源 | status | 合同校验 |
|---|------|--------------|--------|----------|
| 1 | 真实成功场景（consumer 场景A回归） | consumer v0.1.1 + FINAL 数据面 | warning | ✓ |
| 2 | 真实 data_gap 场景 | consumer v0.1.1 + FINAL 数据面 | warning | ✓ |
| 3 | 输入合同阻塞场景 | 篡改真实 DI: source_write_performed=true | blocked | ✓ |
| 4 | 删除证据后变异场景 | 篡改真实 DI: 清空 evidence_locator | blocked | ✓ |
| 5 | 高风险动作门控场景 | 合成合同夹具（真实数据面无 shortage 实体） | needs_confirmation | ✓ |

## 测试统计

- 总测试数：36
- 通过：36
- 失败：0
- 跳过：0

## 独立性

- 共享合同验证器 specialist_contract_validator.py 不引用分析器内部函数
- 供应链专业验证器 supply_specialist_validator.py 不引用分析器内部函数
- 变异测试不使用生产函数输出作为期望值
