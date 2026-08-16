"""
生成质量诊断测试夹具。

每个夹具是一个完整的 BIFROST_DECISION_INPUT_v0.1 合同实例，
覆盖16个测试场景的需求。
"""

import json
import os
import uuid

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)))

# 基础 provenance_ref 模板
def make_provenance(source_field, raw_value, source_data_type, row_num, col_name, col_idx, rule_id="TR-DIRECT"):
    return {
        "source_field": source_field,
        "raw_value": raw_value,
        "source_data_type": source_data_type,
        "transformation_rule_id": rule_id,
        "mapping_ref": {
            "approval_rule_version": "MAP-v1.0.1",
            "match_method": "approved_contract",
            "semantic_model_version": "SEM-v1.1.1",
            "inherited_approval": True,
        },
        "evidence_locator": {
            "source_file_sha256": "abc123def456abc123def456abc123def456abc123def456abc123def456abcd",
            "source_table": "质-不良明细",
            "source_row_number": row_num,
            "source_column_name": col_name,
            "source_column_index": col_idx,
        },
        "note": "raw_value 仅供审计追溯，不得作为消费者业务值使用",
    }

def make_fact(record_key, source_table, source_record_id, field, value, data_type, unit, row_num, col_name, col_idx, rule_id="TR-DIRECT"):
    return {
        "semantic_record_key": record_key,
        "source_table": source_table,
        "source_record_id": source_record_id,
        "semantic_field": field,
        "normalized_value": value,
        "normalized_data_type": data_type,
        "normalized_unit": unit,
        "display_format": "",
        "value_consumption_status": "usable",
        "provenance_ref": make_provenance(col_name, value, data_type, row_num, col_name, col_idx, rule_id),
    }

def make_base_input(request_id, role="quality", facts=None, data_gaps=None):
    return {
        "contract_name": "BIFROST_DECISION_INPUT_v0.1",
        "contract_version": "BIFROST-DECISION-INPUT-v0.1",
        "request_id": request_id,
        "consumer_agent_id": "agent_quality_test",
        "role": role,
        "query_context": {
            "semantic_entity": "defect_detail",
            "source_scope": "P02",
            "requested_fields": [],
            "filters": {},
            "time_window": None,
            "limit": None,
            "semantic_data_ref": {},
            "read_only": True,
        },
        "source_release_id": "BIFROST-SEMANTIC-DATA-PLANE-v0.2-TEST",
        "source_snapshot_id": "SDS-P02-TEST",
        "normalized_facts": facts or [],
        "data_gaps": data_gaps or [],
        "provenance_refs": [],
        "contract_versions": {
            "semantic_model_version": "SEM-v1.1.1",
            "mapping_rule_version": "MAP-v1.0.1",
            "data_contract_version": "BIFROST-SEMANTIC-DATA-v0.1",
            "query_contract_version": "BIFROST-CONSUMER-QUERY-v0.1",
            "decision_input_contract_version": "BIFROST-DECISION-INPUT-v0.1",
            "consumer_logical_version": "0.1.0",
        },
        "validation": {
            "status": "passed",
            "issues": [],
            "normalized_facts_count": len(facts or []),
            "data_gaps_count": len(data_gaps or []),
            "decision_usable_gate_enforced": True,
            "read_only_enforced": True,
            "no_cross_record_join": True,
            "no_business_conclusion": True,
        },
        "source_write_performed": False,
        "actor_can_execute": False,
        "generated_at": "2026-08-10T08:00:00+00:00",
        "local_trace_id": f"FIXTURE-{uuid.uuid4().hex[:8].upper()}",
    }


