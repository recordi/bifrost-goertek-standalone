---
name: bifrost-data-mapper-readonly
description: >-
  BIFROST 字段整合只读映射能力——读取结构化数据文件（xlsx/csv/json），自动识别表、字段、
  数据类型、单位、值域与数据质量特征，将来源字段匹配到 BIFROST 统一语义模型（SEM-v1.1.1），
  发现表间关联键候选，生成字段映射草稿、关联候选和语义扩展建议。适用于新数据源接入、
  字段整合审计、跨源泛化验证场景。全程只读，不修改来源数据，不直接修改正式语义模型。
  低置信度、口径冲突、关联歧义必须经人工确认门控。
---

# BIFROST 字段整合只读映射

## 能力概述

本 Skill 是 BIFROST 数据接入与字段整合专业能力，负责将外部结构化数据文件映射到
统一语义模型。它不是六角色（厂长/线长/质量/设备/工艺/供应链）中的任何一个，
不承担业务决策、OEE 原因分析、任务派发或高风险执行。

## 触发场景

- 新数据源接入时的字段识别与映射
- 字段整合审计与可审计交付
- 跨源泛化验证（SIM / 官方脱敏 / 零样本）
- 语义模型覆盖度检测与扩展建议

## 边界

- **只读**：不修改来源数据，不保存/覆盖/重新导出输入文件
- **不写回**：不直接修改 SEM-v1.1.1 或任何正式语义模型
- **不自动确认**：新数据源 confirmed=0，新关联 confirmed=0
- **人工确认门控**：低置信度、单位冲突、口径冲突、多目标匹配必须 requires_human_confirmation=true
- **合同驱动**：仅读取版本化合同，不把规则硬编码进业务代码
- **不执行宏/公式/外部链接**：Excel 使用 read_only=true 打开

## 合同依赖

所有合同文件位于 `references/contracts/`，必须登记 filename / version / SHA-256 /
source_family / source_type / approval_status / loaded_at_runtime。

合同文件缺失、版本错误或哈希异常时返回 `BLOCKED_SEMANTIC_CONTRACT`。

## 确定性函数

1. `verify_source_asset` — 验证文件存在/格式/大小/SHA-256
2. `inspect_dataset_schema` — 输出表名/行数/字段数/字段顺序/公式字段/隐藏表
3. `profile_source_field` — 输出字段类型/非空/空值率/唯一率/样例/值域/格式/异常
4. `normalize_data_type` — 生成类型标准化建议，不覆盖原始值
5. `normalize_unit` — 识别单位，0-1 与 0-100 比例冲突标记 ambiguous
6. `match_semantic_field` — 根据合同/字段名/类型/单位/值域/实体上下文匹配
7. `infer_join_key_candidates` — 输出命中率/唯一率/基数关系/风险，不自动生成外键
8. `generate_mapping_draft` — 为每个来源字段生成且仅生成一条裁决记录
9. `generate_semantic_extension_proposals` — 仅在 SEM 无法覆盖时输出 proposal
10. `validate_mapping_contract` — 校验字段守恒/状态枚举/审批来源/关联状态/一致性
11. `orchestrate_mapping_run` — 按固定顺序执行，统一输出，门控失败即停止

## 映射状态

`mapping_status` 只允许：confirmed / proposed / ambiguous / rejected / unmapped

自动 confirmed 条件：命中已批准合同 + 来源签名匹配 + 字段名/类型/单位全匹配 +
合同版本完整 + 无新值域冲突。不满足时降级为 proposed 或 ambiguous。

## 关联状态

`relation_status` 只允许：validated_candidate / ambiguous / rejected / confirmed

本 Skill 不具备批准关联权限，所有新关联 confirmed=0。

## CLI 用法

```bash
python scripts/mapper_cli.py \
  --source-file <path> \
  --file-format xlsx \
  --request-id REQ-001 \
  --output result.json
```

## 数据质量

遵守 DQ-v1.0.1：detected / tested_no_anomaly / needs_rule / not_tested。
缺少更新时间或刷新 SLA 时 stale_data=not_tested，不直接判定数据过期。
不自动修复、删除、覆盖或清洗源数据，只输出治理建议。

## 版本

- logical_skill_version: 0.1.2
- release_status: LOCAL_VALIDATED_NOT_PUBLISHED
- skill_id: null
- platform_skill_version: null

## 04C.4A.1 纠偏要点

- 官方 MAP 合同索引兼容 `source_sheet`，与 SIM MAP 的 `source_table` 归一为 `normalized_source_table`。
- SIM 字段扫描口径分离：`physical_used_column_count` / `semantic_mapping_field_count` / `non_tabular_excluded_column_count`；说明/校验型非标准表的空表头列不得生成 `col_n` 进入语义映射。
- `mapping_draft` 字段类型拆分：`source_data_type`（推断数据类型）与 `source_dataset_type`（数据源性质），禁止重复键 `source_type`。
- 继承批准降级：单位/类型/口径检查未通过的继承项输出 `suspended_inherited_approvals`，不再计入 `active_confirmed_count`。
- OEE 安全合同 `can_recompute_oee=false` 作为明确合同字段输出；`performance_rate_raw>1.0` 检出后 `validation_status=flagged_above_unity`，保留原值不截断。

## 04C.4A.2 可信边界收口要点

- 新增只读合同 `source_signature_registry_v1.0.json`（版本 `SOURCE-SIGNATURE-v1.0`），为已批准 SIM 源和官方源登记 `approved_asset_sha256` / `approved_schema_fingerprint_sha256` / `mapping_rule_version` / `approval_status` 等元数据。
- `schema_fingerprint` 由有序表名、每张表有序字段名、字段数量、非标准表分类确定性生成，不含业务数值。
- 数据源身份识别改为签名驱动：文件 SHA-256 完全一致 → `exact`；哈希变化但 schema 指纹一致且字段级类型/单位/口径检查通过 → `compatible`；其他 → `unknown`。文件名、路径名、`source_name`、`declared_source_family` 仅作提示，不得单独建立 exact/compatible 身分。
- 删除基于文件名（`sim`/`v2.2`/`歌尔`/`脱敏`）授予可信身份的逻辑；`unknown` 来源 `confirmed_inherited_count=0`、`confirmed_new_count=0`。
- `orchestrate_mapping_run` 入口强制只读请求合同：`request` 为 object、`source_file` 非空字符串、`file_format` 属于 xlsx/csv/json、`read_only` 存在且严格等于 true；缺失或不为 true 时返回 `BLOCKED_READ_ONLY_VIOLATION`，不继续读取文件。
- 路径穿越真正修复：原始路径包含独立 `..` 路径段时在文件存在性检查前返回 `BLOCKED_PATH_TRAVERSAL`，不得用 `pass` 跳过，不得因路径不存在降级为 `BLOCKED_FILE_NOT_FOUND`；路径穿越、文件不存在、格式不支持为三个可区分错误码。
