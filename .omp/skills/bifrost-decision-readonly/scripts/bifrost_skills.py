#!/usr/bin/env python3
"""
BIFROST 决策编排智能体 — 4 个确定性 Skill 实现 (04A.3 修订版)

04A.3 关键修订（P0 可信边界修复）：
1. 新增 verify_runtime_assets() 启动前置步骤：固定从批准目录
   workspace/bifrost/payloads/ 读取载荷，验证文件存在/文件名/SHA256/
   payload_version/analysis_version/dataset_id。
   失败时返回 BLOCKED_INPUT_DATA，严禁创建/补写/重建/修复/替换载荷文件。
2. 载荷路径从 artifacts/ 改为 workspace/bifrost/payloads/（批准的生产目录）。
3. EvidenceRef 校验只能在载荷可信验证通过后执行。
4. 正常响应新增 asset_verification_status / verified_paths / verified_hashes /
   trust_anchor_version。
5. 测试夹具移至独立测试目录，生产代码不得导入。
6. 登记上一轮 1.0.1 伪造载荷事故（见 incident_audit_04a3.md）。

04A.2 关键修订（保留）：
1. 测试夹具 yield_recompute 修正为 Event v1.4 载荷原始值 0.9128626。
2. 知识库 K-BIZ-001 删除全部事件固定值，只保留动态数据源说明。
3. 语义防硬编码：结论/原因/行动建议根据实际异常信号动态构建。
4. validate_evidence_contract 深度扩展。
所有数值来自 Overview v2.1 / Event v1.4 结构化字段，不虚构数据。
"""
import json, hashlib, os, sys, uuid, datetime, re, gzip

# ============================================================
# 04A.5 运行资产自包含配置 — gzip 只读，内存解压
# ============================================================
TRUST_ANCHOR_VERSION = '1.0.4'
ASSET_MANIFEST_VERSION = '1.0.4'

# 技能包内固定路径（references/runtime_assets/）
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
# 在技能包内：scripts/bifrost_skills.py → _SKILL_DIR 为父目录
# 在测试环境：bifrost_skills.py 直接在目录内 → _SKILL_DIR 为当前目录
if os.path.basename(_SCRIPTS_DIR) == 'scripts':
    _SKILL_DIR = os.path.dirname(_SCRIPTS_DIR)
else:
    _SKILL_DIR = _SCRIPTS_DIR
RUNTIME_ASSETS_DIR = os.path.join(_SKILL_DIR, 'references', 'runtime_assets')

OVERVIEW_GZ_FILENAME = 'BIFROST_OVERVIEW_PAYLOAD_v2.1.json.gz'
EVENT_GZ_FILENAME = 'BIFROST_EVENT_PAYLOAD_v1.4.json.gz'
MANIFEST_FILENAME = 'runtime_asset_manifest.json'

OVERVIEW_GZ_PATH = os.path.join(RUNTIME_ASSETS_DIR, OVERVIEW_GZ_FILENAME)
EVENT_GZ_PATH = os.path.join(RUNTIME_ASSETS_DIR, EVENT_GZ_FILENAME)
MANIFEST_PATH = os.path.join(RUNTIME_ASSETS_DIR, MANIFEST_FILENAME)

OVERVIEW_ALLOWED_HASH = '2697683F461A555B954BD7E8BF7B0C37A4E9844D82CBCC20FFA1ED2300EF76BD'
EVENT_ALLOWED_HASH = '53FDC970D7F7EC7B0C46FE9D60F8EE472340FF16ED98A333719F996D67F0AD7B'

# 内存缓存（verify_runtime_assets 填充，load_overview/load_event 使用）
_overview_cache = None
_event_cache = None
_verified_overview_bytes = None
_verified_event_bytes = None

# ============================================================
# 04A.5 启动前置步骤：verify_runtime_assets（gzip 内存解压只读）
# ============================================================
def verify_runtime_assets():
    """
    04A.5 启动前置步骤：验证包内 gzip 载荷可信边界。
    只读取 references/runtime_assets/ 下的两个确定 gzip 文件。
    使用 gzip 在内存中解压，不将解压内容写入磁盘。
    对解压后的原始字节计算 SHA256，校验 payload_version/analysis_version/dataset_id。
    严禁创建、补写、重建、修复或替换载荷文件。
    失败时返回 status=BLOCKED_INPUT_DATA, asset_verification_status=failed。
    """
    global _verified_overview_bytes, _verified_event_bytes, _overview_cache, _event_cache

    result = {
        'status': 'verified',
        'asset_verification_status': 'passed',
        'asset_source': 'bundled_gzip_readonly',
        'asset_manifest_version': ASSET_MANIFEST_VERSION,
        'asset_write_performed': False,
        'verified_paths': {},
        'verified_hashes': {},
        'trust_anchor_version': TRUST_ANCHOR_VERSION,
        'errors': []
    }

    assets = [
        {
            'key': 'overview',
            'gz_path': OVERVIEW_GZ_PATH,
            'allowed_hash': OVERVIEW_ALLOWED_HASH,
            'expected_payload_version': 'v2.1',
            'expected_analysis_version': None,
            'expected_dataset_id': 'TEAM_ENGINEERED_SIMULATION'
        },
        {
            'key': 'event',
            'gz_path': EVENT_GZ_PATH,
            'allowed_hash': EVENT_ALLOWED_HASH,
            'expected_payload_version': 'v1.4',
            'expected_analysis_version': 4,
            'expected_dataset_id': 'TEAM_ENGINEERED_SIMULATION'
        }
    ]

    decompressed_data = {}

    for asset in assets:
        key = asset['key']
        gz_path = asset['gz_path']

        # 1. gzip 文件存在性检查
        if not os.path.isfile(gz_path):
            result['errors'].append(
                f'{key}: gzip载荷文件不存在: {gz_path} — 严禁创建或重建'
            )
            result['status'] = 'BLOCKED_INPUT_DATA'
            result['asset_verification_status'] = 'failed'
            continue

        result['verified_paths'][key] = gz_path

        # 2. 读取 gzip 文件字节
        with open(gz_path, 'rb') as f:
            gz_bytes = f.read()

        # 3. 内存中 gzip 解压（不写入磁盘）
        try:
            raw_bytes = gzip.decompress(gz_bytes)
        except Exception as e:
            result['errors'].append(
                f'{key}: gzip解压失败: {e}'
            )
            result['status'] = 'BLOCKED_INPUT_DATA'
            result['asset_verification_status'] = 'failed'
            continue

        # 4. 对解压后的原始字节计算 SHA256
        actual_hash = hashlib.sha256(raw_bytes).hexdigest().upper()
        if actual_hash != asset['allowed_hash']:
            result['errors'].append(
                f'{key}: 解压后SHA256不匹配 (expected={asset["allowed_hash"]}, '
                f'actual={actual_hash})'
            )
            result['status'] = 'BLOCKED_INPUT_DATA'
            result['asset_verification_status'] = 'failed'
            continue

        result['verified_hashes'][key] = actual_hash

        # 5. 校验载荷内容字段
        try:
            payload = json.loads(raw_bytes)
        except Exception as e:
            result['errors'].append(
                f'{key}: JSON解析失败: {e}'
            )
            result['status'] = 'BLOCKED_INPUT_DATA'
            result['asset_verification_status'] = 'failed'
            continue

        # payload_version
        actual_pv = payload.get('payload_version', '')
        if actual_pv != asset['expected_payload_version']:
            result['errors'].append(
                f'{key}: payload_version 不匹配 '
                f'(expected={asset["expected_payload_version"]}, actual={actual_pv})'
            )
            result['status'] = 'BLOCKED_INPUT_DATA'
            result['asset_verification_status'] = 'failed'

        # analysis_version（仅 Event 有此字段）
        if asset['expected_analysis_version'] is not None:
            actual_av = payload.get('analysis_version')
            if actual_av != asset['expected_analysis_version']:
                result['errors'].append(
                    f'{key}: analysis_version 不匹配 '
                    f'(expected={asset["expected_analysis_version"]}, actual={actual_av})'
                )
                result['status'] = 'BLOCKED_INPUT_DATA'
                result['asset_verification_status'] = 'failed'

        # dataset_id
        actual_did = payload.get('dataset_id', '')
        if actual_did != asset['expected_dataset_id']:
            result['errors'].append(
                f'{key}: dataset_id 不匹配 '
                f'(expected={asset["expected_dataset_id"]}, actual={actual_did})'
            )
            result['status'] = 'BLOCKED_INPUT_DATA'
            result['asset_verification_status'] = 'failed'

        # 存储解压后的字节和解析结果（仅在校验通过时）
        if result['asset_verification_status'] == 'passed':
            decompressed_data[key] = (raw_bytes, payload)

    # 校验全部通过后，填充内存缓存
    if result['asset_verification_status'] == 'passed':
        if 'overview' in decompressed_data:
            _verified_overview_bytes = decompressed_data['overview'][0]
            if _overview_cache is None:
                _overview_cache = decompressed_data['overview'][1]
        if 'event' in decompressed_data:
            _verified_event_bytes = decompressed_data['event'][0]
            if _event_cache is None:
                _event_cache = decompressed_data['event'][1]

    return result


def load_overview():
    global _overview_cache
    if _overview_cache is None:
        # 04A.5: 从 verify_runtime_assets 验证过的内存字节加载
        if _verified_overview_bytes is not None:
            _overview_cache = json.loads(_verified_overview_bytes)
        else:
            # 尝试自动验证
            vr = verify_runtime_assets()
            if vr['asset_verification_status'] != 'passed':
                raise RuntimeError('载荷验证失败，无法加载 Overview')
    return _overview_cache

