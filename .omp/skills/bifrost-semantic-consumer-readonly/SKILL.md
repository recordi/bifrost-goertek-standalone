---
name: bifrost-semantic-consumer-readonly
label: BIFROST语义消费者只读适配
description: "BIFROST语义数据消费者只读适配能力。验证批准的语义数据面及其MANIFEST、RELEASE_INDEX和快照哈希，仅消费decision_usable=true的可信字段，生成BIFROST_DECISION_INPUT_v0.1结构化输入。不可用字段输出data_gap，不生成业务结论，不执行或写回业务数据。"
---
# bifrost-semantic-consumer-readonly

**logical_version: 0.1.4**
**stage: 04D.4C.1_PLATFORM_READY_NOT_DEPLOYED**

## 用途

BIFROST 语义数据消费者只读适配器。从已物化的语义数据面（04C.5B 产出）安全查询可信事实，生成 `BIFROST_DECISION_INPUT_v0.1` 合同输出，供决策编排智能体消费。

本阶段**只生成可信事实输入**，不直接生成业务结论或执行动作。

## 链路

```
语义数据面ZIP
→ RELEASE_INDEX
→ semantic_data_ref
→ 只读查询
→ BIFROST_DECISION_INPUT_v0.1
→ 决策编排智能体
```

## 12 个确定性能力

| # | 能力 | 说明 |
|---|------|------|
| 1 | `verify_data_plane_package` | 验证 ZIP 完整性、必需文件存在 |
| 2 | `verify_manifest` | 验证 CONTENTS.json 中每个文件 SHA-256 |
| 3 | `load_release_index` | 加载 RELEASE_INDEX，验证快照 SHA-256 |
| 4 | `resolve_semantic_data_ref` | 根据 source_scope 解析快照和 semantic_data_ref |
| 5 | `load_semantic_snapshot` | 加载快照 JSON，验证 SHA-256 |
| 6 | `validate_consumer_role_scope` | 验证角色对实体的查询权限 |
| 7 | `execute_semantic_query` | 执行只读查询（过滤 + 投影） |
| 8 | `enforce_decision_usable_gate` | 只返回 decision_usable=true 的字段 |
| 9 | `build_structured_data_gap` | 将 null/invalid/needs_rule 转为结构化 data_gap |
| 10 | `build_decision_input_contract` | 构建 BIFROST_DECISION_INPUT_v0.1 输出 |
| 11 | `validate_decision_input_contract` | 验证输出合同合规性 |
| 12 | `orchestrate_consumer_run` | 编排完整查询流程 |

## 消费者硬门控

1. 必须先验证 ZIP、MANIFEST、RELEASE_INDEX 与快照 SHA-256
2. 只返回 decision_usable=true 的字段
3. normalized_value 是消费者业务值；raw_value 不得进入普通回答，只能通过折叠式 provenance_ref 追溯
4. null_unavailable/invalid/needs_rule 不得作为事实返回，必须转为结构化 data_gap
5. 不得跨记录、跨实体自行拼接
6. relation_materialization_status != materialized 时不得执行关联查询
7. 不得根据 ID 前缀、行号相同或文本相似自行建立关联
8. 请求字段不存在或无权限时，不得猜测补值
9. read_only 必须为 true；否则阻塞
10. 任何输出 actor_can_execute 必须为 false

## 六角色最小权限

| 角色 | 允许查询的语义实体 |
|------|-------------------|
| factory (厂长) | 全部已物化实体 |
| line (线长) | shift, work_order |
| quality (质量) | defect_detail, quality_freeze |
| equipment (设备) | downtime_event |
| process (工艺) | shift, downtime_event |
| supply (供应链) | purchase_order, inventory_snapshot, material_detail |

其他组合返回 `BLOCKED_ROLE_SCOPE`。

## 输出合同

### BIFROST_DECISION_INPUT_v0.1

**包含**：request_id, consumer_agent_id, role, query_context, source_release_id, source_snapshot_id, normalized_facts, data_gaps, provenance_refs, contract_versions, validation, source_write_performed=false, actor_can_execute=false

**不包含**：conclusion, root_cause, recommended_actions, confirmation_draft, 自动执行指令

## 部署状态

**04C.5C_CONSUMER_ADAPTER_LOCALLY_VALIDATED_NOT_DEPLOYED**

- 本地只读适配器已验证
- 未发布 Skill
- 未安装到智能体
- 未修改决策编排智能体工作指令
- 未接入妙搭
- 未创建控制表
- 未执行高风险动作

## 批准数据面注册表（只读信任锚）

Consumer 仅信任以下已批准数据面 ZIP（按实际 SHA-256 匹配，不信文件名/声明字段）：

| release_id | SHA-256（前16位） | purpose | status |
|---|---|---|---|
| BIFROST_SEMANTIC_DATA_PLANE_v0.2_FINAL | 81a8e5947a28ffe1 | rollback_approved | active |
| BIFROST_v0.3_RC1 | b12e1f6c8abc9f90 | release_candidate_approved | release_candidate |

## 双版本能力边界（不得混写）

### v0.3 RC1（release_candidate_approved）
- P02 shift 实体已物化 `shift_date` 字段（approved_temporal_order_field）
- 支持真实 `last_n_shifts` 时间窗口查询（返回最近 N 个班次）
- SHA-256: b12e1f6c8abc9f901275c09f679fc7d8ec5cae4f89fac42271e704dd436069e0

### v0.2 FINAL（rollback_approved）
- P02 缺少 approved_temporal_order_field（shift_date 未物化）
- 使用旧 FINAL 查询 last_n_shifts 时返回 `data_gap(missing_approved_temporal_order_field)`
- 不得宣称旧 FINAL 支持 last_n_shifts
- SHA-256: 81a8e5947a28ffe1dcabe123f54e00815ec4a06ca876e0f070ca59a88cf01b42

**禁止将两个版本的能力混写。** 查询前先匹配 matched_release_id，按命中版本的实际能力返回。
