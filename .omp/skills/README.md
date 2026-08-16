# BIFROST OMP Skill 清单

本目录是从已授权的 BIFROST 封存包复制并适配到 OMP 的只读 Skill 层。原始压缩包保存在 `vendor/bifrost-sealed/source-packages/`，不覆盖同学仓库已有的 `skills/` 目录。

## 适配状态

| OMP Skill | 来源版本 | 输入/输出合同 | 状态 |
|---|---|---|---|
| `bifrost-semantic-consumer-readonly` | v0.1.4 | SEM 数据面 → `BIFROST_DECISION_INPUT_v0.1` | 本地已验证，未部署 |
| `bifrost-decision-readonly` | v1.0.4 | Overview/Event 载荷 → 决策查询与确认草稿 | 本地已验证，静态载荷回退 |
| `bifrost-production-diagnosis-readonly` | v0.1.2 | `BIFROST_DECISION_INPUT_v0.1` → `BIFROST_SPECIALIST_RESULT_v0.1.3` | 本地已验证，未部署 |
| `bifrost-quality-diagnosis-readonly` | v0.1.2 | `BIFROST_DECISION_INPUT_v0.1` → `BIFROST_SPECIALIST_RESULT_v0.1.3` | 本地已验证，未部署 |
| `bifrost-supply-risk-readonly` | v0.1.3 | `BIFROST_DECISION_INPUT_v0.1` → `BIFROST_SPECIALIST_RESULT_v0.1.3` | 合同已验证，未部署 |
| `bifrost-data-mapper-readonly` | v0.1.2 | xlsx/csv/json → SEM-v1.1.1 映射草稿 | 本地已验证，未部署 |

## 统一边界

- 所有 Skill 默认只读：不写回业务数据、不覆盖批准载荷、不自动执行高风险动作。
- 证据必须引用真实 `EvidenceRef`；字段缺失、口径冲突或关联歧义必须输出数据缺口并进入人工确认门控。
- 没有测量点和规格限时，不计算 SPC/Cpk；没有设备级故障事件时，不伪造 MTBF/MTTR。
- 供应链缺料默认是生产连续性风险，不得直接表述为 OEE 的直接原因。
- OMP 工程代理与 BIFROST 业务角色分离；工程代理负责适配、测试和审计，六个业务角色负责消费结果。

## 未纳入内容

批准的语义数据面、Overview/Event 载荷和企业业务数据不复制到 `.omp/skills`；它们属于受保护的运行资产或测试输入。独立 `BIFROST_SPECIALIST_RESULT` v0.1.3 合同包若不存在，必须标记为阻塞，不得自行发明合同。