# =========================================================================
# 1. valid_quality_input - 合规质量输入成功
# =========================================================================
def fixture_valid_quality_input():
    facts = [
        make_fact("质-不良明细#defect_detail#LINE-S03-001", "质-不良明细", "LINE-S03-001", "yield", 0.95, "float", "", 2, "良率", 1),
        make_fact("质-不良明细#defect_detail#LINE-S03-001", "质-不良明细", "LINE-S03-001", "defect_total", 50, "int", "count", 2, "不良总数", 2),
        make_fact("质-不良明细#defect_detail#LINE-S03-001", "质-不良明细", "LINE-S03-001", "total_output", 1000, "int", "count", 2, "总产出", 3),
        make_fact("质-不良明细#defect_detail#LINE-S03-001", "质-不良明细", "LINE-S03-001", "good_output", 950, "int", "count", 2, "良品数", 4),
        make_fact("质-不良明细#defect_detail#LINE-S03-T1", "质-不良明细", "LINE-S03-T1", "defect_type", "外观不良", "str", "", 3, "不良类型", 1),
        make_fact("质-不良明细#defect_detail#LINE-S03-T1", "质-不良明细", "LINE-S03-T1", "defect_count", 30, "int", "count", 3, "不良数量", 2),
        make_fact("质-不良明细#defect_detail#LINE-S03-T1", "质-不良明细", "LINE-S03-T1", "defect_ratio", 0.6, "float", "", 3, "不良占比", 3),
        make_fact("质-不良明细#defect_detail#LINE-S03-T2", "质-不良明细", "LINE-S03-T2", "defect_type", "尺寸超差", "str", "", 4, "不良类型", 1),
        make_fact("质-不良明细#defect_detail#LINE-S03-T2", "质-不良明细", "LINE-S03-T2", "defect_count", 20, "int", "count", 4, "不良数量", 2),
        make_fact("质-不良明细#defect_detail#LINE-S03-T2", "质-不良明细", "LINE-S03-T2", "defect_ratio", 0.4, "float", "", 4, "不良占比", 3),
    ]
    return make_base_input("FIX-VALID-001", facts=facts)


# =========================================================================
# 2. contract_fail_input - 合同失败阻塞
# =========================================================================
def fixture_contract_fail_input():
    facts = [
        make_fact("质-不良明细#defect_detail#CF-001", "质-不良明细", "CF-001", "yield", 0.90, "float", "", 2, "良率", 1),
    ]
    inp = make_base_input("FIX-CONTRACT-FAIL-002", facts=facts)
    # 破坏合同：source_write_performed=true
    inp["source_write_performed"] = True
    # 破坏合同：actor_can_execute=true
    inp["actor_can_execute"] = True
    # 破坏合同：validation.status=failed
    inp["validation"]["status"] = "failed"
    # 破坏合同：加入禁止字段
    inp["conclusion"] = "不应存在的结论"
    return inp


# =========================================================================
# 3. no_evidence_input - 无证据事实不得进入结论
# =========================================================================
def fixture_no_evidence_input():
    facts = [
        make_fact("质-不良明细#defect_detail#NE-001", "质-不良明细", "NE-001", "yield", 0.92, "float", "", 2, "良率", 1),
    ]
    # 删除 provenance_ref 中的 evidence_locator
    for f in facts:
        f["provenance_ref"]["evidence_locator"] = {}
    return make_base_input("FIX-NO-EVIDENCE-003", facts=facts)


# =========================================================================
# 4. defect_conservation_input - 不良数量与占比统计守恒
# =========================================================================
def fixture_defect_conservation_input():
    facts = [
        make_fact("质-不良明细#defect_detail#DC-001", "质-不良明细", "DC-001", "defect_total", 100, "int", "count", 2, "不良总数", 1),
        make_fact("质-不良明细#defect_detail#DC-T1", "质-不良明细", "DC-T1", "defect_type", "外观不良", "str", "", 3, "不良类型", 1),
        make_fact("质-不良明细#defect_detail#DC-T1", "质-不良明细", "DC-T1", "defect_count", 60, "int", "count", 3, "不良数量", 2),
        make_fact("质-不良明细#defect_detail#DC-T1", "质-不良明细", "DC-T1", "defect_ratio", 0.6, "float", "", 3, "不良占比", 3),
        make_fact("质-不良明细#defect_detail#DC-T2", "质-不良明细", "DC-T2", "defect_type", "尺寸超差", "str", "", 4, "不良类型", 1),
        make_fact("质-不良明细#defect_detail#DC-T2", "质-不良明细", "DC-T2", "defect_count", 40, "int", "count", 4, "不良数量", 2),
        make_fact("质-不良明细#defect_detail#DC-T2", "质-不良明细", "DC-T2", "defect_ratio", 0.4, "float", "", 4, "不良占比", 3),
    ]
    return make_base_input("FIX-CONSERVATION-004", facts=facts)


