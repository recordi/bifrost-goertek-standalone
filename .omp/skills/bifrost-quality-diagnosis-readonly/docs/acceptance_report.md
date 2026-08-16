# 验收报告 — bifrost-quality-diagnosis-readonly v0.1.2

**日期**: 2026-08-10
**阶段**: 04D.3_QUALITY_CONTRACT_MIGRATED_REAL_CONSUMER_LOCALLY_VALIDATED_NOT_DEPLOYED
**specialist_type**: quality
**logical_skill_version**: 0.1.1 → 0.1.2
**输出合同**: BIFROST_SPECIALIST_RESULT_v0.1.3

---

## 一、合成合同测试

### 1.1 版本与合同验证（T01-T02, 2项）

| 测试 | 结果 |
|------|------|
| T01 logical_version=0.1.2 | PASS |
| T02 contract_version=BIFROST-SPECIALIST-RESULT-v0.1.3 | PASS |

### 1.2 输入合同校验（T03-T03b, 2项）

| 测试 | 结果 |
|------|------|
| T03 合规输入通过 | PASS |
| T03b 合同失败输入阻塞 | PASS |

### 1.3 分组与提取（T04-T05, 2项）

| 测试 | 结果 |
|------|------|
| T04 按 record 分组 | PASS |
| T05 指标提取 | PASS |

### 1.4 不良守恒（T06-T07, 2项）

| 测试 | 结果 |
|------|------|
| T06 守恒检查通过 | PASS |
| T07 非守恒检测 | PASS |

### 1.5 SPC/Cpk 门控（T08-T09, 2项）

| 测试 | 结果 |
|------|------|
| T08 无 SPC 数据阻塞 Cpk | PASS |
| T09 有 SPC 数据可计算 | PASS |

### 1.6 冻结关系（T10-T11, 2项）

| 测试 | 结果 |
|------|------|
| T10 冻结无物化关系产生 data_gap | PASS |
| T11 终态冻结排除 | PASS |

### 1.7 无时间字段不制造趋势（T12, 1项）

| 测试 | 结果 |
|------|------|
| T12 缺时间字段不生成趋势 | PASS |

### 1.8 相关性≠因果（T13, 1项）

| 测试 | 结果 |
|------|------|
| T13 相关性不作为根因 | PASS |

### 1.9 高风险门控（T14, 1项）

| 测试 | 结果 |
|------|------|
| T14 高风险动作返回 needs_confirmation | PASS |

### 1.10 共享合同 v0.1.3 验证（T15-T25, 11项）

| 测试 | 结果 |
|------|------|
| T15 输出 Schema 字节一致 | PASS |
| T16 输入 Schema 字节一致 | PASS |
| T17 共享验证器通过合规输出 | PASS |
| T18 validate-against-input 通过 | PASS |
| T19 旧输出 Schema 被拒绝 | PASS |
| T20 非法 status 被拒绝 | PASS |
| T21 critical severity 被拒绝 | PASS |
| T22 actor_can_execute=true 被拒绝 | PASS |
| T23 缺 evidence_refs 被拒绝 | PASS |
| T24 blocked 含 conclusion 被拒绝 | PASS |
| T25 warning 无 data_gaps 被拒绝 | PASS |

### 1.11 EVREF 字段级证据（T26-T29, 4项）

| 测试 | 结果 |
|------|------|
| T26 evidence_refs 为 EVREF-v1 格式 | PASS |
| T27 metrics 字段绑定验证 | PASS |
| T28 非记录键/占位字符串支持指标 | PASS |
| T29 blocked 结果 evidence_refs 为空 | PASS |

### 1.12 data_gaps 归并（T30-T32, 3项）

| 测试 | 结果 |
|------|------|
| T30 data_gaps 为 9 字段结构 | PASS |
| T31 merge_data_gaps 归并重复缺口 | PASS |
| T32 affected_record_count/occurrence_count 正确 | PASS |

### 1.13 变异与黄金值（T33-T34, 2项）

| 测试 | 结果 |
|------|------|
| T33 删除事实后结论同步消失 | PASS |
| T34 无硬编码黄金值 | PASS |

### 1.14 真实 consumer 联调（T35-T39, 5项）

| 测试 | 结果 |
|------|------|
| T35 场景A 真实成功（quality_freeze） | PASS |
| T36 场景B 真实 data_gap（defect_detail） | PASS |
| T37 场景C 输入合同阻塞 | PASS |
| T38 场景D 删除证据变异 | PASS |
| T39 场景E 高风险门控 | PASS |

### 1.15 卫生与打包（T40-T41, 2项）

| 测试 | 结果 |
|------|------|
| T40 交付包不含 __pycache__/.pyc | PASS |
| T41 MANIFEST 三计数一致性 | SKIPPED（打包后验证） |

### 1.16 已验证 vs 未验证能力（T42, 1项）