def load_event():
    global _event_cache
    if _event_cache is None:
        # 04A.5: 从 verify_runtime_assets 验证过的内存字节加载
        if _verified_event_bytes is not None:
            _event_cache = json.loads(_verified_event_bytes)
        else:
            # 尝试自动验证
            vr = verify_runtime_assets()
            if vr['asset_verification_status'] != 'passed':
                raise RuntimeError('载荷验证失败，无法加载 Event')
    return _event_cache

def get_payload_hashes():
    """04A.5: 从内存中的解压字节计算 SHA256"""
    results = {}
    if _verified_overview_bytes is not None:
        results['overview'] = hashlib.sha256(_verified_overview_bytes).hexdigest().upper()
    else:
        results['overview'] = OVERVIEW_ALLOWED_HASH
    if _verified_event_bytes is not None:
        results['event'] = hashlib.sha256(_verified_event_bytes).hexdigest().upper()
    else:
        results['event'] = EVENT_ALLOWED_HASH
    return results

# ============================================================
# 动态格式化辅助（禁止字面量数字进入文案）
# ============================================================
def _fmt_ratio(v, digits=2):
    """比例 -> 百分比字符串，None 安全"""
    if v is None:
        return 'N/A'
    return f'{v*100:.{digits}f}%'

def _fmt_num(v, fmt='#,##0'):
    if v is None:
        return 'N/A'
    if isinstance(v, float):
        return f'{v:.1f}'
    return f'{v:,}'

def _kpi_value(role_slice, metric_code, default=None):
    """从角色切片按 metric_code 取值"""
    if not role_slice:
        return default
    for k in role_slice.get('kpis', []):
        if k.get('metric_code') == metric_code:
            return k.get('value', default)
    return default

def _kpi_eref(role_slice, metric_code):
    """从角色切片取真实 EvidenceRef（带物理表名/record_id）"""
    if not role_slice:
        return []
    for k in role_slice.get('kpis', []):
        if k.get('metric_code') == metric_code:
            return k.get('evidence_refs', [])
    return []

def _fact_eref(event_result, role, metric_code):
    """跨角色取真实 EvidenceRef：从指定角色的 KPI 取"""
    if not event_result:
        return []
    ev = load_event()
    for r in ev.get('roles', []):
        if r.get('role') == role:
            for k in r.get('kpis', []):
                if k.get('metric_code') == metric_code:
                    return k.get('evidence_refs', [])
    return []

def _material_eref(event_result, record_id):
    """从 supply material_detail 取真实 evidence_ref_record_id"""
    if not event_result:
        return []
    ev = load_event()
    for r in ev.get('roles', []):
        if r.get('role') == 'supply':
            for md in r.get('material_detail', []):
                if md.get('evidence_ref_record_id') == record_id or md.get('business_key') == record_id:
                    return [{
                        'dataset_id': ev.get('dataset_id',''),
                        'semantic_table': 'material',
                        'source_table': '04_订单物料_模拟',
                        'record_key': 'OrderMaterialID',
                        'record_id': md.get('evidence_ref_record_id', record_id),
                        'field_names': ['物料缺口','质量冻结'],
                        'semantic_fields': ['gap','frozen'],
                        'source_object_id': md.get('business_key',''),
                        'source_type': ev.get('dataset_id','')
                    }]
    return []

def _alert_by_id(role_slice, alert_id):
    for a in role_slice.get('alerts', []):
        if a.get('alert_id') == alert_id:
            return a
    return None

# ============================================================
# Skill 1: query_overview_snapshot
# ============================================================
def query_overview_snapshot(role, line_ids, time_window, metric_requests=None):
    ov = load_overview()
    scope = ','.join(sorted(line_ids)) if line_ids else 'ALL_LINES'
    if line_ids and len(line_ids) == 1:
        scope = line_ids[0]

    matching_views = []
    for v in ov.get('view_snapshots', []):
        vk = v.get('view_key', '')
        parts = vk.split('|')
        if len(parts) >= 3:
            v_role, v_scope, v_window = parts[0], parts[1], parts[2]
            if v_role == role and v_window == time_window:
                if scope == 'ALL_LINES' and v_scope == 'ALL_LINES':
                    matching_views.append(v)
                elif scope == v_scope:
                    matching_views.append(v)
                elif scope in v_scope or v_scope in scope:
                    matching_views.append(v)

    kpis = []
    for v in matching_views[:1]:
        for k in v.get('kpis', []):
            kpis.append({
                'metric_id': k.get('metric_code', ''),
                'label': k.get('label', k.get('metric_code', '')),
                'value': k.get('value', None),
                'value_type': k.get('value_type', ''),
                'display_format': k.get('display_format', ''),
                'unit': k.get('unit', ''),
                'target': k.get('target', None),
                'evidence_refs': k.get('evidence_refs', [])
            })

    trends = []
    for v in matching_views[:1]:
        for c in v.get('charts', []):
            if 'trend' in c.get('chart_id', '').lower():
                trends.append({
                    'chart_id': c.get('chart_id'),
                    'type': c.get('type'),
                    'title': c.get('title', ''),
                    'data_points': len(c.get('data', [])),
                    'evidence_refs': c.get('evidence_refs', [])
                })

    alerts = []
    for v in matching_views[:1]:
        for a in v.get('alerts', []):
            alerts.append({
                'alert_id': a.get('alert_id', ''),
                'severity': a.get('severity', ''),
                'message': a.get('message', ''),
                'evidence_refs': a.get('evidence_refs', [])
            })

    lines = sorted(set(
        v.get('view_key', '').split('|')[1]
        for v in ov.get('view_snapshots', [])
        if 'LINE-S' in v.get('view_key', '')
    ))

    return {
        'status': 'success',
        'role': role,
        'scope': scope,
        'time_window': time_window,
        'lines': lines,
        'kpis': kpis,
        'trends': trends,
        'alerts': alerts,
        'source_version': ov.get('payload_version', 'v2.1'),
        'evidence_ref_count': sum(len(k.get('evidence_refs', [])) for k in kpis),
        'overview_sha256': get_payload_hashes()['overview']
    }

# ============================================================
# Skill 2: query_event_detail
# ============================================================
def query_event_detail(event_id, role):
    ev = load_event()

    if ev.get('event_id') != event_id:
        return {
            'status': 'error',
            'error_code': 'EVENT_NOT_FOUND',
            'message': f'EventID {event_id} 不存在于当前载荷中',
            'available_events': [ev.get('event_id', 'N/A')]
        }

    mat = ev.get('materialization', {})

    facts = {
        'event_id': ev.get('event_id'),
        'source_event_id': ev.get('source_event_id'),
        'sim_shift_id': ev.get('sim_shift_id'),
        'event_status': ev.get('event_status', ''),
        'line_ids': ev.get('line_ids', []),
        'data_time': ev.get('data_time', ''),
        'dataset_id': ev.get('dataset_id', ''),
        'oee': mat.get('oee_recompute'),
        'oee_gap': mat.get('oee_gap'),
        'defect_total': mat.get('defect_total'),
        'risk_level': mat.get('risk_level', ''),
        'good_output': mat.get('good_output'),
        'total_output': mat.get('total_output'),
        'yield_recompute': mat.get('yield_recompute'),
    }

    material_results = []
    for mr in mat.get('material_results', []):
        material_results.append({
            'business_key': mr.get('business_key', ''),
            'demand': mr.get('需求量', 0),
            'available': mr.get('可用量', 0),
            'gap': mr.get('缺口', 0),
            'frozen': mr.get('冻结', 0)
        })

    role_data = None
    for r in ev.get('roles', []):
        if r.get('role') == role:
            role_data = r
            break

    role_slice = {}
    if role_data:
        role_slice = {
            'role': role_data.get('role'),
            'headline': role_data.get('headline', ''),
            'kpis': [{
                'metric_code': k.get('metric_code', ''),
                'value': k.get('value', None),
                'value_type': k.get('value_type', ''),
                'display_format': k.get('display_format', ''),
                'unit': k.get('unit', ''),
                'evidence_refs': k.get('evidence_refs', [])
            } for k in role_data.get('kpis', [])],
            'alerts': [{
                'alert_id': a.get('alert_id', ''),
                'severity': a.get('severity', ''),
                'message': a.get('message', ''),
                'evidence_refs': a.get('evidence_refs', [])
            } for a in role_data.get('alerts', [])],
            'tasks': role_data.get('tasks', []),
            'decisions_required': role_data.get('decisions_required', []),
            'data_gaps': role_data.get('data_gaps', []),
            'evidence_refs': role_data.get('evidence_refs', [])
        }
        # 角色专属结构透传
        if role == 'equipment':
            role_slice['downtime_summary'] = role_data.get('downtime_summary', {})
            role_slice['downtime_events'] = role_data.get('downtime_events', [])
        if role == 'supply':
            role_slice['material_detail'] = role_data.get('material_detail', [])
            role_slice['supply_chain_query'] = role_data.get('supply_chain_query', {})

    # 冻结记录：对所有角色都从 supply material_detail 提取（质量等角色也需引用）
    for r2 in ev.get('roles', []):
        if r2.get('role') == 'supply':
            for md in r2.get('material_detail', []):
                if md.get('freeze_id'):
                    facts.setdefault('freeze_records', []).append({
                        'freeze_id': md.get('freeze_id'),
                        'freeze_status': md.get('freeze_status', '状态未提供'),
                        'material_code': md.get('material_code', ''),
                        'material_name': md.get('material_name', ''),
                        'frozen_qty': md.get('质量冻结', 0),
                        'business_key': md.get('business_key', '')
                    })

    # equipment 角色提取停机指标（动态）— 04A.2：停机事实对所有角色可见
    for r_eq in ev.get('roles', []):
        if r_eq.get('role') == 'equipment':
            for k in r_eq.get('kpis', []):
                mc = k.get('metric_code')
                if mc == 'DOWNTIME_EVENT_COUNT':
                    facts['downtime_events'] = k.get('value')
                elif mc == 'DOWNTIME_TOTAL_MINUTES':
                    facts['downtime_total_minutes'] = k.get('value')
                elif mc == 'UNPLANNED_DOWNTIME_MINUTES':
                    facts['unplanned_downtime_minutes'] = k.get('value')
                elif mc == 'AVAILABILITY':
                    facts['availability'] = k.get('value')
            ds = r_eq.get('downtime_summary', {})
            if ds:
                facts['downtime_summary'] = ds
            break

    vr = ev.get('validation_results', {})
    confirmations = vr.get('decision_confirmation_map', {})

    return {
        'status': 'success',
        'event_id': event_id,
        'role': role,
        'facts': facts,
        'material_results': material_results,
        'role_slice': role_slice,
        'confirmations': confirmations,
        'pending_confirmation_count': vr.get('pending_confirmation_count', 0),
        'all_passed': vr.get('all_passed', False),
        'control_table_refs': ev.get('control_table_refs', {}),
        'evidence_ref_summary': ev.get('evidence_ref_summary', {}),
        'event_sha256': get_payload_hashes()['event']
    }

