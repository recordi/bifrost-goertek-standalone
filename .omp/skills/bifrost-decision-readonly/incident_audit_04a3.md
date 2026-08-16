# BIFROST 载荷伪造事故审计记录

## 事故编号
INCIDENT-BIFROST-04A3-PAYLOAD-FABRICATION

## 登记时间
2026-08-08

## 事故等级
P0（真实性缺陷）

## 涉及版本
- 缺陷版本：bifrost-decision-readonly v1.0.1 (skill_4kswbwnxuahmm)
- 修复版本：bifrost-decision-readonly v1.0.2 (skill_4kswbwnxuahmm)

## 事故描述

版本 1.0.1 在找不到生产载荷文件时，没有停止运行并返回错误，而是自行构造替代载荷，产生了以下伪造内容：

1. **虚构物理表名** — 伪造了不存在的数据库表名，使 EvidenceRef 看起来已解析到物理记录
2. **虚构"主轴轴承磨损"** — 编造了不存在的故障原因，作为设备角色的归因结论
3. **使用防硬编码测试中的 30%/28% 缺陷比例** — 将测试夹具中的缺陷比例值（外观不良 30.0%、尺寸超差 28.0%）当作生产数据返回
4. **基于伪造载荷返回 validation=passed** — 在载荷完全虚构的情况下，证据契约校验仍返回通过

## 根因分析

1. `orchestrate_response()` 在调用 `load_event()` / `load_overview()` 失败时，没有阻塞退出，而是继续执行业务逻辑
2. 缺乏启动前置验证步骤，无法检测载荷文件是否真实存在、哈希是否正确
3. 测试夹具与生产代码在同一目录层级，存在被误导入的风险
4. EvidenceRef 校验在载荷不可信的情况下仍被执行，可能基于伪造数据返回通过

## 影响评估

- 1.0.1 版本不得继续用于正式演示
- 所有基于 1.0.1 的演示结果需要复核，确认是否使用了伪造载荷
- 伪造的物理表名和故障原因可能误导决策

## 修复措施（04A.3）

1. **新增 `verify_runtime_assets()` 启动前置步骤** — 固定从批准目录 `workspace/bifrost/payloads/` 读取，验证文件存在/文件名/SHA256/payload_version/analysis_version/dataset_id
2. **失败时立即阻塞** — 返回 `{"status": "BLOCKED_INPUT_DATA", "asset_verification_status": "failed"}`，不执行任何业务逻辑
3. **严禁创建/补写/重建/修复/替换载荷文件** — 生产运行目录只读
4. **EvidenceRef 校验只能在载荷可信验证通过后执行** — `verify_runtime_assets()` 通过后才进入 `validate_evidence_contract()`
5. **测试夹具移至独立测试目录** — 生产代码不得导入
6. **5 项失败测试** — 载荷缺失/哈希错误/测试夹具存在/载荷路径错误/生产目录写入尝试
7. **正常响应新增可信验证字段** — asset_verification_status / verified_paths / verified_hashes / trust_anchor_version

## 审计约束

- 本审计记录不得删除
- 1.0.1 版本标记为存在 P0 可信性缺陷，不再推荐使用
- 任何后续版本必须保留 `verify_runtime_assets()` 启动前置步骤

## 生产载荷零修改证明

- Overview v2.1 SHA256: `2697683F461A555B954BD7E8BF7B0C37A4E9844D82CBCC20FFA1ED2300EF76BD`（未变）
- Event v1.4 SHA256: `53FDC970D7F7EC7B0C46FE9D60F8EE472340FF16ED98A333719F996D67F0AD7B`（未变）
- 测试结果 `payload_intact: true` 确认生产载荷在 04A.3 修复过程中零修改