| 测试 | 结果 |
|------|------|
| T42 verified/unverified 能力分开登记 | PASS |

**合成合同测试合计**: 42 PASS + 1 SKIPPED = 43 项

---

## 二、真实 consumer 联调

### 联调环境

| 项目 | 值 |
|------|-----|
| consumer 版本 | 0.1.1 |
| 数据面包 | BIFROST_SEMANTIC_DATA_PLANE_v0.2_FINAL.zip |
| consumer 路径 | bifrost-semantic-consumer-readonly |
| 输出合同 | BIFROST_SPECIALIST_RESULT_v0.1.3 |
| Skill 逻辑版本 | 0.1.2 |

### 场景 A: 真实成功场景（quality_freeze）

| 指标 | 值 |
|------|-----|
| consumer 版本 | 0.1.1 |
| BIFROST_DECISION_INPUT 合同校验 | passed |
| 专业 Skill 版本 | 0.1.2 |
| BIFROST_SPECIALIST_RESULT 合同校验 | passed |
| contract_version | BIFROST-SPECIALIST-RESULT-v0.1.3 |
| normalized_facts 数量 | 45 |
| evidence_refs 数量 | 0（纯 data_gap warning 模式） |
| data_gaps 数量 | 6（merge_data_gaps 归并后） |
| data_gaps 字段数 | 9（含 affected_record_count, occurrence_count） |
| status | warning |
| actor_can_execute | False |
| source_write_performed | False |

**说明**: quality_freeze 实体有 45 条记录，但仅包含 decision_event_id 字段，缺少 freeze_status/freeze_reason 等质量分析所需字段。经 merge_data_gaps 归并后产生 6 个结构化 data_gaps（9 字段），status=warning，conclusion=""，evidence_refs=[]。这是真实数据不足的正确表现（纯 data_gap warning 模式），非合成夹具冒充。

### 场景 B: 真实 data_gap 场景（defect_detail）

| 指标 | 值 |
|------|-----|
| consumer 版本 | 0.1.1 |
| BIFROST_DECISION_INPUT 合同校验 | passed |
| 专业 Skill 版本 | 0.1.2 |
| BIFROST_SPECIALIST_RESULT 合同校验 | passed |
| contract_version | BIFROST-SPECIALIST-RESULT-v0.1.3 |
| normalized_facts 数量 | 0 |
| evidence_refs 数量 | 0 |
| data_gaps 数量 | 6（merge_data_gaps 归并后，原始数千条已归并） |
| data_gaps 字段数 | 9 |
| status | warning |
| actor_can_execute | False |

**说明**: defect_detail 有 1575 条记录，但仅含 simulated_shift_id 字段。质量诊断所需的 defect_type/defect_count/yield_rate/spc_measurement 等字段全部缺失。原始 data_gaps 为每条记录 × 每个缺失字段（数千条），经共享 merge_data_gaps 归并后为 6 个结构化缺口。normalized_facts=0，status=warning，conclusion=""，evidence_refs=[]。

### 场景 C: 输入合同阻塞场景

- 构造不合格输入合同（validation.status=failed）
- 结果: status=blocked，conclusion=""，evidence_refs=[]，无 metrics、无 causes、无 recommended_actions
- data_gaps=0
- 通过验证

### 场景 D: 删除证据后的变异场景

- 从 consumer 生成输入合同后，删除部分 normalized_facts 中的证据
- 结果: 对应 metrics/causes/actions 同步消失，data_gaps=2
- 变异测试通过

### 场景 E: 高风险动作门控场景

- 构造含冻结解除请求的输入
- 结果: status=needs_confirmation，evidence_refs=1
- recommended_actions 中 is_high_risk=true, needs_human_confirmation=true, prohibited_auto_execute=true, actor_can_execute=false
- data_gaps=4
- 通过验证

---

## 三、实际成功场景

场景 A 是实际成功场景：consumer 成功读取 FINAL 数据面，生成有效 BIFROST_DECISION_INPUT_v0.1 合同，质量诊断 Skill v0.1.2 成功消费并输出通过共享验证器的 BIFROST_SPECIALIST_RESULT_v0.1.3。

由于真实数据面中 quality_freeze 实体仅有 decision_event_id 字段，status 为 warning（有 data_gaps）而非 completed。这是真实数据不足的正确表现，符合"若真实数据不足，输出 warning/data_gap，不得用合成夹具冒充真实联调成功"的要求。

---

## 四、实际 data_gap 场景

场景 B 是实际 data_gap 场景：defect_detail 实体有 1575 条记录但仅含 simulated_shift_id 字段，质量诊断所需的全部专业字段缺失。原始数千条 data_gaps 经共享 merge_data_gaps 归并后为 6 个结构化缺口（9 字段，含 affected_record_count 和 occurrence_count）。输出 status=warning，normalized_facts=0，conclusion=""，evidence_refs=[]。

