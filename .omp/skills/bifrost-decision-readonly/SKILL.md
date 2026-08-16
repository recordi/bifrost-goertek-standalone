---
name: bifrost-decision-readonly
label: BIFROST决策只读编排
description: BIFROST 制造业多角色决策编排只读闭环。04A.5 版本运行资产自包含修复：将两个批准载荷以 gzip 形式嵌入 Skill 包 references/runtime_assets/ 目录，verify_runtime_assets 仅读取固定包内 gzip 路径，在内存中解压并校验 SHA256/版本/字段，解压内容不写入磁盘。新增 runtime_asset_manifest.json 登记资产元数据。响应增加 asset_source=bundled_gzip_readonly、asset_manifest_version、asset_write_performed 字段。保留04A.4全部业务因果表达修正（OEE直接驱动仅限开动率/性能率/质量因子，物料缺口默认表述为后续生产连续性风险）和04A.3全部可信边界。执行四个确定性 Skill（query_overview_snapshot、query_event_detail、validate_evidence_contract、build_confirmation_draft），基于 Overview v2.1 / Event v1.4 结构化载荷生成六角色动态回答。EvidenceRef 校验只能在载荷可信验证通过后执行。严禁创建/补写/重建/修复或替换载荷文件。当用户需要 BIFROST 决策编排、六角色只读查询、证据契约校验、制造业事件归因分析时使用。
---

# BIFROST 决策只读编排 (v1.0.4)

## 版本历史

- **v1.0.4 (04A.5)** — 运行资产自包含修复：将两个批准载荷以 gzip 形式嵌入 Skill 包 `references/runtime_assets/` 目录（Overview 46.9KB, Event 10.9KB，均 <200KB）；verify_runtime_assets 重写为仅读取固定包内 gzip 路径，使用 `gzip.decompress()` 在内存中解压，对解压字节计算 SHA256 校验，解压内容不写入磁盘；新增 `runtime_asset_manifest.json` 登记资产元数据（original_filename/compressed_filename/payload_version/analysis_version/dataset_id/uncompressed_sha256/compressed_sha256/source_type=TEAM_ENGINEERED_SIMULATION_STATIC_SNAPSHOT）；响应增加 asset_source=bundled_gzip_readonly、asset_manifest_version=1.0.4、asset_write_performed=false；新增 7 项测试（Test 23-29：gzip 大小验证、内存解压成功、gzip 缺失阻塞、gzip 损坏阻塞、哈希不符阻塞、运行前后无新增文件、正式代码无写文件操作）。保留 1.0.3/1.0.4 全部可信边界和业务因果修正。
- **v1.0.3 (04A.4)** — 业务因果表达修正：OEE直接驱动仅限开动率/性能率/质量因子；物料缺口默认表述为"后续生产连续性风险"，仅在存在物料缺口→MATERIALS停机的明确EvidenceRef关联时表述为OEE间接影响；line/factory角色结论区分直接驱动与关联风险；新增 direct_drivers/associated_risks/causal_evidence_level 字段；新增2项因果测试（Test 21-22）。保留04A.3全部可信边界。
- **v1.0.2 (04A.3)** — P0 可信边界修复：新增 verify_runtime_assets 启动前置步骤，固定从批准目录读取载荷，验证 SHA256/版本/字段，失败时阻塞；测试夹具移至独立测试目录；5 项失败测试 + 1 项成功测试；登记 1.0.1 伪造载荷事故。
- **v1.0.1 (04A.2)** — ⚠️ 存在 P0 可信性缺陷，不再推荐使用。在找不到生产载荷时自行构造替代载荷（虚构物理表名、虚构"主轴轴承磨损"、使用测试夹具缺陷比例），基于伪造载荷返回 validation=passed。
- **v1.0.0 (04A.1)** — 初始版本。

## 核心能力

五个确定性 Skill，全部只读，不写回业务事实表：

0. **verify_runtime_assets** (04A.5 重写) — 启动前置步骤：仅读取 Skill 包内固定 gzip 路径 `references/runtime_assets/BIFROST_OVERVIEW_PAYLOAD_v2.1.json.gz` 和 `BIFROST_EVENT_PAYLOAD_v1.4.json.gz`，使用 `gzip.decompress()` 在内存中解压，对解压后原始字节计算 SHA256 校验，验证 payload_version/analysis_version/dataset_id，校验通过后 `json.loads` 内存字节。解压内容不写入磁盘。禁止搜索其他目录。失败时返回 `BLOCKED_INPUT_DATA`。
1. **query_overview_snapshot** — 按 role/line_ids/time_window 查询 Overview v2.1 快照，返回 KPI、趋势、告警。
2. **query_event_detail** — 按 event_id + role 查询 Event v1.4，返回事实(facts)、角色切片(role_slice)、物料结果(material_results)、确认状态。
3. **validate_evidence_contract** — 发布前证据契约深度校验：EvidenceRef 必须解析到物理表名(source_table)、record_key、record_id，验证在载荷 deduplicated_records 中唯一命中且字段值一致。**只能在 verify_runtime_assets 通过后执行。**
4. **build_confirmation_draft** — 高风险动作只生成待确认草稿，prohibited_auto_execute=true。

## 可信边界配置

