# bifrost-semantic-consumer-readonly

BIFROST 语义数据消费者只读适配器。

- **logical_version**: 0.1.4
- **query_contract_version**: BIFROST-CONSUMER-QUERY-v0.2
- **stage**: 04D.4C.1_PLATFORM_READY_NOT_DEPLOYED

## 04D.4C.1-CONSUMER-P0 变更（value_consumption_status 兼容层修复）

1. **value_status → value_consumption_status 确定性归一化**：在 `_normalize_v03_fields` 中，
   将 RC1 轻量字段（含 `value_status`、不含 `value_consumption_status`）的 `value_status`
   确定性映射为 `value_consumption_status`。
   - `usable` → `value_consumption_status=usable`、`normalized_value` 从 `value` 读取、`decision_usable=true`
   - `null_unavailable`/`invalid`/`needs_rule` → 保留对应不可消费状态、`decision_usable=false`，不得提升为 usable
   - 未知/缺失/非法 `value_status` → `value_consumption_status=blocked`、`decision_usable=false`，转为 data_gap，不得默认通过
2. **保留原始事实**：字段已存在 `value_consumption_status` 时保留不覆盖；与 `value_status` 矛盾时
   返回结构化合同问题（合同阻塞），不得静默通过。
3. **轻量 provenance 映射**：将 RC1 轻量字段的 `source_table`/`source_column`/`provenance` 映射为
   标准 `evidence_locator`/`source_field`，使下游专业 Skill 可消费；不编造 `source_row_number`/`source_column_index`
   （缺失则该字段无法生成 EVREF，但不阻塞输入合同）。
4. **不修改** RC1、旧 FINAL、Production、Quality 或共享合同；不针对 LINE-S03、固定字段值或当前样本写专属分支。
5. **修复根因**：0.1.3 兼容层仅将 `value_status` 归一化为 `decision_usable`（通过门控），却未归一化为
   `value_consumption_status`（输出事实为空串），导致 Production/Quality 专业 Skill 输入合同校验以
   `value_consumption_status` 为空阻塞（BLOCKED_UNUSABLE_FACT / BLOCKED_INPUT_CONTRACT）。

## 04D.4B.1.2 纠偏内容

1. **测试真实性收口**：逐测试机器可读明细，31 项内部测试全部实际执行并通过（0 skipped）
2. **确认队列分流**：27 项混合队列分流为 4 类（mapping_review=15, semantic_alias_review=5, cross_source_blocked=5, rematerialization=2），守恒 15+5+5+2=27
3. **双版本能力边界**：v0.3 RC1 的 P02 已物化 shift_date，支持真实 last_n_shifts 查询；v0.2 FINAL 的 P02 缺少该字段，使用旧 FINAL 时返回 data_gap(missing_approved_temporal_order_field)，两个版本能力不得混写
4. **外部包装检查分离**：three-count / all-zero 检查从内部测试分离，在 ZIP 创建后执行

## 04D.4B.1.1 纠偏内容

1. **跨源隔离**：覆盖矩阵按 source_scope (P01_OFFICIAL / P02_SIM) 独立生成，禁止跨源引用
2. **source_missing 修正**：综合 4 源证据（表头/MAP/SEM/handoff），模糊匹配只生成候选
3. **别名防护**：performance_rate/performance_rate_raw、quality_rate/quality_factor 严格区分
4. **单位合同**：带单位后缀的停机时长字段经过字段合同和单位规则判断
5. **矩阵分源输出**：P01/P02/combined 三份独立矩阵
6. **测试真实性纠偏**：合成测试标记、真实 P02 时间字段缺失测试、跨源变异测试、别名误判测试、报告守恒测试

## 04D.4B.1 升级内容（保留）

1. **区间查询**：支持 last_n_shifts / last_n_records / date_range / all_available
2. **结构化过滤**：支持 eq / in / between / is_null / is_not_null
3. **排序与限制**：sort（单键/多键）+ limit（过滤窗口排序后执行）
4. **多实体编排**：orchestrate_consumer_batch_run()
5. **覆盖矩阵**：coverage_matrix.py 动态生成生产/质量字段覆盖矩阵（v0.2 跨源隔离版）

## 批准数据面与能力边界

| release_id | SHA-256 前16位 | purpose | shift_date | last_n_shifts |
|---|---|---|---|---|
| BIFROST_SEMANTIC_DATA_PLANE_v0.2_FINAL | 81a8e5947a28ffe1 | rollback_approved | 未物化 | data_gap |
| BIFROST_v0.3_RC1 | b12e1f6c8abc9f90 | release_candidate_approved | 已物化 | 支持 |

- v0.3 RC1：P02 shift 已物化 shift_date，支持真实 last_n_shifts 查询
- v0.2 FINAL：P02 缺少 approved_temporal_order_field，查询 last_n_shifts 返回 data_gap
- 两个版本能力不得混写；按 matched_release_id 命中版本的实际能力返回

## 向后兼容

v0.1 单实体查询（orchestrate_consumer_run）完全兼容，旧 request 格式无需修改。

## 关键约束

- 只返回 decision_usable=true 的字段
- 缺少批准时间字段时返回 data_gap(missing_approved_temporal_order_field)
- 不按 record_id / 行号 / 字符串前缀猜测时间顺序
- relation_materialization_status 未确认时禁止跨实体 join
- read_only 必须为 true；actor_can_execute 恒为 false
- 覆盖矩阵禁止跨源引用，跨源字段标记为 cross_source_candidate

## 测试

- tests/test_consumer_adapter.py — 原有回归测试
- tests/test_04d_4b_1.py — 04D.4B.1 测试（T01–T25）
- tests/test_04d_4b_1_1.py — 04D.4B.1.1 纠偏测试（T01–T30）
- 内部测试统计: discovered=31, executed=31, passed=31, skipped=0, failed=0, errors=0, blocked=0
- 外部包装检查: three_counts_equal + all_zero (ZIP 创建后执行)
- 历史 skipped 说明: T16/T17 在 04D.4B.1.1 首次运行因 test_results 文件未生成而 skipped，本轮实际执行并通过