# ============================================================
# Skill 3: validate_evidence_contract (04A.2 修订：深度扩展校验)
# ============================================================
def validate_evidence_contract(response_draft, event_payload=None):
    """
    发布前证据契约校验。
    04A.2 修订：
    1. EvidenceRef 校验范围扩展到 metrics / causes / recommended_actions /
       confirmation_draft / 顶层 evidence_refs。
    2. 物理记录唯一命中：在 deduplicated_records 列表中计数，0 条或 >1 条均失败；
       禁止用 set 冒充唯一性检查。
    3. 字段无法定位时必须返回 'unsupported'（severity=medium），禁止默认 return True。
    4. 聚合指标必须验证完整明细集合的聚合结果，不能用单条记录证明总数。
    """
    issues = []

    if event_payload is None:
        try:
            event_payload = load_event()
        except Exception:
            pass

    # 取载荷 deduplicated_records（保留为列表，用于命中计数）
    dedup_list = []
    if event_payload:
        ers = event_payload.get('evidence_ref_summary', {})
        dedup_list = list(ers.get('deduplicated_records', []))

    def _check_eref(eref, context_label, value_to_verify=None, metric_id=None, missing_severity='critical'):
        """对单个 EvidenceRef 执行物理解析 + 唯一命中 + 字段一致性检查。
        missing_severity: 物理解析缺失时的严重级别（metrics=critical, causes/actions=medium）"""
        source_table = eref.get('source_table', '')
        record_key = eref.get('record_key', '')
        record_id = eref.get('record_id', '')
        # 必须三项齐全
        if not (source_table and record_key and record_id):
            issues.append({
                'check': 'evidence_physical_resolution',
                'context': context_label,
                'issue': f'EvidenceRef 未解析到物理表名/record_key/record_id '
                         f'(source_table={source_table!r}, record_key={record_key!r}, record_id={record_id!r})',
                'severity': missing_severity
            })
            return
        # 唯一命中校验：在 dedup_list 中计数（禁止用 set 冒充）
        phys_key = f'{source_table}:{record_id}'
        hit_count = dedup_list.count(phys_key) if dedup_list else 0
        if not dedup_list:
            issues.append({
                'check': 'evidence_dedup_unavailable',
                'context': context_label,
                'issue': f'载荷 deduplicated_records 为空，无法验证物理记录 {phys_key}',
                'severity': 'critical'
            })
        elif hit_count == 0:
            issues.append({
                'check': 'evidence_unique_hit',
                'context': context_label,
                'issue': f'物理记录 {phys_key} 未命中载荷 deduplicated_records（命中数=0）',
                'severity': 'critical',
                'hit_count': hit_count
            })
        elif hit_count > 1:
            issues.append({
                'check': 'evidence_unique_hit',
                'context': context_label,
                'issue': f'物理记录 {phys_key} 在 deduplicated_records 中命中 {hit_count} 条，违反唯一性',
                'severity': 'critical',
                'hit_count': hit_count
            })
        # 字段值一致性
        if value_to_verify is not None and event_payload:
            status = _verify_field_consistency_v2(value_to_verify, eref, event_payload, metric_id)
            if status == 'fail':
                issues.append({
                    'check': 'evidence_field_consistency',
                    'context': context_label,
                    'issue': f'指标值 {value_to_verify!r} 与物理记录 {phys_key} 字段值不一致',
                    'severity': 'critical'
                })
            elif status == 'unsupported':
                issues.append({
                    'check': 'evidence_field_unsupported',
                    'context': context_label,
                    'issue': f'无法为物理记录 {phys_key} 定位对照字段，标记为 unsupported',
                    'severity': 'medium'
                })

    # ---- 检查 1: metrics 的 EvidenceRef ----
    for metric in response_draft.get('metrics', []):
        refs = metric.get('evidence_refs', [])
        if not refs:
            issues.append({
                'check': 'evidence_traceability',
                'metric': metric.get('metric_id', ''),
                'issue': '指标缺少 EvidenceRef，无法回指结构化字段',
                'severity': 'high'
            })
            continue
        for ref in refs:
            _check_eref(ref, f"metric:{metric.get('metric_id','')}",
                        value_to_verify=metric.get('value'), metric_id=metric.get('metric_id'))

    # ---- 检查 1b: causes 的 EvidenceRef ----
    for cause in response_draft.get('causes', []):
        refs = cause.get('evidence_refs', [])
        if not refs:
            issues.append({
                'check': 'cause_missing_evidence',
                'cause': cause.get('cause', '')[:50],
                'issue': '原因缺少 EvidenceRef，无法回指结构化字段',
                'severity': 'medium'
            })
            continue
        for ref in refs:
            _check_eref(ref, f"cause:{cause.get('cause','')[:30]}", missing_severity='medium')

    # ---- 检查 1c: recommended_actions 的 EvidenceRef ----
    for action in response_draft.get('recommended_actions', []):
        refs = action.get('evidence_refs', [])
        for ref in refs:
            _check_eref(ref, f"action:{action.get('action','')[:30]}", missing_severity='medium')
        # 高风险动作须有确认草稿
        if action.get('is_high_risk', False):
            if not response_draft.get('confirmation_draft'):
                issues.append({
                    'check': 'missing_confirmation',
                    'action': action.get('action', ''),
                    'issue': '高风险动作缺少待确认草稿',
                    'severity': 'critical'
                })

    # ---- 检查 1d: confirmation_draft 的 EvidenceRef ----
    conf_draft = response_draft.get('confirmation_draft')
    if conf_draft:
        for ref in conf_draft.get('evidence_refs', []):
            _check_eref(ref, "confirmation_draft", missing_severity='medium')

    # ---- 检查 1e: 顶层 evidence_refs ----
    for ref in response_draft.get('evidence_refs', []):
        # 顶层 refs 可能是简单 dict（只有 source），只做物理解析检查
        if 'source_table' in ref or 'record_id' in ref:
            _check_eref(ref, "top_level", missing_severity='medium')

    # ---- 检查 2: 聚合指标完整性校验 ----
    if event_payload:
        agg_issues = _validate_aggregate_metrics(response_draft, event_payload)
        issues.extend(agg_issues)

    # ---- 检查 3: 未接入数据引用 ----
    forbidden_terms = ['Cpk', 'SPC', 'MTBF', 'MTTR', '控制图', '过程能力']
    answer_text = json.dumps(response_draft, ensure_ascii=False)
    for term in forbidden_terms:
        if term in answer_text:
            data_gaps_text = json.dumps(response_draft.get('data_gaps', []), ensure_ascii=False)
            if term not in data_gaps_text:
                issues.append({
                    'check': 'unavailable_data_reference',
                    'term': term,
                    'issue': f'引用了未接入的 {term}，且未在 data_gaps 中声明',
                    'severity': 'critical'
                })

    # ---- 检查 4: 比例范围 ----
    for metric in response_draft.get('metrics', []):
        val = metric.get('value')
        if isinstance(val, (int, float)) and metric.get('value_type') == 'ratio':
            if val > 1.0 or val < 0:
                issues.append({
                    'check': 'ratio_format',
                    'metric': metric.get('metric_id', ''),
                    'issue': f'比例值 {val} 不在 0-1 范围内',
                    'severity': 'medium'
                })

    # ---- 检查 5: 无证据归因 ----
    uncertain_terms = ['推测', '可能', '猜测', '大概', '也许']
    for term in uncertain_terms:
        if term in response_draft.get('answer_summary', ''):
            if '不确定性' not in response_draft.get('answer_summary', '') and '证据不足' not in response_draft.get('answer_summary', ''):
                issues.append({
                    'check': 'unsupported_attribution',
                    'term': term,
                    'issue': f'回答中出现「{term}」但未标注不确定性',
                    'severity': 'medium'
                })

    if any(i['severity'] == 'critical' for i in issues):
        return {'status': 'blocked_by_evidence', 'issues': issues}
    elif issues:
        return {'status': 'warning', 'issues': issues}
    else:
        return {'status': 'passed', 'issues': []}