# =========================================================================
# 5. defect_nonconservation_input - 不守恒时产生 data_gap
# =========================================================================
def fixture_defect_nonconservation_input():
    facts = [
        make_fact("质-不良明细#defect_detail#NC-001", "质-不良明细", "NC-001", "defect_total", 100, "int", "count", 2, "不良总数", 1),
        make_fact("质-不良明细#defect_detail#NC-T1", "质-不良明细", "NC-T1", "defect_type", "外观不良", "str", "", 3, "不良类型", 1),
        make_fact("质-不良明细#defect_detail#NC-T1", "质-不良明细", "NC-T1", "defect_count", 70, "int", "count", 3, "不良数量", 2),
        make_fact("质-不良明细#defect_detail#NC-T1", "质-不良明细", "NC-T1", "defect_ratio", 0.7, "float", "", 3, "不良占比", 3),
        make_fact("质-不良明细#defect_detail#NC-T2", "质-不良明细", "NC-T2", "defect_type", "尺寸超差", "str", "", 4, "不良类型", 1),
        make_fact("质-不良明细#defect_detail#NC-T2", "质-不良明细", "NC-T2", "defect_count", 50, "int", "count", 4, "不良数量", 2),
        make_fact("质-不良明细#defect_detail#NC-T2", "质-不良明细", "NC-T2", "defect_ratio", 0.5, "float", "", 4, "不良占比", 3),
    ]
    # sum(counts)=120 != defect_total=100, sum(ratios)=1.2 != 1.0
    return make_base_input("FIX-NONCONSERVATION-005", facts=facts)


# =========================================================================
# 6. no_spc_input - 无测量点/规格限时禁止 Cpk
# =========================================================================
def fixture_no_spc_input():
    facts = [
        make_fact("质-不良明细#defect_detail#NSPC-001", "质-不良明细", "NSPC-001", "yield", 0.88, "float", "", 2, "良率", 1),
        make_fact("质-不良明细#defect_detail#NSPC-001", "质-不良明细", "NSPC-001", "defect_total", 120, "int", "count", 2, "不良总数", 2),
        # 无 spc_measurement_points, usl, lsl
    ]
    return make_base_input("FIX-NO-SPC-006", facts=facts)


# =========================================================================
# 7. with_spc_input - 有完整 SPC 夹具时才允许调用计算接口
# =========================================================================
def fixture_with_spc_input():
    facts = [
        make_fact("质-不良明细#defect_detail#SPC-001", "质-不良明细", "SPC-001", "yield", 0.93, "float", "", 2, "良率", 1),
        make_fact("质-不良明细#defect_detail#SPC-001", "质-不良明细", "SPC-001", "defect_total", 70, "int", "count", 2, "不良总数", 2),
        make_fact("质-不良明细#defect_detail#SPC-001", "质-不良明细", "SPC-001", "spc_measurement_points", "[10.1, 10.2, 9.9, 10.0, 10.1]", "str", "", 2, "SPC测量点", 3),
        make_fact("质-不良明细#defect_detail#SPC-001", "质-不良明细", "SPC-001", "usl", 10.5, "float", "", 2, "规格上限", 4),
        make_fact("质-不良明细#defect_detail#SPC-001", "质-不良明细", "SPC-001", "lsl", 9.5, "float", "", 2, "规格下限", 5),
    ]
    return make_base_input("FIX-WITH-SPC-007", facts=facts)


