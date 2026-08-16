# bifrost-quality-diagnosis-readonly v0.1.2

BIFROST 质量诊断只读分析 Skill，输出合同 `BIFROST_SPECIALIST_RESULT_v0.1.3`。

## 版本

| 维度 | 值 |
|------|-----|
| logical_version | 0.1.2 |
| output_contract | BIFROST_SPECIALIST_RESULT_v0.1.3 |
| input_contract | BIFROST_DECISION_INPUT_v0.1（字节不变） |
| 共享验证器 | specialist_contract_validator.py v0.1.3（逐字节复制） |
| stage | LOCALLY_VALIDATED_NOT_DEPLOYED |

## 目录结构

```
bifrost-quality-diagnosis-readonly/
├── SKILL.md
├── README.md
├── CONTENTS.json          # 全文件清单（不含自身哈希）
├── MANIFEST.sha256        # 逐文件 SHA-256（不含自身）
├── scripts/
│   └── quality_diagnosis.py   # 10 个确定性能力 + 编排入口
├── validator/
│   ├── specialist_contract_validator.py  # v0.1.3 共享验证器（逐字节复制）
│   └── quality_validator.py              # 质量专业外部验证器
├── schema/
│   ├── BIFROST_DECISION_INPUT_v0.1.schema.json          # 输入合同（字节不变）
│   └── BIFROST_SPECIALIST_RESULT_v0.1.3.schema.json     # 权威输出 Schema
├── tests/
│   ├── test_quality_diagnosis.py     # 42 项测试
│   ├── fixtures/                      # 13 个合成夹具 + v0.1.3 合规样例
│   └── results/test_results.json      # 机器可复核测试结果
├── real_integration/                  # 真实 consumer 联调产物
│   ├── decision_input_scenario_{A-E}.json
│   ├── specialist_result_scenario_{A-E}.json
│   └── integration_test_results.json
├── references/quality_rules.md
└── docs/
    ├── acceptance_report.md           # 验收报告
    └── diff_rollback.md               # v0.1.1 → v0.1.2 差异
```

## 测试

```
python3 -m pytest tests/test_quality_diagnosis.py -v
```

42 项通过、0 失败、1 跳过（MANIFEST 一致性在打包后验证）。

## 安全约束

- 全部只读，actor_can_execute 恒 false
- 不发布、不安装、不进入平台运行
- 不修改 consumer、数据面、其他专业 Skill、前端或正式基线