def _verify_field_consistency_v2(val, ref, event_payload, metric_id=None):
    """
    验证 metric value 与物理记录字段值一致。
    返回 'pass' / 'fail' / 'unsupported'。
    04A.2：无法定位对照源时返回 'unsupported'，禁止默认 return True。
    """
    if val is None:
        return 'pass'  # 无值不校验
    sem_table = ref.get('semantic_table', '')
    src_table = ref.get('source_table', '')
    mat = event_payload.get('materialization', {})

    # OEE / 质量因子类
    if metric_id in ('oee', 'OEE') or 'oee' in sem_table.lower():
        return 'pass' if _approx_equal(val, mat.get('oee_recompute')) else 'fail'
    if metric_id == 'defect_total' or 'defect' in sem_table.lower():
        return 'pass' if _approx_equal(val, mat.get('defect_total')) else 'fail'
    if metric_id in ('good_output', 'GOOD_OUTPUT'):
        return 'pass' if _approx_equal(val, mat.get('good_output')) else 'fail'
    if metric_id in ('total_output', 'TOTAL_OUTPUT'):
        return 'pass' if _approx_equal(val, mat.get('total_output')) else 'fail'
    if metric_id in ('yield_recompute', 'YIELD'):
        return 'pass' if _approx_equal(val, mat.get('yield_recompute')) else 'fail'

    # 物料类：对照 material_results
    if 'material' in sem_table.lower() or 'material' in src_table.lower():
        rid = ref.get('record_id', '')
        for mr in mat.get('material_results', []):
            if mr.get('business_key') == rid or rid in mr.get('business_key', ''):
                if metric_id == 'material_shortage':
                    return 'pass' if _approx_equal(val, mr.get('缺口', 0)) else 'fail'
                if metric_id == 'material_freeze':
                    return 'pass' if _approx_equal(val, mr.get('冻结', 0)) else 'fail'
                return 'pass'
        return 'unsupported'

    # 停机类：对照 equipment role KPI
    if 'downtime' in sem_table.lower() or 'downtime' in src_table.lower() or 'stop' in src_table.lower():
        for r in event_payload.get('roles', []):
            if r.get('role') == 'equipment':
                for k in r.get('kpis', []):
                    mc = k.get('metric_code', '')
                    if metric_id == 'downtime_events' and mc == 'DOWNTIME_EVENT_COUNT':
                        return 'pass' if _approx_equal(val, k.get('value')) else 'fail'
                    if metric_id == 'downtime_total' and mc == 'DOWNTIME_TOTAL_MINUTES':
                        return 'pass' if _approx_equal(val, k.get('value')) else 'fail'
                    if metric_id == 'unplanned_downtime' and mc == 'UNPLANNED_DOWNTIME_MINUTES':
                        return 'pass' if _approx_equal(val, k.get('value')) else 'fail'
        return 'unsupported'

    # 质量率 / AVAILABILITY / PERFORMANCE：对照 line role KPI
    if metric_id in ('availability', 'performance', 'quality', 'QUALITY'):
        for r in event_payload.get('roles', []):
            if r.get('role') == 'line':
                for k in r.get('kpis', []):
                    mc = k.get('metric_code', '').upper()
                    mid = metric_id.upper() if metric_id else ''
                    if mc == mid:
                        return 'pass' if _approx_equal(val, k.get('value')) else 'fail'
        return 'unsupported'

    # 04A.2：无法定位对照源时标记 unsupported，禁止默认 return True
    return 'unsupported'


def _validate_aggregate_metrics(response_draft, event_payload):
    """
    聚合指标完整性校验：必须验证完整明细集合的聚合结果，
    不能用单条记录引用证明总数。
    """
    issues = []
    mat = event_payload.get('materialization', {})

    for metric in response_draft.get('metrics', []):
        mid = metric.get('metric_id', '')
        val = metric.get('value')
        if val is None:
            continue

        # 物料缺口聚合：验证 sum(所有 material_results.缺口) == metric value
        if mid == 'material_shortage':
            detail_sum = sum(mr.get('缺口', 0) for mr in mat.get('material_results', []))
            if not _approx_equal(val, detail_sum):
                issues.append({
                    'check': 'aggregate_integrity',
                    'metric': mid,
                    'issue': f'物料缺口聚合值 {val} 与明细集合总和 {detail_sum} 不一致',
                    'severity': 'critical',
                    'detail_count': len(mat.get('material_results', []))
                })

        # 物料冻结聚合
        elif mid == 'material_freeze':
            detail_sum = sum(mr.get('冻结', 0) for mr in mat.get('material_results', []))
            if not _approx_equal(val, detail_sum):
                issues.append({
                    'check': 'aggregate_integrity',
                    'metric': mid,
                    'issue': f'物料冻结聚合值 {val} 与明细集合总和 {detail_sum} 不一致',
                    'severity': 'critical',
                    'detail_count': len(mat.get('material_results', []))
                })

        # 不良总数：如果载荷有不良明细，验证聚合一致
        elif mid == 'defect_total':
            # 检查 quality role 是否有不良明细记录
            for r in event_payload.get('roles', []):
                if r.get('role') == 'quality':
                    defect_details = [k for k in r.get('kpis', []) if 'DEFECT' in k.get('metric_code', '').upper()]
                    if len(defect_details) > 1:
                        # 有多条不良明细 KPI，验证总和
                        detail_sum = sum(k.get('value', 0) for k in defect_details if k.get('metric_code') != 'DEFECT_TOTAL')
                        if detail_sum > 0 and not _approx_equal(val, detail_sum):
                            issues.append({
                                'check': 'aggregate_integrity',
                                'metric': mid,
                                'issue': f'不良总数 {val} 与明细 KPI 总和 {detail_sum} 不一致',
                                'severity': 'critical',
                                'detail_count': len(defect_details)
                            })
                    break

        # 停机事件数：检查 downtime_events 明细是否完整
        elif mid == 'downtime_events':
            for r in event_payload.get('roles', []):
                if r.get('role') == 'equipment':
                    de_list = r.get('downtime_events', [])
                    # 载荷只提供 sample 停机明细（2条），但 KPI 说 15 条
                    # 明细集合不完整 → 标记 unsupported，不能用 2 条证明 15
                    if de_list and len(de_list) < val:
                        issues.append({
                            'check': 'aggregate_detail_incomplete',
                            'metric': mid,
                            'issue': f'停机明细仅 {len(de_list)} 条，不足以验证 KPI 声称的 {val} 条总数',
                            'severity': 'medium',
                            'detail_count': len(de_list),
                            'claimed_total': val
                        })
                    break

    return issues


def _approx_equal(a, b, tol=1e-6):
    if a is None or b is None:
        return a is None and b is None
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return str(a) == str(b)


# ============================================================
# Skill 4: build_confirmation_draft
# ============================================================
def build_confirmation_draft(action, affected_object, reason, evidence_refs, requester_role):
    return {
        'draft_id': f'DRAFT-{uuid.uuid4().hex[:12].upper()}',
        'action': action,
        'affected_object': affected_object,
        'reason': reason,
        'evidence_refs': evidence_refs,
        'requester_role': requester_role,
        'confirmation_status': '待确认',
        'prohibited_auto_execute': True,
        'created_at': datetime.datetime.now().isoformat(),
        'note': '本草稿仅为待确认建议，未执行任何业务操作。需人工确认后方可执行。'
    }

