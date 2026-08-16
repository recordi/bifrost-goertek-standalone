# bifrost-production-diagnosis-readonly v0.1.2

BIFROST 生产诊断只读 Skill — 迁移共享合同 v0.1.3 并完成真实 consumer 最终联调。

## 版本

- **逻辑版本:** 0.1.2
- **输出合同:** BIFROST-SPECIALIST-RESULT-v0.1.3
- **状态:** LOCALLY_VALIDATED_NOT_DEPLOYED

## 11 项必完成项

1. ✓ 逐字节复制 v0.1.3 输出 Schema、输入 Schema 和独立验证器，哈希校验通过
2. ✓ 使用共享 build_canonical_evidence_ref 生成字段级 EVREF-v1
3. ✓ 删除 EV:no_evidence、EV:*:no_provenance、裸 semantic_record_key 及其他占位证据
4. ✓ metrics/causes/actions 每条证据通过 validate_specialist_result_against_input
5. ✓ 高风险动作存在时，非 blocked 结果为 needs_confirmation，不得为 warning/completed
6. ✓ 使用共享 merge_data_gaps 归并缺口，输出 affected_record_count、occurrence_count 及最多 3 条样例定位
7. ✓ 修复真实联调中 735 条重复 data_gap 直接输出的问题（归并后 8 条）
8. ✓ 保留 OEE 三因子、物料风险非直接原因、禁止伪造 MTBF/MTTR、禁止制造趋势等既有规则
9. ✓ 重新执行真实 consumer 联调，保存机器可读的 decision_input、specialist_result 和 integration_test_results
10. ✓ 增加变异测试：错误字段 EVREF、裸 record_key、占位证据、高风险+warning 必须失败
11. ✓ 不修改 consumer、数据面、其他专业 Skill、前端或正式基线；不发布、不安装

## 测试结果

- 合同测试: 29/29 PASS
- 真实 consumer 联调: 28/28 PASS
- 总计: 57/57 PASS

## 目录结构

```
bifrost-production-diagnosis-readonly_v0.1.2/
├── SKILL.md
├── README.md
├── CONTENTS.json
├── schema/
│   ├── BIFROST_DECISION_INPUT_v0.1.schema.json
│   └── BIFROST_SPECIALIST_RESULT_v0.1.3.schema.json
├── scripts/
│   ├── __init__.py
│   ├── production_constants.py
│   └── production_diagnosis.py
├── validator/
│   ├── specialist_contract_validator.py
│   └── production_validator.py
├── references/
│   └── production_rules.md
├── tests/
│   ├── fixtures/
│   │   └── golden_event_values.json
│   ├── test_production_diagnosis.py
│   ├── test_real_consumer_integration.py
│   └── results/
│       ├── integration_test_results.json
│       ├── decision_input_saved.json
│       └── specialist_result_saved.json
└── docs/
    ├── acceptance_report.md
    └── migration_notes_v0.1.2.md
```

## 运行

```bash
# 合同测试
python3 -m pytest tests/test_production_diagnosis.py -v

# 真实 consumer 联调
python3 tests/test_real_consumer_integration.py
```

## 依赖

- Python 3.10+
- bifrost-semantic-consumer-readonly v0.1.1 (只调用)
- BIFROST_SEMANTIC_DATA_PLANE_v0.2_FINAL (只读取)
- BIFROST_SPECIALIST_CONTRACT_v0.1.3 (Schema + 验证器逐字节复制)
