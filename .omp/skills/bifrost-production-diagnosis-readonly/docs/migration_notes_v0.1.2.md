# 迁移说明 — v0.1.1 → v0.1.2 (04D.3-PROD)

## 变更概要

本版本将生产诊断 Skill 从共享合同 v0.1.1 迁移到 v0.1.3，完成真实 consumer 最终联调。

## 核心变更

### 1. 输出合同升级
- v0.1.1: `BIFROST-SPECIALIST-RESULT-v0.1.1`
- v0.1.2: `BIFROST-SPECIALIST-RESULT-v0.1.3`
- 逐字节复制共享 Schema 和验证器，哈希校验通过

### 2. EVREF-v1 字段级证据
- v0.1.1: `EV:{field}:{source_table}:{source_record_id}` (占位格式)
- v0.1.2: `EVREF-v1:<SHA256>` (由共享 `build_canonical_evidence_ref` 生成)
- 删除所有占位证据 (`EV:no_evidence:`, `EV:*:no_provenance:`, 裸 `semantic_record_key`)

### 3. 高风险动作状态优先级修复
- v0.1.1 bug: `needs_confirmation + data_gaps → warning` (高风险被降级)
- v0.1.2 fix: `needs_confirmation` 无条件优先 (高风险动作存在时必须为 needs_confirmation)

### 4. data_gaps 归并
- v0.1.1: 原始 data_gaps 直接输出 (321/741 条)
- v0.1.2: 使用共享 `merge_data_gaps` 归并 (735 → 8 条)

### 5. metrics 字段绑定
- v0.1.2: 每个 metric 的 `evidence_refs` 解析到的 `semantic_field` 必须与 metric 声明一致
- 无合法 EVREF 的字段不产出 metric

### 6. 变异测试新增
- 错误字段 EVREF 必须被 `validate_against_input` 拒绝
- 裸 record_key 必须被外部验证器拒绝
- 占位证据必须被验证器拒绝
- 高风险+warning 必须被验证器拒绝