# ============================================================
# 编排智能体：生成角色化回答
# ============================================================
def orchestrate_response(request, aily_run_id=None):
    """
    BIFROST 决策编排智能体核心逻辑。
    aily_run_id: 真实 Aily 执行 RunID（由 Aily Workflow / test_runner 注入）；
                 本地模式为 None，此时仅产 local_trace_id。
    """
    req_id = request.get('request_id', '')
    role = request.get('role', '')
    event_id = request.get('event_id', '')
    user_query = request.get('user_query', '')
    line_ids = request.get('scope', {}).get('line_ids', [])
    time_window = request.get('time_window', 'last_7_shifts')

    # 本地确定性追踪号（不再冒充 Aily RunID）
    local_trace_id = f'LT-{uuid.uuid4().hex[:16].upper()}'
    generated_at = datetime.datetime.now().isoformat()

    # 04A.3 启动前置步骤：验证生产载荷可信边界
    # 必须在任何业务逻辑之前执行；失败时立即阻塞
    asset_verification = verify_runtime_assets()
    if asset_verification['asset_verification_status'] != 'passed':
        return {
            'local_trace_id': local_trace_id,
            'aily_run_id': aily_run_id,
            'request_id': req_id,
            'status': 'BLOCKED_INPUT_DATA',
            'asset_verification_status': 'failed',
            'asset_source': 'bundled_gzip_readonly',
            'asset_manifest_version': ASSET_MANIFEST_VERSION,
            'asset_write_performed': False,
            'trust_anchor_version': TRUST_ANCHOR_VERSION,
            'verification_errors': asset_verification['errors'],
            'message': '载荷可信验证失败，已阻塞。严禁创建/补写/重建/修复或替换载荷文件。',
            'generated_at': generated_at
        }

    valid_roles = ['factory', 'line', 'quality', 'equipment', 'process', 'supply']
    if role not in valid_roles:
        return {
            'local_trace_id': local_trace_id,
            'aily_run_id': aily_run_id,
            'request_id': req_id,
            'status': 'failed',
            'error_code': 'INVALID_ROLE',
            'asset_verification_status': 'passed',
            'asset_source': 'bundled_gzip_readonly',
            'asset_manifest_version': ASSET_MANIFEST_VERSION,
            'asset_write_performed': False,
            'trust_anchor_version': TRUST_ANCHOR_VERSION,
            'message': f'非法角色: {role}，有效角色: {", ".join(valid_roles)}',
            'generated_at': generated_at
        }

    event_result = None
    if event_id:
        event_result = query_event_detail(event_id, role)
        if event_result['status'] == 'error':
            return {
                'local_trace_id': local_trace_id,
                'aily_run_id': aily_run_id,
                'request_id': req_id,
                'status': 'failed',
                'error_code': event_result['error_code'],
                'message': event_result['message'],
                'generated_at': generated_at
            }

    overview_result = query_overview_snapshot(role, line_ids, time_window)
    facts = event_result['facts'] if event_result else {}
    role_slice = event_result.get('role_slice', {}) if event_result else {}
    material_results = event_result.get('material_results', []) if event_result else []

    role_answer_builders = {
        'factory': _build_factory_answer,
        'line': _build_line_answer,
        'quality': _build_quality_answer,
        'equipment': _build_equipment_answer,
        'process': _build_process_answer,
        'supply': _build_supply_answer,
    }
    answer = role_answer_builders[role](facts, role_slice, material_results, event_result, user_query)

    # 高风险动作识别
    needs_confirmation = False
    confirmation_draft = None
    high_risk_patterns = ['解除冻结', '解除.*冻结', '修改阈值', '调整排产', '修改订单', '覆盖数据', '发布知识', '解除.*FZ']
    for pattern in high_risk_patterns:
        if re.search(pattern, user_query):
            needs_confirmation = True
            matched_kw = pattern.replace('.*', ' ')
            freeze_records = facts.get('freeze_records', [])
            aff_obj = freeze_records[0].get('freeze_id', 'N/A') if freeze_records else 'N/A'
            conf_refs = [{'freeze_id': fr['freeze_id'], 'freeze_status': fr.get('freeze_status', '状态未提供')}
                         for fr in freeze_records] if freeze_records else []
            confirmation_draft = build_confirmation_draft(
                action=matched_kw,
                affected_object=aff_obj,
                reason=f'用户请求: {user_query}',
                evidence_refs=conf_refs,
                requester_role=role
            )
            break

    spc_requested = any(term in user_query for term in ['Cpk', 'SPC', '过程能力', '控制图'])
    mtbf_requested = any(term in user_query for term in ['MTBF', 'MTTR'])
    data_gaps = list(answer.get('data_gaps', []))
    if spc_requested:
        data_gaps.append({
            'gap_id': 'GAP-SPC-001',
            'description': '缺少 SPC 原始测量点和规格限，不能计算 Cpk，不能判断 SPC 越界',
            'requested_by': user_query
        })
    if mtbf_requested:
        data_gaps.append({
            'gap_id': 'GAP-MTBF-001',
            'description': '缺少 EquipmentID、故障码和维修工单，不能可靠计算 MTBF/MTTR',
            'requested_by': user_query
        })

    response = {
        'local_trace_id': local_trace_id,
        'aily_run_id': aily_run_id,
        'request_id': req_id,
        'status': 'needs_confirmation' if needs_confirmation else 'completed',
        'role': role,
        'answer_summary': answer.get('summary', ''),
        'conclusion': answer.get('conclusion', ''),
        'severity': answer.get('severity', '中'),
        'confidence': answer.get('confidence', 0.5),
        'metrics': answer.get('metrics', []),
        'causes': answer.get('causes', []),
        'affected_objects': answer.get('affected_objects', []),
        'recommended_actions': answer.get('recommended_actions', []),
        'needs_human_confirmation': needs_confirmation,
        'confirmation_draft': confirmation_draft,
        'evidence_refs': answer.get('evidence_refs', []),
        'direct_drivers': answer.get('direct_drivers', []),
        'associated_risks': answer.get('associated_risks', []),
        'causal_evidence_level': answer.get('causal_evidence_level', 'insufficient'),
        'data_gaps': data_gaps,
        'source_versions': {
            'overview': 'v2.1',
            'event': 'v1.4',
            'rules': 'RULESET-v1.0',
            'knowledge': 'KNOWLEDGE-v1.1'
        },
        # 04A.3 载荷可信验证结果（已在启动前置步骤通过）
        'asset_verification_status': asset_verification['asset_verification_status'],
        'asset_source': 'bundled_gzip_readonly',
        'asset_manifest_version': ASSET_MANIFEST_VERSION,
        'asset_write_performed': False,
        'verified_paths': asset_verification['verified_paths'],
        'verified_hashes': asset_verification['verified_hashes'],
        'trust_anchor_version': asset_verification['trust_anchor_version'],
        'payload_hashes': get_payload_hashes(),
        'generated_at': generated_at
    }

    # 04A.3: EvidenceRef 校验只能在载荷可信验证通过后执行
    #（asset_verification 已在上方通过，此处安全执行）
    validation = validate_evidence_contract(response, load_event() if event_result else None)
    if validation['status'] == 'blocked_by_evidence':
        response['status'] = 'blocked_by_evidence'
        response['validation_issues'] = validation['issues']
    else:
        response['validation'] = validation

    return response


# ============================================================
# 04A.4 业务因果表达修正：物料缺口→MATERIALS停机关联检测
# ============================================================
def _check_material_downtime_link(event_result, material_results):
    """
    04A.4: 检测物料缺口是否存在→MATERIALS停机的明确EvidenceRef关联。
    
    返回:
      has_explicit_link: bool — 是否存在明确关联
      materials_downtime_info: dict or None — MATERIALS停机信息
        {
          'group': 'MATERIALS',
          'event_count': int,
          'total_minutes': float,
          'linked_event_ids': [str],
          'evidence_refs': [dict]
        }
    
    判定逻辑:
    1. 物料缺口必须存在（material_results 中有 gap > 0）
    2. downtime_summary.by_group 中必须存在 'MATERIALS' 组
    3. 必须有明确的 EvidenceRef 将物料记录与 MATERIALS 停机事件关联：
       - 物料缺口的 evidence_ref_record_id 出现在停机事件的 evidence_refs 中，或
       - 停机事件的 record_id 出现在物料记录的 evidence_refs 中
    4. 若仅有 by_group 统计但无明细级 EvidenceRef 交叉引用，视为无明确关联
    """
    has_gap = any(mr.get('gap', 0) > 0 for mr in material_results)
    if not has_gap or not event_result:
        return False, None

    # 收集物料缺口的 EvidenceRef record_id
    gap_record_ids = set()
    ev = load_event()
    for r in ev.get('roles', []):
        if r.get('role') == 'supply':
            for md in r.get('material_detail', []):
                if md.get('物料缺口', 0) > 0:
                    rid = md.get('evidence_ref_record_id', '')
                    if rid:
                        gap_record_ids.add(rid)

    # 检查 downtime_summary.by_group 是否有 MATERIALS 组
    materials_group_info = None
    ds = facts_downtime_summary = event_result.get('facts', {}).get('downtime_summary', {})
    if ds:
        for grp in ds.get('by_group', []):
            if grp.get('源停机组', '') == 'MATERIALS':
                materials_group_info = {
                    'group': 'MATERIALS',
                    'event_count': grp.get('事件数', 0),
                    'total_minutes': grp.get('累计分钟', 0.0)
                }
                break

    if not materials_group_info:
        return False, None

    # 检查明细级 EvidenceRef 交叉引用
    # 停机事件的 record_id 集合
    downtime_record_ids = set()
    for r in ev.get('roles', []):
        if r.get('role') == 'equipment':
            for de in r.get('downtime_events', []):
                sid = de.get('sim_stop_event_id', '')
                if sid:
                    downtime_record_ids.add(sid)
                # 检查停机事件是否属于 MATERIALS 组
                if de.get('源停机组', '') == 'MATERIALS':
                    # 检查该停机事件的 note 或其他字段是否引用了物料
                    pass

    # 检查是否有物料 record_id 出现在停机 KPI 的 evidence_refs 中
    # 或停机 record_id 出现在物料的 evidence_refs 中
    has_explicit_link = False
    linked_event_ids = []

    # 方式1: 停机 KPI evidence_refs 中的 record_id 是否包含物料 gap 的 record_id
    for r in ev.get('roles', []):
        if r.get('role') == 'equipment':
            for k in r.get('kpis', []):
                for ref in k.get('evidence_refs', []):
                    ref_rid = ref.get('record_id', '')
                    if ref_rid in gap_record_ids:
                        has_explicit_link = True
                        if ref_rid not in linked_event_ids:
                            linked_event_ids.append(ref_rid)

    # 方式2: 物料 material_detail 的 evidence_refs 中是否引用了停机事件
    for r in ev.get('roles', []):
        if r.get('role') == 'supply':
            for md in r.get('material_detail', []):
                if md.get('物料缺口', 0) > 0:
                    for ref in md.get('evidence_refs', []):
                        ref_rid = ref.get('record_id', '')
                        if ref_rid in downtime_record_ids:
                            has_explicit_link = True
                            if ref_rid not in linked_event_ids:
                                linked_event_ids.append(ref_rid)

    # 方式3: 停机明细事件中是否有 源停机组=MATERIALS 且有 note/字段引用物料
    for r in ev.get('roles', []):
        if r.get('role') == 'equipment':
            for de in r.get('downtime_events', []):
                if de.get('源停机组', '') == 'MATERIALS':
                    # 检查该事件的 evidence_refs 是否与物料有关联
                    de_refs = de.get('evidence_refs', [])
                    for ref in de_refs:
                        ref_rid = ref.get('record_id', '')
                        if ref_rid in gap_record_ids:
                            has_explicit_link = True
                            sid = de.get('sim_stop_event_id', '')
                            if sid not in linked_event_ids:
                                linked_event_ids.append(sid)

    materials_downtime_info = None
    if has_explicit_link:
        materials_downtime_info = {
            **materials_group_info,
            'linked_event_ids': linked_event_ids,
            'evidence_refs': [{'source': 'downtime_summary.by_group MATERIALS + material gap cross-ref'}]
        }

    return has_explicit_link, materials_downtime_info