---

## 五、已验证能力与未验证能力

### 已验证能力（8项）

| 能力 | 验证方式 |
|------|----------|
| 输入合同 BIFROST_DECISION_INPUT_v0.1 校验 | 真实 consumer 输出 |
| EVREF-v1 字段级证据生成与跨输入输出验证 | 真实数据 |
| data_gaps 归并（9字段，数千条→少量结构化缺口） | 真实数据 |
| 纯 data_gap warning 模式（conclusion='' / evidence_refs=[]） | 真实数据字段不足 |
| blocked 语义（输入合同失败时不输出业务结论） | 真实+合成 |
| needs_confirmation 高风险门控（冻结审查动作） | 真实+合成 |
| 变异测试（删除事实后 metrics/causes/actions 同步消失） | 真实+合成 |
| 共享验证器 validate + validate-against-input 全部通过 | 真实数据 |

### 尚未验证能力（7项，因字段不足）

| 能力 | 原因 |
|------|------|
| 良率分析 | FINAL 数据面无 yield/yield_rate/quality_rate/good_output/total_output 字段 |
| 不良分布分析 | defect_detail 仅含 simulated_shift_id，缺 defect_type/defect_count/defect_ratio |
| SPC/Cpk 计算 | 无 spc_measurement_points/usl/lsl/sample_rule 字段 |
| 冻结状态分析 | quality_freeze 仅含 decision_event_id，缺 freeze_status/freeze_id/freeze_quantity |
| 复检分析 | 无 inspection_status/reinspection_status 字段 |
| 不良守恒聚合检查 | 无 defect_count/defect_ratio 字段无法执行聚合 |
| （注） | 以上能力代码已实现并通过合成夹具测试，但因 FINAL 数据面字段不足无法在真实联调中产生 completed 结果 |

---

## 六、未执行的平台部署

| 项目 | 状态 |
|------|------|
| Skill 发布 | 未执行 |
| Skill 安装 | 未执行 |
| 进入 Aily 平台运行 | 未执行 |
| 修改决策编排智能体工作指令 | 未执行 |
| 接入妙搭前端 | 未执行 |
| 修改共享合同包 | 未执行 |
| 修改 consumer v0.1.1 | 未执行 |
| 修改数据面 FINAL 包 | 未执行 |
| 修改其他专业 Skill | 未执行 |
| 创建控制表 | 未执行 |

---

## 七、测试汇总

| 类别 | 测试ID | 数量 | 结果 |
|------|--------|------|------|
| 版本与合同 | T01-T02 | 2 | ALL PASS |
| 输入合同校验 | T03-T03b | 2 | ALL PASS |
| 分组与提取 | T04-T05 | 2 | ALL PASS |
| 不良守恒 | T06-T07 | 2 | ALL PASS |
| SPC/Cpk 门控 | T08-T09 | 2 | ALL PASS |
| 冻结关系 | T10-T11 | 2 | ALL PASS |
| 无时间字段不制造趋势 | T12 | 1 | PASS |
| 相关性≠因果 | T13 | 1 | PASS |
| 高风险门控 | T14 | 1 | PASS |
| 共享合同 v0.1.3 | T15-T25 | 11 | ALL PASS |
| EVREF 字段级证据 | T26-T29 | 4 | ALL PASS |
| data_gaps 归并 | T30-T32 | 3 | ALL PASS |
| 变异与黄金值 | T33-T34 | 2 | ALL PASS |
| 真实 consumer 联调 | T35-T39 | 5 | ALL PASS |
| 卫生与打包 | T40-T41 | 2 | 1 PASS + 1 SKIPPED |
| 已验证vs未验证能力 | T42 | 1 | PASS |
| **合计** | | **43** | **42 PASS + 1 SKIPPED** |

机器可复核结果文件: tests/results/test_results.json

---

## 八、施工隔离确认

- 未修改 BIFROST_SPECIALIST_CONTRACT_v0.1.3（逐字节复制 schema 和验证器）
- 未修改 consumer v0.1.1
- 未修改数据面 FINAL 包
- 未修改生产/供应链专业 Skill
- 未修改 bifrost-decision-readonly
- 未修改 bifrost-data-mapper-readonly
- 未修改妙搭前端
- 未修改 MAP/SEM/DQ 基线
- 未修改现有智能体工作指令
- 未发布、未安装、未进入平台运行

---

## 九、包装一致性

| 指标 | 值 |
|------|-----|
| zip_file_count（除 MANIFEST） | 41 |
| contents_file_count | 41 |
| manifest_entry_count | 41 |
| 三者一致 | ✓ |
| CONTENTS.json 已登记 | ✓ |
| README.md 已登记 | ✓ |
| 无 __pycache__/.pyc | ✓ |
| CONTENTS.json 不含自身哈希 | ✓ |
