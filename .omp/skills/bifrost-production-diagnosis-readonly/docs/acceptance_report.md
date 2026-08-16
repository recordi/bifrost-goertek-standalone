# 验收报告 — bifrost-production-diagnosis-readonly v0.1.2

## 基本信息

| 项目 | 值 |
|---|---|
| Skill 逻辑版本 | 0.1.2 |
| 输出合同版本 | BIFROST-SPECIALIST-RESULT-v0.1.3 |
| 状态 | LOCALLY_VALIDATED_NOT_DEPLOYED |
| 任务编号 | 04D.3-PROD |
| 日期 | 2026-08-10 |

## 1. 逐字节复制与哈希校验

### 输入 Schema
- 文件: `schema/BIFROST_DECISION_INPUT_v0.1.schema.json`
- SHA-256: `b899167f8fd282c3e1992a063bda8ffd5ba0d2b64cde82b13e6f946c7dfc9862`
- 与合同源: 逐字节一致 ✓

### 输出 Schema
- 文件: `schema/BIFROST_SPECIALIST_RESULT_v0.1.3.schema.json`
- SHA-256: `bc2c043ceb72db5904e6b5abc252cbb53779125ce49e5f938f57befc04711c0b`
- 与合同源: 逐字节一致 ✓

### 共享验证器
- 文件: `validator/specialist_contract_validator.py`
- SHA-256: `048191df4dbba441278987659697fc8b6e078859febb73690eca314c4d20a020`
- 与合同源: 逐字节一致 ✓

## 2. EVREF-v1 字段级证据

- 使用共享 `build_canonical_evidence_ref` 生成 `EVREF-v1:<SHA256>`
- 7 个规范字段参与哈希：semantic_record_key, semantic_field, source_file_sha256, source_table, source_row_number, source_column_name, source_column_index
- 删除所有占位证据：`EV:no_evidence`、`EV:*:no_provenance`、裸 `semantic_record_key` ✓

## 3. metrics/causes/actions 证据验证

- 每条 metric 的 `evidence_refs` 为字段级 EVREF-v1，且通过 `validate_specialist_result_against_input` 校验 ✓
- metrics 字段绑定：每个 metric 的 `evidence_refs` 解析到的 `semantic_field` 与 metric 声明的 `semantic_field` 一致 ✓
- 无合法 EVREF 的字段不产出 metric/cause/action（不使用占位证据） ✓

## 4. 高风险动作状态优先级

- 优先级: blocked > needs_confirmation > warning > completed
- 高风险动作存在时，非 blocked 结果必须为 `needs_confirmation` ✓
- v0.1.1 bug 修复：S5 高风险场景从 `warning` 修正为 `needs_confirmation` ✓

## 5. data_gaps 归并

- 使用共享 `merge_data_gaps` 归并 ✓
- 输出 9 字段结构：semantic_entity, semantic_field, reason, value_consumption_status, source_locator, required_resolution, affected_record_count, occurrence_count, sample_source_locators ✓
- sample_source_locators 最多 3 条 ✓

### 321/741 重复 data_gap 修复

| 场景 | 原始 data_gaps | 归并后 data_gaps | 修复效果 |
|---|---|---|---|
| S1 (oee_source+source_shift_id) | — | 7 | ✓ |
| S2 (oee_source+oee_recomputed) | 735 | 8 | ✓ 大幅缩减 |

## 6. 真实 consumer 联调结果

### 场景 1: 真实成功场景
- consumer: shift 实体, P02 scope, oee_source + source_shift_id
- normalized_facts: 525
- evidence_refs: 有 (EVREF-v1)
- data_gaps: 7 (已归并)
- status: needs_confirmation (有 oee_source → 高风险排产动作)
- validate_output: PASS
- validate_against_input: PASS
- external_validator: PASS

### 场景 2: 真实 data_gap 场景
- consumer: shift 实体, oee_source + oee_recomputed
- normalized_facts: 105
- 原始 data_gaps: 735 → 归并后: 8
- status: needs_confirmation
- validate_output: PASS
- validate_against_input: PASS

### 场景 3: 输入合同阻塞场景
- 篡改 contract_name → blocked
- conclusion 空, metrics 空, causes 空, actions 空, evidence_refs 空
- validate_output: PASS

### 场景 4: 删除证据变异场景
- 删除 oee_source → 对应 metric 消失
- data_gaps 从 7 → 8 (新增 oee_source gap)
- 变异结果通过验证器

### 场景 5: 高风险动作门控场景
- 合成夹具: 三因子齐全 + oee_source
- high_risk_count: 1
- status: needs_confirmation (v0.1.1 为 warning，已修复)
- 破坏门控 (改为 warning) → 被拒绝 ✓

## 7. 变异测试

| 变异类型 | 预期 | 结果 |
|---|---|---|
| 错误字段 EVREF | validate_against_input 拒绝 | ✓ PASS |
| 裸 record_key | 外部验证器 + validate_against_input 拒绝 | ✓ PASS |
| 占位证据 (EV:no_evidence) | 外部验证器 + validate_output 拒绝 | ✓ PASS |
| 高风险+warning | validate_output + 外部验证器拒绝 | ✓ PASS |
| 高风险+completed | validate_output 拒绝 | ✓ PASS |

## 8. 既有规则保留

- OEE 三因子白名单 (availability/performance_rate/quality_factor) ✓
- 物料风险非直接原因 (associated_risk, 非 oee_direct_driver) ✓
- 禁止伪造 MTBF/MTTR (缺证据时不计算) ✓
- 禁止制造趋势 (时间字段不足时不声称趋势) ✓

## 9. 隔离性

- 未修改 consumer ✓
- 未修改数据面 ✓
- 未修改其他专业 Skill ✓
- 未修改前端 ✓
- 未修改正式基线 ✓
- 未发布、未安装 ✓

## 10. 测试统计

- 合同测试: 29/29 PASS
- 真实 consumer 联调: 28/28 PASS
- 总计: 57/57 PASS, 0 FAIL

## 11. 机器可读结果文件

- `tests/results/integration_test_results.json` — 联调汇总
- `tests/results/decision_input_saved.json` — 各场景 decision_input
- `tests/results/specialist_result_saved.json` — 各场景 specialist_result