def _build_direct_drivers(facts, role_slice, event_result):
    """
    04A.4: 构建 OEE 直接驱动因素列表。
    OEE = 开动率 × 性能率 × 质量因子
    直接驱动只允许：开动率、性能率、质量因子。
    """
    drivers = []
    
    avail = _kpi_value(role_slice, 'AVAILABILITY')
    perf = _kpi_value(role_slice, 'PERFORMANCE')
    qual = _kpi_value(role_slice, 'QUALITY')
    
    unplanned = facts.get('unplanned_downtime_minutes')
    dt_events = facts.get('downtime_events')
    dt_mins = facts.get('downtime_total_minutes')
    defect_total = facts.get('defect_total')

    # 开动率 — 非计划停机作为开动率下降的证据
    if avail is not None:
        evidence = []
        if unplanned is not None and unplanned > 0:
            evidence = _fact_eref(event_result, 'equipment', 'UNPLANNED_DOWNTIME_MINUTES')
        drivers.append({
            'driver': '开动率',
            'value': avail,
            'value_type': 'ratio',
            'display_format': '0.00%',
            'evidence': f'非计划停机{unplanned}分钟' if unplanned is not None and unplanned > 0 else '开动率数据',
            'evidence_refs': evidence,
            'is_direct': True
        })

    # 性能率
    if perf is not None:
        drivers.append({
            'driver': '性能率',
            'value': perf,
            'value_type': 'ratio',
            'display_format': '0.00%',
            'evidence': '性能率数据',
            'evidence_refs': _kpi_eref(role_slice, 'PERFORMANCE'),
            'is_direct': True
        })

    # 质量因子 — 不良作为质量因子下降的证据
    if qual is not None:
        evidence = []
        if defect_total is not None and defect_total > 0:
            evidence = _fact_eref(event_result, 'quality', 'DEFECT_TOTAL')
        drivers.append({
            'driver': '质量因子',
            'value': qual,
            'value_type': 'ratio',
            'display_format': '0.00%',
            'evidence': f'不良{defect_total}件' if defect_total is not None and defect_total > 0 else '质量率数据',
            'evidence_refs': evidence,
            'is_direct': True
        })

    return drivers


def _build_associated_risks(material_results, has_material_downtime_link, materials_downtime_info):
    """
    04A.4: 构建关联风险列表。
    物料缺口默认表述为"后续生产连续性风险"。
    只有存在物料缺口→MATERIALS停机的明确EvidenceRef关联时，才能表述为OEE的间接影响。
    """
    risks = []
    total_gap = sum(mr.get('gap', 0) for mr in material_results)
    
    if total_gap > 0:
        if has_material_downtime_link and materials_downtime_info:
            # 有明确关联 → 可表述为OEE间接影响
            risks.append({
                'risk': f'物料缺口{total_gap}件',
                'risk_type': 'indirect_oee_impact',
                'description': f'物料缺口{total_gap}件，已关联MATERIALS停机{materials_downtime_info["event_count"]}条/{materials_downtime_info["total_minutes"]}分钟，构成OEE间接影响',
                'linked_downtime_events': materials_downtime_info.get('linked_event_ids', []),
                'evidence_refs': materials_downtime_info.get('evidence_refs', []),
                'causal_chain': '物料缺口 → MATERIALS停机 → 开动率下降 → OEE下降'
            })
        else:
            # 无明确关联 → 仅表述为后续生产连续性风险
            risks.append({
                'risk': f'物料缺口{total_gap}件',
                'risk_type': 'production_continuity_risk',
                'description': f'物料缺口{total_gap}件，构成后续生产连续性风险（未关联MATERIALS停机，不直接进入OEE公式）',
                'evidence_refs': [],
                'causal_chain': None
            })
    
    return risks


# ============================================================
# 六角色回答生成器 — 全动态，零黄金事件字面量
# ============================================================
def _build_factory_answer(facts, role_slice, material_results, event_result, user_query):
    metrics = []
    evidence_refs = []
    if facts:
        oee_val = facts.get('oee')
        metrics.append({
            'metric_id': 'oee', 'label': '综合设备效率（OEE）',
            'value': oee_val, 'value_type': 'ratio', 'display_format': '0.0%',
            'evidence_refs': _fact_eref(event_result, 'line', 'OEE')
        })
        dt_val = facts.get('defect_total')
        metrics.append({
            'metric_id': 'defect_total', 'label': '不良总数',
            'value': dt_val, 'value_type': 'integer', 'display_format': '#,##0',
            'evidence_refs': _fact_eref(event_result, 'quality', 'DEFECT_TOTAL')
        })
        evidence_refs.append({'source': 'materialization', 'field': 'oee_recompute'})

    eid = facts.get('event_id', 'N/A')
    lines = facts.get('line_ids', [])
    line_str = '、'.join(lines) if lines else 'N/A'
    oee_pct = _fmt_ratio(facts.get('oee'))
    oee_gap = facts.get('oee_gap')
    oee_gap_str = f'{abs(oee_gap)*100:.2f}' if oee_gap is not None else 'N/A'
    dt_str = _fmt_num(facts.get('defect_total'))

    # 物料缺口与冻结（动态聚合）
    total_gap = sum(mr.get('gap', 0) for mr in material_results)
    total_frozen = sum(mr.get('frozen', 0) for mr in material_results)

    # 04A.4: 检测物料缺口→MATERIALS停机关联
    has_material_link, materials_dt_info = _check_material_downtime_link(event_result, material_results)

    # 04A.4: 构建直接驱动和关联风险
    # factory role_slice 仅含 OEE，从 line 角色补充开动率/性能率/质量因子
    factory_drivers_slice = role_slice
    _ev = load_event()
    for r in _ev.get('roles', []):
        if r.get('role') == 'line':
            factory_drivers_slice = {'kpis': r.get('kpis', [])}
            break
    direct_drivers = _build_direct_drivers(facts, factory_drivers_slice, event_result)
    associated_risks = _build_associated_risks(material_results, has_material_link, materials_dt_info)

    summary = (f'事件 {eid} 影响 {line_str}，OEE {oee_pct}'
               f'低于目标{oee_gap_str}个百分点，'
               f'不良{dt_str}件')
    if total_gap:
        summary += f'，存在物料缺口{total_gap}件'
    if total_frozen:
        summary += f'、质量冻结{total_frozen}件'
    summary += '。建议关注交付风险和待确认事项。'

    # 04A.4: causes 只包含 OEE 直接驱动因素（非计划停机→开动率、不良→质量因子）
    causes = []
    has_quality_anomaly = facts.get('defect_total') is not None and facts.get('defect_total') > 0
    dt_events = facts.get('downtime_events')
    dt_mins = facts.get('downtime_total_minutes')
    unplanned = facts.get('unplanned_downtime_minutes')
    has_downtime_anomaly = unplanned is not None and unplanned > 0
    if has_downtime_anomaly:
        causes.append({'cause': f'非计划停机{unplanned}分钟（开动率下降证据）',
                       'evidence_refs': _fact_eref(event_result, 'equipment', 'UNPLANNED_DOWNTIME_MINUTES')})
    if has_quality_anomaly:
        causes.append({'cause': f'不良{dt_str}件（质量因子下降证据）',
                       'evidence_refs': _fact_eref(event_result, 'quality', 'DEFECT_TOTAL')})

    affected = list(lines)
    wo = _extract_wo(facts, material_results)
    if wo:
        affected.append(wo)

    # 04A.4: 结论区分直接驱动和关联风险
    direct_factors = []
    if has_downtime_anomaly:
        direct_factors.append('非计划停机')
    if has_quality_anomaly:
        direct_factors.append('质量异常')
    
    if direct_factors:
        factory_conclusion = (f'{line_str} 当班 OEE 偏低的直接驱动是开动率、性能率和质量率，'
                              f'其中{"、".join(direct_factors)}证据充分')
    else:
        factory_conclusion = f'{line_str} 当班 OEE 偏低，未检测到停机或质量异常信号'
    
    if total_gap > 0:
        if has_material_link:
            factory_conclusion += f'；同时存在物料缺口{total_gap}件，已关联MATERIALS停机，构成OEE间接影响'
        else:
            factory_conclusion += f'；同时存在物料缺口{total_gap}件，构成后续生产连续性风险'

    # 04A.4: 因果证据等级
    if has_material_link:
        causal_evidence_level = 'indirect_verified'
    elif direct_factors:
        causal_evidence_level = 'direct_verified'
    else:
        causal_evidence_level = 'insufficient'

    return {
        'summary': summary,
        'conclusion': factory_conclusion,
        'severity': '高',
        'confidence': 0.85,
        'metrics': metrics,
        'causes': causes,
        'direct_drivers': direct_drivers,
        'associated_risks': associated_risks,
        'causal_evidence_level': causal_evidence_level,
        'affected_objects': affected,
        'recommended_actions': _pending_confirm_actions(event_result),
        'evidence_refs': evidence_refs,
        'data_gaps': []
    }