# =========================================================================
# 8. freeze_no_relation_input - 冻结记录无关联时不得绑定事件
# =========================================================================
def fixture_freeze_no_relation_input():
    facts = [
        make_fact("质-冻结记录#quality_freeze#FR-001", "质-冻结记录", "FR-001", "freeze_id", "FR-2026-001", "str", "", 2, "冻结单号", 1),
        make_fact("质-冻结记录#quality_freeze#FR-001", "质-冻结记录", "FR-001", "freeze_status", "active", "str", "", 2, "冻结状态", 2),
        make_fact("质-冻结记录#quality_freeze#FR-001", "质-冻结记录", "FR-001", "freeze_quantity", 500, "int", "count", 2, "冻结数量", 3),
        make_fact("质-冻结记录#quality_freeze#FR-001", "质-冻结记录", "FR-001", "freeze_reason", "质量异常", "str", "", 2, "冻结原因", 4),
        make_fact("质-冻结记录#quality_freeze#FR-001", "质-冻结记录", "FR-001", "material_code", "MAT-001", "str", "", 2, "物料编码", 5),
        # 无 quality_event_id / event_id / linked_event_ref / relation_ref
    ]
    return make_base_input("FIX-FREEZE-NO-REL-008", facts=facts)


# =========================================================================
# 9. freeze_revoked_input - 已解除/撤回记录不得进入待确认
# =========================================================================
def fixture_freeze_revoked_input():
    facts = [
        make_fact("质-冻结记录#quality_freeze#FR-002", "质-冻结记录", "FR-002", "freeze_id", "FR-2026-002", "str", "", 2, "冻结单号", 1),
        make_fact("质-冻结记录#quality_freeze#FR-002", "质-冻结记录", "FR-002", "freeze_status", "released", "str", "", 2, "冻结状态", 2),
        make_fact("质-冻结记录#quality_freeze#FR-002", "质-冻结记录", "FR-002", "freeze_quantity", 300, "int", "count", 2, "冻结数量", 3),
        make_fact("质-冻结记录#quality_freeze#FR-002", "质-冻结记录", "FR-002", "freeze_reason", "已解除", "str", "", 2, "冻结原因", 4),
        # 另一条活跃冻结
        make_fact("质-冻结记录#quality_freeze#FR-003", "质-冻结记录", "FR-003", "freeze_id", "FR-2026-003", "str", "", 3, "冻结单号", 1),
        make_fact("质-冻结记录#quality_freeze#FR-003", "质-冻结记录", "FR-003", "freeze_status", "active", "str", "", 3, "冻结状态", 2),
        make_fact("质-冻结记录#quality_freeze#FR-003", "质-冻结记录", "FR-003", "freeze_quantity", 200, "int", "count", 3, "冻结数量", 3),
        make_fact("质-冻结记录#quality_freeze#FR-003", "质-冻结记录", "FR-003", "freeze_reason", "待处理", "str", "", 3, "冻结原因", 4),
    ]
    return make_base_input("FIX-FREEZE-REVOKED-009", facts=facts)


# =========================================================================
# 10. unfreeze_request_input - 解除冻结请求只生成确认需求
# =========================================================================
def fixture_unfreeze_request_input():
    facts = [
        make_fact("质-冻结记录#quality_freeze#UF-001", "质-冻结记录", "UF-001", "freeze_id", "FR-2026-004", "str", "", 2, "冻结单号", 1),
        make_fact("质-冻结记录#quality_freeze#UF-001", "质-冻结记录", "UF-001", "freeze_status", "active", "str", "", 2, "冻结状态", 2),
        make_fact("质-冻结记录#quality_freeze#UF-001", "质-冻结记录", "UF-001", "freeze_quantity", 800, "int", "count", 2, "冻结数量", 3),
        make_fact("质-冻结记录#quality_freeze#UF-001", "质-冻结记录", "UF-001", "freeze_reason", "重大质量异常", "str", "", 2, "冻结原因", 4),
        make_fact("质-冻结记录#quality_freeze#UF-001", "质-冻结记录", "UF-001", "material_code", "MAT-002", "str", "", 2, "物料编码", 5),
    ]
    return make_base_input("FIX-UNFREEZE-REQ-010", facts=facts)