- **批准的运行资产目录**: Skill 包内 `references/runtime_assets/`（gzip 只读）
- **Overview v2.1 gzip**: `BIFROST_OVERVIEW_PAYLOAD_v2.1.json.gz`（解压后 SHA256: `2697683F461A555B954BD7E8BF7B0C37A4E9844D82CBCC20FFA1ED2300EF76BD`）
- **Event v1.4 gzip**: `BIFROST_EVENT_PAYLOAD_v1.4.json.gz`（解压后 SHA256: `53FDC970D7F7EC7B0C46FE9D60F8EE472340FF16ED98A333719F996D67F0AD7B`）
- **trust_anchor_version**: `1.0.4`
- **asset_manifest_version**: `1.0.4`
- **asset_source**: `bundled_gzip_readonly`
- **asset_write_performed**: `false`
- **内存解压** — gzip 在内存中解压，解压内容不写入磁盘
- **禁止搜索其他目录** — 仅读取固定包内路径
- **生产运行目录只读** — 严禁创建/补写/重建/修复或替换载荷文件
- **测试夹具移至独立测试目录** — 生产代码不得导入

## 正常响应新增字段 (04A.3)

- `asset_verification_status`: 载荷可信验证状态 (passed/failed)
- `verified_paths`: 已验证的载荷文件路径
- `verified_hashes`: 已验证的载荷文件 SHA256
- `trust_anchor_version`: 信任锚版本号

## 运行资产自包含字段 (04A.5)

- `asset_source`: `bundled_gzip_readonly` — 资产来源为包内 gzip 只读
- `asset_manifest_version`: `1.0.4` — 资产清单版本
- `asset_write_performed`: `false` — 运行时未执行任何写文件操作

## 业务因果表达字段 (04A.4)

- `direct_drivers`: OEE直接驱动因素列表（开动率/性能率/质量因子），每项含值、证据、evidence_refs、is_direct=true
- `associated_risks`: 关联风险列表，物料缺口默认为 `production_continuity_risk`；存在→MATERIALS停机明确EvidenceRef关联时为 `indirect_oee_impact`
- `causal_evidence_level`: 因果证据等级
  - `direct_verified`: 停机/质量证据存在（开动率/质量因子下降已验证）
  - `indirect_verified`: 物料缺口→MATERIALS停机关联已验证
  - `insufficient`: 无充分因果证据

### 因果表达规则

1. OEE直接驱动只允许：开动率、性能率、质量因子
2. 非计划停机作为开动率下降的证据
3. 不良作为质量因子下降的证据
4. 物料缺口默认表述为"后续生产连续性风险"
5. 仅当存在物料缺口→MATERIALS停机的明确EvidenceRef关联时，表述为OEE间接影响

## 编排入口

`scripts/bifrost_skills.py` 的 `orchestrate_response(request, aily_run_id=None)` 是统一编排入口：
- 启动时先执行 `verify_runtime_assets()`，失败则返回 `BLOCKED_INPUT_DATA`
- `local_trace_id`：本地确定性追踪号（LT- 前缀），不冒充 Aily RunID
- `aily_run_id`：真实 Aily 执行 RunID，由 Aily Workflow / 调用方注入

## 使用方式

```bash
# CLI 调用
python scripts/bifrost_skills.py --request-json req.json --aily-run-id <real_run_id>

# Python 调用
from scripts.bifrost_skills import orchestrate_response
result = orchestrate_response(request, aily_run_id='run_xxx')
```

## 关键约束

- 六角色回答零字面量：所有数值从 facts/role_slice/material_results 动态读取。
- **载荷可信验证优先于一切**：verify_runtime_assets 失败时，不执行任何业务逻辑，不创建任何文件。
- EvidenceRef 校验只能在载荷可信验证通过后执行。
- 知识库只保存公式/语义/权限/规则。
- 测试夹具在 `tests/fixtures/` 目录（独立于生产代码），生产代码不得导入。

## 测试

`scripts/test_runner.py` 执行 29 项验收测试（14 项 04A.2 测试 + 6 项 04A.3 可信边界测试 + 2 项 04A.4 因果表达测试 + 7 项 04A.5 运行资产自包含测试），记录真实 Aily RunID、WorkflowID、时间戳、耗时、错误状态，保存脱敏请求/响应。

04A.3 新增测试：
- Test 15: 载荷缺失 → 阻塞且不创建文件
- Test 16: 哈希错误 → 阻塞
- Test 17: 测试夹具存在 → 正式运行不读取
- Test 18: 载荷路径错误 → 不得搜索其他目录
- Test 19: 生产目录写入尝试 → 必须失败
- Test 20: 正确载荷成功测试

04A.4 新增测试：
- Test 21: 物料缺口存在但无MATERIALS停机关联 → 不得称为OEE直接原因（risk_type=production_continuity_risk, causal_evidence_level=direct_verified）
- Test 22: 有明确物料→MATERIALS停机关联 → 只能称为间接影响（risk_type=indirect_oee_impact, causal_evidence_level=indirect_verified）

04A.5 新增测试：
- Test 23: gzip 文件大小验证（均 <200KB）
- Test 24: 正常内存解压成功·解压后哈希完全一致
- Test 25: gzip 缺失时阻塞（BLOCKED_INPUT_DATA）
- Test 26: gzip 损坏时阻塞（BLOCKED_INPUT_DATA）
- Test 27: 解压后哈希不符时阻塞（BLOCKED_INPUT_DATA）
- Test 28: 运行前后目录无新增文件
- Test 29: 正式代码不调用写文件操作

```bash
AILY_RUN_ID=<real_run_id> python scripts/test_runner.py
```