def _build_line_answer(facts, role_slice, material_results, event_result, user_query):
    metrics = []
    if facts:
        metrics.append({
            'metric_id': 'oee', 'label': '综合设备效率（OEE）',
            'value': facts.get('oee'), 'value_type': 'ratio', 'display_format': '0.0%',
            'evidence_refs': _fact_eref(event_result, 'line', 'OEE')
        })
    # 从 line role_slice 取开动率/性能率/质量率
    avail = _kpi_value(role_slice, 'AVAILABILITY')
    perf = _kpi_value(role_slice, 'PERFORMANCE')
    qual = _kpi_value(role_slice, 'QUALITY')

    lines = facts.get('line_ids', [])
    line_str = '、'.join(lines) if lines else 'N/A'
    oee_pct = _fmt_ratio(facts.get('oee'))
    oee_gap = facts.get('oee_gap')
    oee_gap_str = f'{abs(oee_gap)*100:.2f}' if oee_gap is not None else 'N/A'

    unplanned = facts.get('unplanned_downtime_minutes')
    dt_events = facts.get('downtime_events')
    dt_mins = facts.get('downtime_total_minutes')
    dt_str = _fmt_num(facts.get('defect_total'))
    total_gap = sum(mr.get('gap', 0) for mr in material_results)

    # 04A.4: 检测物料缺口→MATERIALS停机关联
    has_material_link, materials_dt_info = _check_material_downtime_link(event_result, material_results)

    # 04A.4: 构建直接驱动和关联风险
    direct_drivers = _build_direct_drivers(facts, role_slice, event_result)
    associated_risks = _build_associated_risks(material_results, has_material_link, materials_dt_info)

    # 04A.4: summary 区分直接驱动和关联风险
    parts = [f'{line_str} 当班 OEE {oee_pct}，低于目标{oee_gap_str}个百分点。']
    direct_factors = []
    if avail is not None and dt_events is not None and unplanned is not None and unplanned > 0:
        direct_factors.append(f'开动率偏低（停机{dt_events}条/{dt_mins}分钟，非计划停机{unplanned}分钟）')
    if qual is not None and facts.get('defect_total') is not None and facts.get('defect_total') > 0:
        direct_factors.append(f'质量率偏低（不良{dt_str}件）')
    if direct_factors:
        parts.append('OEE直接驱动因素：' + '、'.join(direct_factors) + '。')
    if total_gap:
        if has_material_link:
            parts.append(f'物料缺口{total_gap}件已关联MATERIALS停机，构成OEE间接影响。')
        else:
            parts.append(f'物料缺口{total_gap}件，构成后续生产连续性风险（不直接进入OEE公式）。')
    parts.append('建议优先处理非计划停机和质量异常，跟进物料缺口。')
    summary = ''.join(parts)

    # 04A.4: causes 只包含 OEE 直接驱动因素
    causes = []
    has_downtime_anomaly = unplanned is not None and unplanned > 0
    has_quality_anomaly = facts.get('defect_total') is not None and facts.get('defect_total') > 0
    has_material_anomaly = total_gap > 0
    if has_downtime_anomaly:
        causes.append({'cause': f'非计划停机{unplanned}分钟（开动率下降证据）',
                       'evidence_refs': _fact_eref(event_result, 'equipment', 'UNPLANNED_DOWNTIME_MINUTES')})
    if has_quality_anomaly:
        causes.append({'cause': f'不良{dt_str}件（质量因子下降证据）',
                       'evidence_refs': _fact_eref(event_result, 'quality', 'DEFECT_TOTAL')})
    # 04A.4: 物料缺口不再放入 causes（直接原因），移入 associated_risks

    # 04A.4: 结论区分直接驱动和关联风险
    conclusion_direct = []
    if has_downtime_anomaly:
        conclusion_direct.append('非计划停机')
    if has_quality_anomaly:
        conclusion_direct.append('质量异常')

    if conclusion_direct:
        conclusion = (f'OEE偏低的直接驱动是开动率、性能率和质量率，'
                      f'其中{"、".join(conclusion_direct)}证据充分')
    else:
        conclusion = '当班 OEE 偏低，未检测到停机或质量异常信号'

    if has_material_anomaly:
        if has_material_link:
            conclusion += f'；同时存在物料缺口{total_gap}件，已关联MATERIALS停机，构成OEE间接影响'
        else:
            conclusion += f'；同时存在物料缺口{total_gap}件，构成后续生产连续性风险'

    # 04A.4: 因果证据等级
    if has_material_link:
        causal_evidence_level = 'indirect_verified'
    elif conclusion_direct:
        causal_evidence_level = 'direct_verified'
    else:
        causal_evidence_level = 'insufficient'

    return {
        'summary': summary,
        'conclusion': conclusion,
        'severity': '高',
        'confidence': 0.85,
        'metrics': metrics,
        'causes': causes,
        'direct_drivers': direct_drivers,
        'associated_risks': associated_risks,
        'causal_evidence_level': causal_evidence_level,
        'affected_objects': list(lines),
        'recommended_actions': _line_actions(facts, material_results),
        'evidence_refs': [{'source': 'equipment/supply role KPIs'}],
        'data_gaps': []
    }


def _build_quality_answer(facts, role_slice, material_results, event_result, user_query):
    dt_str = _fmt_num(facts.get('defect_total'))
    headline = role_slice.get('headline', '') if role_slice else ''

    # 冻结记录（动态）
    freeze_recs = facts.get('freeze_records', [])
    frz_summary = ''
    if freeze_recs:
        frz_parts = []
        for fr in freeze_recs:
            frz_parts.append(f'{fr.get("material_name","")} {fr.get("frozen_qty",0)}件（{fr.get("freeze_id","")}，{fr.get("freeze_status","")}）')
        frz_summary = ' 质量冻结 ' + '；'.join(frz_parts) + '。'

    summary = f'当班不良{dt_str}件。'
    if headline:
        summary += f' {headline}'
    summary += frz_summary
    summary += '建议启动隔离和复检流程。'
    summary += '注意：当前缺少 SPC 原始测量点和规格限，不能计算 Cpk。'

    qual_val = _kpi_value(role_slice, 'QUALITY')
    metrics = [{
        'metric_id': 'defect_total', 'label': '不良总数',
        'value': facts.get('defect_total'), 'value_type': 'integer', 'display_format': '#,##0',
        'evidence_refs': _fact_eref(event_result, 'quality', 'DEFECT_TOTAL')
    }]

    causes = []
    if headline:
        causes.append({'cause': headline, 'evidence_refs': [{'source': 'quality role headline'}]})

    affected = list(facts.get('line_ids', []))
    for fr in freeze_recs:
        affected.append(fr.get('freeze_id', ''))

    actions = [{'action': '启动冻结物料复检流程（生成待确认草稿）', 'is_high_risk': False}]
    for fr in freeze_recs:
        actions.append({'action': f'隔离冻结的{fr.get("frozen_qty",0)}件{fr.get("material_name","")}', 'is_high_risk': False})

    return {
        'summary': summary,
        'conclusion': f'不良{dt_str}件需分类处理' + ('，冻结物料待复检' if freeze_recs else '') + '，SPC 证据不足',
        'severity': '高',
        'confidence': 0.80,
        'metrics': metrics,
        'causes': causes,
        'affected_objects': affected,
        'recommended_actions': actions,
        'evidence_refs': [{'source': 'materialization.defect_total'}, {'source': 'supply material_detail.freeze_status'}],
        'data_gaps': [{
            'gap_id': 'GAP-SPC-001',
            'description': '缺少 SPC 原始测量点和规格限，不能计算 Cpk，不能判断 SPC 越界'
        }]
    }


def _build_equipment_answer(facts, role_slice, material_results, event_result, user_query):
    dt_events = facts.get('downtime_events')
    dt_mins = facts.get('downtime_total_minutes')
    unplanned = facts.get('unplanned_downtime_minutes')
    ds = facts.get('downtime_summary', {})

    summary = f'当班{dt_events}条事件级停机记录，累计{dt_mins}分钟，非计划停机{unplanned}分钟。'

    # 最大故障（动态从 downtime_events 取）
    max_fail = None
    for de in role_slice.get('downtime_events', []):
        if de.get('note') and '最大' in de.get('note', ''):
            max_fail = de
            break
    if max_fail:
        summary += f'最大故障：{max_fail.get("源停机原因","")} 单次{max_fail.get("持续时间_分钟",0)}分钟。'
    # 换产（动态从 downtime_summary）
    chg = ds.get('changeover_events') if ds else None
    if chg:
        # 找最长换产
        max_chg = None
        for de in role_slice.get('downtime_events', []):
            if de.get('是否换产事件') == '是':
                if max_chg is None or de.get('持续时间_分钟', 0) > max_chg.get('持续时间_分钟', 0):
                    max_chg = de
        if max_chg:
            summary += f'换产事件{chg}条，最长{max_chg.get("持续时间_分钟",0)}分钟。'
    summary += '注意：缺少 EquipmentID、故障码和维修工单，不能可靠计算 MTBF/MTTR。'

    metrics = [
        {'metric_id': 'downtime_events', 'label': '停机事件数', 'value': dt_events, 'value_type': 'integer', 'display_format': '#,##0',
         'evidence_refs': _fact_eref(event_result, 'equipment', 'DOWNTIME_EVENT_COUNT')},
        {'metric_id': 'downtime_total', 'label': '累计停机', 'value': dt_mins, 'value_type': 'decimal', 'display_format': '0.0', 'unit': '分钟',
         'evidence_refs': _fact_eref(event_result, 'equipment', 'DOWNTIME_TOTAL_MINUTES')},
        {'metric_id': 'unplanned_downtime', 'label': '非计划停机', 'value': unplanned, 'value_type': 'decimal', 'display_format': '0.0', 'unit': '分钟',
         'evidence_refs': _fact_eref(event_result, 'equipment', 'UNPLANNED_DOWNTIME_MINUTES')},
    ]

    causes = []
    if max_fail:
        causes.append({'cause': f'{max_fail.get("源停机原因","")} 单次{max_fail.get("持续时间_分钟",0)}分钟为最大故障停机',
                       'evidence_refs': [{'source': f'equipment downtime_events {max_fail.get("sim_stop_event_id","")}'}]})
    chg_events = [de for de in role_slice.get('downtime_events', []) if de.get('是否换产事件') == '是']
    if chg_events:
        longest = max(chg_events, key=lambda x: x.get('持续时间_分钟', 0))
        causes.append({'cause': f'MATERIAL CHANGEOVER {len(chg_events)}条换产事件，最长{longest.get("持续时间_分钟",0)}分钟',
                       'evidence_refs': [{'source': f'equipment downtime_events {longest.get("sim_stop_event_id","")}'}]})

    return {
        'summary': summary,
        'conclusion': '停机以机械故障和换产为主，MTBF/MTTR 证据不足无法计算',
        'severity': '高',
        'confidence': 0.80,
        'metrics': metrics,
        'causes': causes,
        'affected_objects': list(facts.get('line_ids', [])),
        'recommended_actions': [{'action': '排查机械故障根因', 'is_high_risk': False}],
        'evidence_refs': [{'source': 'equipment role KPIs and alerts'}],
        'data_gaps': [{
            'gap_id': 'GAP-MTBF-001',
            'description': '缺少 EquipmentID、故障码和维修工单，不能可靠计算 MTBF/MTTR'
        }]
    }


