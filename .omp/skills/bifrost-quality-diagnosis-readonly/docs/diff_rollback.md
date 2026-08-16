# 回滚说明 — bifrost-quality-diagnosis-readonly v0.1.2

## 回滚场景

如果 bifrost-quality-diagnosis-readonly 需要回滚，按以下步骤执行。

## 回滚步骤

### 1. 删除交付包

删除交付 ZIP 文件和解压目录即可完全回滚。本 Skill 不修改任何外部系统：

- 未发布 Skill
- 未安装到智能体
- 未修改决策编排智能体工作指令
- 未接入妙搭
- 未创建控制表
- 未修改业务数据
- 未修改其他并行施工线产物

### 2. 无需恢复外部状态

由于本阶段为 LOCALLY_VALIDATED_NOT_DEPLOYED：
- 无数据库变更需要回滚
- 无配置变更需要恢复
- 无 API 注册需要注销
- 无权限变更需要撤销

### 3. 影响范围

回滚仅影响：
- 质量诊断 Skill 本身（本地原型代码 v0.1.2）
- 测试夹具和结果
- 独立验证器（共享 v0.1.3 逐字节副本）

不影响：
- 语义消费者
- 决策编排智能体
- 生产诊断 Skill
- 供应链诊断 Skill
- 语义数据面
- 妙搭前端

## v0.1.1 → v0.1.2 差异

| 维度 | v0.1.1 | v0.1.2 |
|------|--------|--------|
| logical_version | 0.1.1 | 0.1.2 |
| 输出合同 | BIFROST_SPECIALIST_RESULT_v0.1.1 | BIFROST_SPECIALIST_RESULT_v0.1.3 |
| 输出 Schema | bifrost_specialist_result_v0.1.schema.json | BIFROST_SPECIALIST_RESULT_v0.1.3.schema.json |
| 验证器 | 自有验证器 | 共享验证器（逐字节复制） |
| evidence_refs | 记录级 semantic_record_key | EVREF-v1 字段级（build_canonical_evidence_ref） |
| data_gaps | 原始重复（数千条） | merge_data_gaps 归并（9字段结构化） |
| data_gaps 字段数 | 变量 | 固定9字段（含 affected_record_count, occurrence_count） |
| 纯 data_gap warning 模式 | 未实现 | conclusion='' / evidence_refs=[] |
| blocked evidence_refs | 含占位字符串 | []（空） |
| metrics 字段绑定 | 未验证 | EVREF 字段绑定验证 |
| 真实 consumer 联调 | 未执行 | 5场景全部通过 |
| 已验证/未验证能力 | 未区分 | 8项已验证 + 7项未验证 |
| 测试数量 | 18项 | 43项（42 PASS + 1 SKIPPED） |

## 差异说明（与消费者）

| 维度 | 消费者 | 质量诊断 |
|------|--------|----------|
| 输入 | 语义数据面 ZIP | BIFROST_DECISION_INPUT_v0.1 |
| 输出 | BIFROST_DECISION_INPUT_v0.1 | BIFROST_SPECIALIST_RESULT_v0.1.3 |
| 职责 | 查询可信事实 | 专业质量分析 |
| 专业范围 | 全部已物化实体 | 良率/不良/冻结/SPC |
| 写操作 | 无 | 无 |
| actor_can_execute | false | false |

## 版本信息

- logical_version: 0.1.2
- 输出合同: BIFROST_SPECIALIST_RESULT_v0.1.3
- stage: LOCALLY_VALIDATED_NOT_DEPLOYED
- 日期: 2026-08-10