# =========================================================================
# 11. reinspect_100pct_input - 100%复检建议不得自动执行
# =========================================================================
def fixture_reinspect_100pct_input():
    facts = [
        make_fact("质-不良明细#defect_detail#RI-001", "质-不良明细", "RI-001", "yield", 0.75, "float", "", 2, "良率", 1),
        make_fact("质-不良明细#defect_detail#RI-001", "质-不良明细", "RI-001", "defect_total", 250, "int", "count", 2, "不良总数", 2),
        make_fact("质-不良明细#defect_detail#RI-001", "质-不良明细", "RI-001", "total_output", 1000, "int", "count", 2, "总产出", 3),
        make_fact("质-不良明细#defect_detail#RI-001", "质-不良明细", "RI-001", "inspection_status", "failed", "str", "", 2, "检验状态", 4),
        make_fact("质-不良明细#defect_detail#RI-001", "质-不良明细", "RI-001", "reinspection_status", "pending", "str", "", 2, "复检状态", 5),
    ]
    return make_base_input("FIX-REINSPECT-100-011", facts=facts)


# =========================================================================
# 12. no_timefield_input - 缺时间字段时不生成趋势结论
# =========================================================================
def fixture_no_timefield_input():
    facts = [
        make_fact("质-不良明细#defect_detail#NT-001", "质-不良明细", "NT-001", "yield", 0.91, "float", "", 2, "良率", 1),
        make_fact("质-不良明细#defect_detail#NT-001", "质-不良明细", "NT-001", "defect_total", 90, "int", "count", 2, "不良总数", 2),
        # 无 record_timestamp / inspection_date / shift_id
    ]
    return make_base_input("FIX-NO-TIME-012", facts=facts)


# =========================================================================
# 13. correlation_input - 相关性不得表述为已验证根因
# =========================================================================
def fixture_correlation_input():
    facts = [
        make_fact("质-不良明细#defect_detail#COR-001", "质-不良明细", "COR-001", "yield", 0.85, "float", "", 2, "良率", 1),
        make_fact("质-不良明细#defect_detail#COR-001", "质-不良明细", "COR-001", "defect_total", 150, "int", "count", 2, "不良总数", 2),
        make_fact("质-不良明细#defect_detail#COR-T1", "质-不良明细", "COR-T1", "defect_type", "焊接不良", "str", "", 3, "不良类型", 1),
        make_fact("质-不良明细#defect_detail#COR-T1", "质-不良明细", "COR-T1", "defect_count", 100, "int", "count", 3, "不良数量", 2),
        make_fact("质-不良明细#defect_detail#COR-T1", "质-不良明细", "COR-T1", "defect_ratio", 0.667, "float", "", 3, "不良占比", 3),
        make_fact("质-不良明细#defect_detail#COR-T2", "质-不良明细", "COR-T2", "defect_type", "组装不良", "str", "", 4, "不良类型", 1),
        make_fact("质-不良明细#defect_detail#COR-T2", "质-不良明细", "COR-T2", "defect_count", 50, "int", "count", 4, "不良数量", 2),
        make_fact("质-不良明细#defect_detail#COR-T2", "质-不良明细", "COR-T2", "defect_ratio", 0.333, "float", "", 4, "不良占比", 3),
        # sum(counts)=150=defect_total ✓, sum(ratios)=1.0 ✓
    ]
    return make_base_input("FIX-CORRELATION-013", facts=facts)


# 生成所有夹具
FIXTURES = {
    "valid_quality_input.json": fixture_valid_quality_input,
    "contract_fail_input.json": fixture_contract_fail_input,
    "no_evidence_input.json": fixture_no_evidence_input,
    "defect_conservation_input.json": fixture_defect_conservation_input,
    "defect_nonconservation_input.json": fixture_defect_nonconservation_input,
    "no_spc_input.json": fixture_no_spc_input,
    "with_spc_input.json": fixture_with_spc_input,
    "freeze_no_relation_input.json": fixture_freeze_no_relation_input,
    "freeze_revoked_input.json": fixture_freeze_revoked_input,
    "unfreeze_request_input.json": fixture_unfreeze_request_input,
    "reinspect_100pct_input.json": fixture_reinspect_100pct_input,
    "no_timefield_input.json": fixture_no_timefield_input,
    "correlation_input.json": fixture_correlation_input,
}

if __name__ == "__main__":
    for filename, fn in FIXTURES.items():
        data = fn()
        path = os.path.join(FIXTURES_DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Generated: {filename} ({len(data['normalized_facts'])} facts)")
    print(f"\nTotal: {len(FIXTURES)} fixtures generated")