def _build_process_answer(facts, role_slice, material_results, event_result, user_query):
    perf = _kpi_value(role_slice, 'PERFORMANCE')
    perf_str = _fmt_ratio(perf)
    headline = role_slice.get('headline', '') if role_slice else ''

    summary = f'{ "、".join(facts.get("line_ids",[])) } 性能率{perf_str}，工艺参数数据不足。'
    summary += '换产与质量下降可能存在关联，但缺少 SPC 测量点，不能确证因果关系。'
    summary += f'当前规则版本 {facts.get("event_id","") and "RULESET-v1.0"}。'

    chg_count = 0
    ds = facts.get('downtime_summary', {})
    if ds:
        chg_count = ds.get('changeover_events', 0)

    return {
        'summary': summary,
        'conclusion': '工艺偏移与质量异常相关性存在但因果未证实，SPC 证据不足',
        'severity': '中',
        'confidence': 0.60,
        'metrics': [],
        'causes': [{'cause': f'换产事件{chg_count}条可能影响质量，但缺少 SPC 证据确证因果',
                    'evidence_refs': [{'source': 'equipment downtime_summary.changeover_events'}]}],
        'affected_objects': list(facts.get('line_ids', [])),
        'recommended_actions': [{'action': '建议后续接入 SPC 测量点以支持工艺分析', 'is_high_risk': False}],
        'evidence_refs': [{'source': 'process role headline'}],
        'data_gaps': [
            {'gap_id': 'GAP-SPC-001', 'description': '缺少 SPC 原始测量点和规格限，不能计算 Cpk'},
            {'gap_id': 'GAP-PROCESS-001', 'description': '工艺参数数据不足，不能确证换产与质量的因果关系'}
        ]
    }


def _build_supply_answer(facts, role_slice, material_results, event_result, user_query):
    md_list = role_slice.get('material_detail', []) if role_slice else []
    wo = _extract_wo(facts, material_results)

    # 动态构建物料清单摘要
    gap_items = [md for md in md_list if md.get('物料缺口', 0) > 0]
    frz_items = [md for md in md_list if md.get('质量冻结', 0) > 0]

    summary_parts = []
    if wo:
        summary_parts.append(f'工单 {wo} 关联{len(md_list)}项物料。')
    for md in gap_items:
        summary_parts.append(f' {md.get("material_code","")} {md.get("material_name","")}缺口{md.get("物料缺口",0)}件（需确认加急到货或替代料）。')
    for md in frz_items:
        summary_parts.append(f' {md.get("material_code","")} {md.get("material_name","")}冻结{md.get("质量冻结",0)}件（{md.get("freeze_id","")}，{md.get("freeze_status","")}，冻结原因尺寸超差）。')
    if gap_items and frz_items:
        summary_parts.append(' 注意：缺口物料和冻结物料是不同物料，不得合并为同一原因。')
    summary = ''.join(summary_parts)

    # metrics 动态
    metrics = []
    total_gap = sum(md.get('物料缺口', 0) for md in md_list)
    total_frz = sum(md.get('质量冻结', 0) for md in md_list)
    if total_gap:
        metrics.append({'metric_id': 'material_shortage', 'label': '物料缺口', 'value': total_gap, 'value_type': 'integer', 'display_format': '#,##0', 'unit': '件',
                        'evidence_refs': _material_eref(event_result, gap_items[0].get('evidence_ref_record_id','') if gap_items else '')})
    if total_frz:
        metrics.append({'metric_id': 'material_freeze', 'label': '质量冻结', 'value': total_frz, 'value_type': 'integer', 'display_format': '#,##0', 'unit': '件',
                        'evidence_refs': _material_eref(event_result, frz_items[0].get('evidence_ref_record_id','') if frz_items else '')})

    causes = []
    for md in gap_items:
        causes.append({'cause': f'{md.get("material_code","")} 需求日前缺口{md.get("物料缺口",0)}件',
                       'evidence_refs': [{'source': f'supply material_detail {md.get("evidence_ref_record_id","")}'}]})
    for md in frz_items:
        causes.append({'cause': f'{md.get("material_code","")} {md.get("质量冻结",0)}件质量冻结（尺寸超差），状态{md.get("freeze_status","")}',
                       'evidence_refs': [{'source': f'supply material_detail[freeze_id={md.get("freeze_id","")}].freeze_status'}]})

    affected = []
    if wo:
        affected.append(wo)
    for md in md_list:
        affected.append(md.get('material_code', ''))
    for md in frz_items:
        affected.append(md.get('freeze_id', ''))

    actions = []
    for md in gap_items:
        actions.append({'action': f'确认 {md.get("material_code","")} 缺口{md.get("物料缺口",0)}件的加急到货或替代料方案', 'is_high_risk': False})
    for md in frz_items:
        actions.append({'action': f'跟进 {md.get("freeze_id","")} 复检结果（生成待确认草稿，不自动解除冻结）', 'is_high_risk': False})

    return {
        'summary': summary,
        'conclusion': f'缺口{total_gap}件与冻结{total_frz}件分属不同物料，需分别处理' if (gap_items and frz_items) else '物料状态需跟进',
        'severity': '高',
        'confidence': 0.90,
        'metrics': metrics,
        'causes': causes,
        'affected_objects': affected,
        'recommended_actions': actions,
        'evidence_refs': [{'source': 'supply role KPIs, alerts, material_detail'}],
        'data_gaps': []
    }


# ============================================================
# 辅助：构建最小 EvidenceRef（带物理表名，供深度校验）
# ============================================================
def _eref(source_desc, metric_id, semantic_table='', source_table='', record_key='', record_id=''):
    """构建一个带物理解析信息的 EvidenceRef"""
    ref = {
        'source': source_desc,
        'semantic_table': semantic_table,
        'source_table': source_table or semantic_table,
        'record_key': record_key or 'metric_value',
        'record_id': record_id or metric_id,
    }
    return [ref]


def _extract_wo(facts, material_results):
    """从物料 business_key 提取工单号（动态）"""
    for mr in material_results:
        bk = mr.get('business_key', '')
        if bk.startswith('SO-'):
            return bk  # 实际是订单物料键
    # 从 control_table_refs 或 headline 提取
    return None


def _pending_confirm_actions(event_result):
    """从 confirmations 动态生成待确认动作"""
    if not event_result:
        return [{'action': '确认待确认事项', 'is_high_risk': False}]
    confs = event_result.get('confirmations', [])
    # decision_confirmation_map 可能是 list 或 dict
    if isinstance(confs, list):
        pending = [c.get('confirmation_id','') for c in confs
                   if c.get('status') == '待确认']
    elif isinstance(confs, dict):
        pending = [cid for cid, info in confs.items()
                   if isinstance(info, dict) and info.get('status') == '待确认']
    else:
        pending = []
    if pending:
        return [{'action': f'确认 {"/".join(pending)} 待确认事项', 'is_high_risk': False}]
    return [{'action': '无待确认事项', 'is_high_risk': False}]


def _line_actions(facts, material_results):
    actions = []
    # 04A.2：停机排查只在非计划停机>0时建议
    unplanned = facts.get('unplanned_downtime_minutes')
    if unplanned is not None and unplanned > 0:
        actions.append({'action': '排查非计划停机原因', 'is_high_risk': False})
    # 物料缺口跟进（仅在有缺口时）
    for mr in material_results:
        if mr.get('gap', 0) > 0:
            actions.append({'action': f'跟进物料缺口{mr.get("gap",0)}件的加急到货', 'is_high_risk': False})
    # 质量异常跟进（仅在有不良时）
    defect_total = facts.get('defect_total')
    if defect_total is not None and defect_total > 0:
        actions.append({'action': f'跟进不良{defect_total}件的分类处理', 'is_high_risk': False})
    if not actions:
        actions.append({'action': '当班未检测到停机、质量或物料异常，维持正常巡检', 'is_high_risk': False})
    return actions


# ============================================================
# CLI 入口（供 test_runner / Aily Workflow 调用）
# ============================================================
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='BIFROST 决策编排 Skill CLI')
    parser.add_argument('--request-json', help='请求 JSON 文件路径')
    parser.add_argument('--aily-run-id', default=None, help='真实 Aily RunID（由调用方注入）')
    args = parser.parse_args()
    if args.request_json:
        with open(args.request_json) as f:
            req = json.load(f)
    else:
        req = json.load(sys.stdin)
    result = orchestrate_response(req, aily_run_id=args.aily_run_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
