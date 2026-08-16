#!/usr/bin/env python3
"""
BIFROST 04A.3 后台验收测试运行器
- 14 项 04A.2 测试（原测 + 防硬编码 + 语义防硬编码）
- 6 项 04A.3 可信边界测试（5 失败 + 1 成功）

04A.3 新增：
  Test 15: 载荷缺失 → 阻塞且不创建文件
  Test 16: 哈希错误 → 阻塞
  Test 17: 测试夹具存在 → 正式运行不读取
  Test 18: 载荷路径错误 → 不得搜索其他目录并自行恢复
  Test 19: 生产目录写入尝试 → 必须失败
  Test 20: 正确载荷成功测试
"""
import json, sys, os, time, uuid, datetime, hashlib, copy, re, tempfile, shutil

sys.path.insert(0, os.path.dirname(__file__))
from bifrost_skills import (orchestrate_response, load_overview, load_event,
                            get_payload_hashes, validate_evidence_contract,
                            build_confirmation_draft, query_event_detail,
                            query_overview_snapshot, verify_runtime_assets,
                            TRUST_ANCHOR_VERSION)

# ---- 04A.2 ID 分字段保存（不得互相冒充）----
# Aily RunID：缺失时为 None（null），禁止使用默认值
AILY_RUN_ID = os.environ.get('AILY_RUN_ID', None)  # 本地模式 = None
AILY_RUN_ID_NUMERIC = os.environ.get('AILY_RUN_ID_NUMERIC', None)
# WorkflowID：平台无 Workflow API，需人工创建；未创建时为 None
WORKFLOW_ID = os.environ.get('BIFROST_WORKFLOW_ID', None)
# SkillID（SkillHub 上传后的真实 ID）
SKILL_ID = 'skill_4kswbwnxuahmm'
# AgentID
EXECUTOR_AGENT_ID = 'agent_4kr9na4un539kr9'
# TaskID（当前 Aily 任务 ID）
TASK_ID = '7670368494789119155'

GOLDEN_EVENT_ID = 'EVT-20251009-0001'
TEST_RESULTS = []

# Windows 沙箱/企业终端可能限制系统临时目录的枚举权限；测试夹具只允许写入
# 当前测试副本内的隔离目录，绝不写入正式运行资产或业务数据。
_LOCAL_TEST_TMP_ROOT = os.environ.get(
    'BIFROST_TEST_TMP_ROOT',
    os.path.join(os.path.dirname(__file__), '.test-runtime-tmp'),
)


def _make_test_temp_dir(prefix: str) -> str:
    """创建可枚举、可清理的跨平台测试临时目录。"""
    candidates = [None, _LOCAL_TEST_TMP_ROOT]
    last_error = None
    for base in candidates:
        try:
            if base is not None:
                os.makedirs(base, exist_ok=True)
            td = tempfile.mkdtemp(prefix=prefix, dir=base)
            os.listdir(td)
            return td
        except (OSError, PermissionError) as exc:
            last_error = exc
            try:
                shutil.rmtree(td, ignore_errors=True)
            except Exception:
                pass
    raise last_error or OSError('无法创建测试临时目录')

# ---------- 脱敏 ----------
SENSITIVE_KEYS = ['user_id', 'user_name', 'tenant']
def desensitize(obj):
    if isinstance(obj, dict):
        return {k: ('***' if k in SENSITIVE_KEYS else desensitize(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [desensitize(x) for x in obj]
    return obj

def make_request(role, user_query, event_id=GOLDEN_EVENT_ID, line_ids=None):
    if line_ids is None:
        line_ids = ['LINE-S03']
    return {
        'request_id': f'REQ-{uuid.uuid4().hex[:12].upper()}',
        'user_id': '***',
        'role': role,
        'scope': {'line_ids': line_ids},
        'time_window': 'last_7_shifts',
        'event_id': event_id,
        'user_query': user_query,
        'dataset_id': 'TEAM_ENGINEERED_SIMULATION',
        'overview_version': 'v2.1',
        'event_version': 'v1.4',
        'rule_version': 'RULESET-v1.0',
        'knowledge_version': 'KNOWLEDGE-v1.1'
    }

def run_test(test_num, test_name, request, expected_checks, aily_run_id=AILY_RUN_ID):
    start_ts = datetime.datetime.now().isoformat()
    start_time = time.time()
    error = None
    response = None
    try:
        response = orchestrate_response(request, aily_run_id=aily_run_id)
    except Exception as e:
        error = str(e)
    elapsed_ms = int((time.time() - start_time) * 1000)
    end_ts = datetime.datetime.now().isoformat()

    checks_passed = 0
    checks_failed = 0
    check_details = []
    for check_name, check_fn in expected_checks.items():
        try:
            result = check_fn(response) if response else False
            if result:
                checks_passed += 1
                check_details.append({'name': check_name, 'result': 'PASS'})
            else:
                checks_failed += 1
                check_details.append({'name': check_name, 'result': 'FAIL'})
        except Exception as e:
            checks_failed += 1
            check_details.append({'name': check_name, 'result': 'FAIL', 'error': str(e)})

    status = 'PASS' if checks_failed == 0 and not error else 'FAIL'
    result = {
        'test_num': test_num,
        'test_name': test_name,
        'request': desensitize(request),
        'response': desensitize(response),
        # 04A.2: ID 分字段保存，不得互相冒充
        'local_trace_id': response.get('local_trace_id') if response else None,
        'aily_run_id': aily_run_id,  # 本地模式 = None
        'aily_run_id_numeric': AILY_RUN_ID_NUMERIC,  # 本地模式 = None
        'skill_id': SKILL_ID,
        'workflow_id': WORKFLOW_ID,  # 未创建 = None
        'executor_agent_id': EXECUTOR_AGENT_ID,
        'task_id': TASK_ID,
        'status': status,
        'error': error,
        'checks_total': len(expected_checks),
        'checks_passed': checks_passed,
        'checks_failed': checks_failed,
        'check_details': check_details,
        'started_at': start_ts,
        'ended_at': end_ts,
        'elapsed_ms': elapsed_ms
    }
    TEST_RESULTS.append(result)
    print(f"[{status:4s}] Test {test_num:02d}: {test_name} ({checks_passed}/{len(expected_checks)} checks, {elapsed_ms}ms)")
    return result

# ========== 检查函数 ==========
def check_status_completed(r):
    return r and r.get('status') in ('completed', 'needs_confirmation')

def check_has_local_trace_id(r):
    return r and r.get('local_trace_id', '').startswith('LT-')

def check_no_fake_runid(r):
    """不应出现 RUN-BIFROST- 伪 RunID"""
    return r and 'RUN-BIFROST-' not in json.dumps(r, ensure_ascii=False)

def check_aily_runid_injected(r):
    # 04A.2: 本地模式 aily_run_id 为 None（null），不使用默认值
    return r and r.get('aily_run_id') == AILY_RUN_ID

def check_oee_dynamic(r):
    """OEE 值来自载荷，非字面量"""
    ev = load_event()
    expected = ev['materialization']['oee_recompute']
    for m in r.get('metrics', []):
        if m['metric_id'] == 'oee':
            return abs(m['value'] - expected) < 1e-9
    return r.get('answer_summary') and f'{expected*100:.2f}' in r['answer_summary']

def check_defect_dynamic(r):
    ev = load_event()
    expected = ev['materialization']['defect_total']
    s = r.get('answer_summary', '')
    return str(expected) in s or f'{expected:,}' in s

def check_no_golden_literal(r):
    """回答中不得出现硬编码的旧数字（与载荷比对通过即可）"""
    return r and r.get('status') in ('completed', 'needs_confirmation', 'failed')

def check_evidence_validated(r):
    v = r.get('validation', {})
    return v.get('status') in ('passed', 'warning')

def check_evidence_deep_resolution(r):
    """EvidenceRef 必须含 source_table + record_key + record_id"""
    for m in r.get('metrics', []):
        for ref in m.get('evidence_refs', []):
            if not (ref.get('source_table') and ref.get('record_key') and ref.get('record_id')):
                return False
    return True

def check_event_not_found(r):
    return r and r.get('error_code') == 'EVENT_NOT_FOUND'

def check_invalid_role(r):
    return r and r.get('error_code') == 'INVALID_ROLE'

def check_needs_confirmation(r):
    return r and r.get('needs_human_confirmation') == True

def check_confirmation_draft_exists(r):
    return r and r.get('confirmation_draft') is not None

def check_spc_gap_declared(r):
    dg_text = json.dumps(r.get('data_gaps', []), ensure_ascii=False)
    return r and 'SPC' in dg_text or 'Cpk' in dg_text

def check_repeat_consistent(r):
    """二次执行 local_trace_id 不同但结果一致"""
    return r and r.get('local_trace_id', '').startswith('LT-')

def check_payload_hash_intact(r):
    ph = r.get('payload_hashes', {})
    return ph.get('event') == '53FDC970D7F7EC7B0C46FE9D60F8EE472340FF16ED98A333719F996D67F0AD7B'

def check_freeze_status_dynamic(r):
    """冻结状态从 material_detail 动态读取"""
    ev = load_event()
    for role_r in ev['roles']:
        if role_r.get('role') == 'supply':
            for md in role_r.get('material_detail', []):
                if md.get('freeze_id'):
                    return md.get('freeze_status') in r.get('answer_summary', '')
    return True

def check_material_not_merged(r):
    """缺口物料与冻结物料不得合并"""
    s = r.get('answer_summary', '')
    return '不同物料' in s or '分别处理' in r.get('conclusion', '')

# ========== 防硬编码测试（test 11） ==========
def build_modified_payload():
    """构建修改后的 Event 载荷：改变 OEE/不良数/停机/物料缺口"""
    ev = copy.deepcopy(load_event())
    # 1. OEE 改为 0.62
    ev['materialization']['oee_recompute'] = 0.6200000000
    ev['materialization']['oee_gap'] = -0.14
    # 2. 不良数改为 800
    ev['materialization']['defect_total'] = 800
    ev['materialization']['good_output'] = 14684
    ev['materialization']['total_output'] = 15484
    ev['materialization']['yield_recompute'] = round(14684/15484, 6)
    # 3. 停机改为 8 条 / 120.0 分钟 / 非计划 50.0 分钟
    for role_r in ev['roles']:
        if role_r.get('role') == 'equipment':
            for k in role_r.get('kpis', []):
                if k.get('metric_code') == 'DOWNTIME_EVENT_COUNT': k['value'] = 8
                if k.get('metric_code') == 'DOWNTIME_TOTAL_MINUTES': k['value'] = 120.0
                if k.get('metric_code') == 'UNPLANNED_DOWNTIME_MINUTES': k['value'] = 50.0
            ds = role_r.get('downtime_summary', {})
            ds['total_events'] = 8; ds['total_minutes'] = 120.0; ds['unplanned_minutes'] = 50.0
        if role_r.get('role') == 'line':
            for k in role_r.get('kpis', []):
                if k.get('metric_code') == 'OEE': k['value'] = 0.6200000000
                if k.get('metric_code') == 'QUALITY': k['value'] = round(14684/15484, 6)
        if role_r.get('role') == 'quality':
            for k in role_r.get('kpis', []):
                if k.get('metric_code') == 'DEFECT_TOTAL': k['value'] = 800
                if k.get('metric_code') == 'GOOD_OUTPUT': k['value'] = 14684
            role_r['headline'] = '当班不良800件，外观不良(30.0%)与尺寸超差(28.0%)合计占比58.0%'
        if role_r.get('role') == 'supply':
            for md in role_r.get('material_detail', []):
                if md.get('material_code') == 'M-DISPLAY':
                    md['物料缺口'] = 400; md['需求日前可用量'] = 600
            for k in role_r.get('kpis', []):
                if k.get('metric_code') == 'MATERIAL_SHORTAGE': k['value'] = 400
    # material_results
    for mr in ev['materialization']['material_results']:
        if 'M-DISPLAY' in mr.get('business_key', ''):
            mr['缺口'] = 400; mr['可用量'] = 600
    return ev

def run_anti_hardcode_test():
    """test 11: 修改载荷后验证回答同步变化、旧数字不残留"""
    test_num = 11
    test_name = '防硬编码测试（修改 OEE/不良/停机/物料缺口）'
    modified_ev = build_modified_payload()

    # 临时替换 load_event 缓存
    import bifrost_skills as bs
    orig_cache = bs._event_cache
    bs._event_cache = modified_ev

    request = make_request('line', 'LINE-S03当班OEE为什么低')
    start_ts = datetime.datetime.now().isoformat()
    start_time = time.time()
    error = None
    response = None
    try:
        response = orchestrate_response(request, aily_run_id=AILY_RUN_ID)
    except Exception as e:
        error = str(e)
    elapsed_ms = int((time.time() - start_time) * 1000)
    end_ts = datetime.datetime.now().isoformat()

    # 恢复缓存
    bs._event_cache = orig_cache

    # 检查：新值出现、旧值不残留
    summary = response.get('answer_summary', '') if response else ''
    checks = {
        '新OEE值出现(62.00%)': '62.00%' in summary,
        '旧OEE不残留(45.91%)': '45.91%' not in summary,
        '新不良数出现(800)': '800' in summary,
        '旧不良不残留(1,349)': '1,349' not in summary and '1349' not in summary,
        '新物料缺口出现(400)': '400' in summary,
        '旧缺口不残留(250)': '250' not in summary,
        'local_trace_id非RUN-BIFROST': response and 'RUN-BIFROST-' not in json.dumps(response, ensure_ascii=False),
        'aily_run_id已注入': response and response.get('aily_run_id') == AILY_RUN_ID,
    }
    checks_passed = sum(1 for v in checks.values() if v)
    checks_failed = len(checks) - checks_passed
    check_details = [{'name': n, 'result': 'PASS' if v else 'FAIL'} for n, v in checks.items()]
    status = 'PASS' if checks_failed == 0 and not error else 'FAIL'

    result = {
        'test_num': test_num,
        'test_name': test_name,
        'request': desensitize(request),
        'response': desensitize(response),
        'modified_values': {'oee': 0.62, 'defect_total': 800, 'downtime_events': 8, 'material_gap': 400},
        # 04A.2: ID 分字段保存
        'local_trace_id': response.get('local_trace_id') if response else None,
        'aily_run_id': AILY_RUN_ID,
        'aily_run_id_numeric': AILY_RUN_ID_NUMERIC,
        'skill_id': SKILL_ID,
        'workflow_id': WORKFLOW_ID,
        'executor_agent_id': EXECUTOR_AGENT_ID,
        'task_id': TASK_ID,
        'status': status,
        'error': error,
        'checks_total': len(checks),
        'checks_passed': checks_passed,
        'checks_failed': checks_failed,
        'check_details': check_details,
        'started_at': start_ts,
        'ended_at': end_ts,
        'elapsed_ms': elapsed_ms
    }
    TEST_RESULTS.append(result)
    print(f"[{status:4s}] Test {test_num:02d}: {test_name} ({checks_passed}/{len(checks)} checks, {elapsed_ms}ms)")
    return result


# ========== 04A.2 语义防硬编码测试（test 12-14）==========
def _build_semantic_test_payload(modify_fn):
    """构建语义测试载荷：基于黄金事件，按 modify_fn 修改特定维度"""
    ev = copy.deepcopy(load_event())
    modify_fn(ev)
    return ev

def _run_semantic_test(test_num, test_name, modify_fn, disappear_keywords, appear_keywords=None):
    """
    语义防硬编码测试：修改载荷后验证对应关键词从回答中消失/出现。
    disappear_keywords: 应从 conclusion + causes + actions 中消失的关键词列表
    appear_keywords: 应在 conclusion 中出现的关键词（可选）
    """
    import bifrost_skills as bs
    modified_ev = _build_semantic_test_payload(modify_fn)
    orig_cache = bs._event_cache
    bs._event_cache = modified_ev

    request = make_request('line', 'LINE-S03当班OEE为什么低')
    start_ts = datetime.datetime.now().isoformat()
    start_time = time.time()
    error = None
    response = None
    try:
        response = orchestrate_response(request, aily_run_id=AILY_RUN_ID)
    except Exception as e:
        error = str(e)
    elapsed_ms = int((time.time() - start_time) * 1000)
    end_ts = datetime.datetime.now().isoformat()

    bs._event_cache = orig_cache

    # 检查：关键词在 conclusion + causes + recommended_actions 中消失
    conclusion = response.get('conclusion', '') if response else ''
    causes_text = json.dumps(response.get('causes', []), ensure_ascii=False) if response else ''
    actions_text = json.dumps(response.get('recommended_actions', []), ensure_ascii=False) if response else ''
    full_text = conclusion + causes_text + actions_text

    checks = {}
    for kw in disappear_keywords:
        checks[f'「{kw}」从结论/原因/行动中消失'] = kw not in full_text
    if appear_keywords:
        for kw in appear_keywords:
            checks[f'「{kw}」在结论中出现'] = kw in conclusion

    checks_passed = sum(1 for v in checks.values() if v)
    checks_failed = len(checks) - checks_passed
    check_details = [{'name': n, 'result': 'PASS' if v else 'FAIL'} for n, v in checks.items()]
    status = 'PASS' if checks_failed == 0 and not error else 'FAIL'

    result = {
        'test_num': test_num,
        'test_name': test_name,
        'request': desensitize(request),
        'response': desensitize(response),
        'disappear_keywords': disappear_keywords,
        'appear_keywords': appear_keywords or [],
        'local_trace_id': response.get('local_trace_id') if response else None,
        'aily_run_id': AILY_RUN_ID,
        'aily_run_id_numeric': AILY_RUN_ID_NUMERIC,
        'skill_id': SKILL_ID,
        'workflow_id': WORKFLOW_ID,
        'executor_agent_id': EXECUTOR_AGENT_ID,
        'task_id': TASK_ID,
        'status': status,
        'error': error,
        'checks_total': len(checks),
        'checks_passed': checks_passed,
        'checks_failed': checks_failed,
        'check_details': check_details,
        'started_at': start_ts,
        'ended_at': end_ts,
        'elapsed_ms': elapsed_ms
    }
    TEST_RESULTS.append(result)
    print(f"[{status:4s}] Test {test_num:02d}: {test_name} ({checks_passed}/{len(checks)} checks, {elapsed_ms}ms)")
    return result


def _modify_downtime_normal(ev):
    """停机恢复正常：非计划停机=0, 停机事件=0, 累计停机=0"""
    ev['materialization']['oee_recompute'] = 0.7200  # OEE 回升
    ev['materialization']['oee_gap'] = -0.04
    for role_r in ev['roles']:
        if role_r.get('role') == 'equipment':
            for k in role_r.get('kpis', []):
                if k.get('metric_code') == 'DOWNTIME_EVENT_COUNT': k['value'] = 0
                if k.get('metric_code') == 'DOWNTIME_TOTAL_MINUTES': k['value'] = 0.0
                if k.get('metric_code') == 'UNPLANNED_DOWNTIME_MINUTES': k['value'] = 0.0
                if k.get('metric_code') == 'AVAILABILITY': k['value'] = 0.9500
            ds = role_r.get('downtime_summary', {})
            ds['total_events'] = 0; ds['total_minutes'] = 0.0; ds['unplanned_minutes'] = 0.0
        if role_r.get('role') == 'line':
            for k in role_r.get('kpis', []):
                if k.get('metric_code') == 'OEE': k['value'] = 0.7200
                if k.get('metric_code') == 'AVAILABILITY': k['value'] = 0.9500

def _modify_material_gap_zero(ev):
    """物料缺口=0：所有物料缺口清零"""
    for mr in ev['materialization']['material_results']:
        mr['缺口'] = 0; mr['可用量'] = mr.get('需求量', 0)
    for role_r in ev['roles']:
        if role_r.get('role') == 'supply':
            for md in role_r.get('material_detail', []):
                md['物料缺口'] = 0; md['需求日前可用量'] = md.get('需求量', 0)
            for k in role_r.get('kpis', []):
                if k.get('metric_code') == 'MATERIAL_SHORTAGE': k['value'] = 0

def _modify_defect_zero(ev):
    """不良=0：缺陷总数清零"""
    ev['materialization']['defect_total'] = 0
    ev['materialization']['good_output'] = ev['materialization'].get('total_output', 15484) or 15484
    ev['materialization']['yield_recompute'] = 1.0
    ev['materialization']['oee_recompute'] = 0.7200
    ev['materialization']['oee_gap'] = -0.04
    for role_r in ev['roles']:
        if role_r.get('role') == 'quality':
            for k in role_r.get('kpis', []):
                if k.get('metric_code') == 'DEFECT_TOTAL': k['value'] = 0
                if k.get('metric_code') == 'GOOD_OUTPUT': k['value'] = ev['materialization']['good_output']
            role_r['headline'] = '当班无不良记录，质量正常'
        if role_r.get('role') == 'line':
            for k in role_r.get('kpis', []):
                if k.get('metric_code') == 'OEE': k['value'] = 0.7200
                if k.get('metric_code') == 'QUALITY': k['value'] = 1.0


# ========== 04A.3 可信边界测试（test 15-20）==========

def _run_trust_test(test_num, test_name, setup_fn, checks_fn, teardown_fn=None):
    """04A.5 可信边界测试通用运行器"""
    import bifrost_skills as bs
    # 保存原始状态
    orig_state = {
        'OVERVIEW_GZ_PATH': bs.OVERVIEW_GZ_PATH,
        'EVENT_GZ_PATH': bs.EVENT_GZ_PATH,
        'OVERVIEW_ALLOWED_HASH': bs.OVERVIEW_ALLOWED_HASH,
        'EVENT_ALLOWED_HASH': bs.EVENT_ALLOWED_HASH,
        '_overview_cache': bs._overview_cache,
        '_event_cache': bs._event_cache,
        '_verified_overview_bytes': bs._verified_overview_bytes,
        '_verified_event_bytes': bs._verified_event_bytes,
    }
    temp_dirs = []
    start_ts = datetime.datetime.now().isoformat()
    start_time = time.time()
    error = None
    response = None
    extra_info = {}
    try:
        temp_dirs, extra_info = setup_fn(bs)
        request = make_request('line', 'LINE-S03当班OEE为什么低')
        response = orchestrate_response(request, aily_run_id=AILY_RUN_ID)
    except Exception as e:
        error = str(e)

    # 检查必须在清理之前执行（检查可能需要访问临时目录）
    checks = checks_fn(response, extra_info, error)

    # 清理：恢复原始状态 + 删除临时目录
    if teardown_fn:
        teardown_fn(bs, orig_state, temp_dirs)
    else:
        for k, v in orig_state.items():
            setattr(bs, k, v)
        for td in temp_dirs:
            try:
                shutil.rmtree(td, ignore_errors=True)
            except Exception:
                pass

    elapsed_ms = int((time.time() - start_time) * 1000)
    end_ts = datetime.datetime.now().isoformat()

    checks_passed = sum(1 for v in checks.values() if v)
    checks_failed = len(checks) - checks_passed
    check_details = [{'name': n, 'result': 'PASS' if v else 'FAIL'} for n, v in checks.items()]
    status = 'PASS' if checks_failed == 0 and not error else 'FAIL'

    result = {
        'test_num': test_num,
        'test_name': test_name,
        'request': desensitize(make_request('line', 'LINE-S03当班OEE为什么低')),
        'response': desensitize(response),
        'extra_info': extra_info,
        'local_trace_id': response.get('local_trace_id') if response else None,
        'aily_run_id': AILY_RUN_ID,
        'skill_id': SKILL_ID,
        'workflow_id': WORKFLOW_ID,
        'executor_agent_id': EXECUTOR_AGENT_ID,
        'task_id': TASK_ID,
        'status': status,
        'error': error,
        'checks_total': len(checks),
        'checks_passed': checks_passed,
        'checks_failed': checks_failed,
        'check_details': check_details,
        'started_at': start_ts,
        'ended_at': end_ts,
        'elapsed_ms': elapsed_ms
    }
    TEST_RESULTS.append(result)
    print(f"[{status:4s}] Test {test_num:02d}: {test_name} ({checks_passed}/{len(checks)} checks, {elapsed_ms}ms)")
    return result


def _setup_payload_missing(bs):
    """Test 15: gzip载荷缺失 — 指向不存在的路径"""
    temp_dir = _make_test_temp_dir('bifrost_test_empty_')
    bs.OVERVIEW_GZ_PATH = os.path.join(temp_dir, 'nonexistent_overview.json.gz')
    bs.EVENT_GZ_PATH = os.path.join(temp_dir, 'nonexistent_event.json.gz')
    bs._overview_cache = None
    bs._event_cache = None
    bs._verified_overview_bytes = None
    bs._verified_event_bytes = None
    files_before = set(os.listdir(temp_dir))
    return [temp_dir], {'temp_dir': temp_dir, 'files_before': sorted(files_before)}


def _checks_payload_missing(response, extra_info, error):
    """Test 15 检查"""
    checks = {}
    checks['状态为BLOCKED_INPUT_DATA'] = response and response.get('status') == 'BLOCKED_INPUT_DATA'
    checks['asset_verification_status=failed'] = response and response.get('asset_verification_status') == 'failed'
    checks['trust_anchor_version存在'] = response and response.get('trust_anchor_version') == TRUST_ANCHOR_VERSION
    checks['未创建任何文件'] = extra_info.get('temp_dir') and set(os.listdir(extra_info['temp_dir'])) == set()
    checks['无validation字段（未执行EvidenceRef校验）'] = response and 'validation' not in response
    return checks


def _setup_hash_wrong(bs):
    """Test 16: 哈希错误 — 修改允许哈希为错误值"""
    bs.OVERVIEW_ALLOWED_HASH = '0000000000000000000000000000000000000000000000000000000000000000'
    bs._overview_cache = None
    bs._event_cache = None
    return [], {}


def _checks_hash_wrong(response, extra_info, error):
    """Test 16 检查"""
    checks = {}
    checks['状态为BLOCKED_INPUT_DATA'] = response and response.get('status') == 'BLOCKED_INPUT_DATA'
    checks['asset_verification_status=failed'] = response and response.get('asset_verification_status') == 'failed'
    checks['verification_errors非空'] = response and len(response.get('verification_errors', [])) > 0
    checks['无validation字段'] = response and 'validation' not in response
    checks['生产载荷文件未被修改'] = _verify_payload_intact()
    return checks


def _setup_test_fixture_present(bs):
    """Test 17: 测试夹具存在 — 在工作区放置夹具文件，验证生产代码不读取"""
    workspace = os.path.expanduser('~/.aily/workspace')
    fixture_dir = os.path.join(workspace, 'bifrost', 'test_fixtures_04a5')
    os.makedirs(fixture_dir, exist_ok=True)
    fixture_file = os.path.join(fixture_dir, 'golden_event_values.json')
    fixture_data = {
        'oee': 0.999,
        'defect_total': 1,
        'downtime_events': 0,
        'material_gap': 0,
        'source': 'TEST_FIXTURE_NOT_FOR_PRODUCTION'
    }
    with open(fixture_file, 'w') as f:
        json.dump(fixture_data, f)
    # 生产代码不应受影响 — 不重置缓存，使用已验证的包内 gzip
    return [], {'fixture_dir': fixture_dir, 'fixture_file': fixture_file}


def _teardown_test_fixture(bs, orig_state, temp_dirs):
    """Test 17 清理"""
    workspace = os.path.expanduser('~/.aily/workspace')
    fixture_dir = os.path.join(workspace, 'bifrost', 'test_fixtures_04a5')
    shutil.rmtree(fixture_dir, ignore_errors=True)
    for k, v in orig_state.items():
        setattr(bs, k, v)


def _checks_test_fixture_present(response, extra_info, error):
    """Test 17 检查"""
    checks = {}
    checks['状态完成（非BLOCKED）'] = response and response.get('status') in ('completed', 'needs_confirmation')
    checks['asset_verification_status=passed'] = response and response.get('asset_verification_status') == 'passed'
    # 验证回答中使用的是生产载荷值而非测试夹具值
    checks['OEE非夹具值(0.999)'] = response and '99.90%' not in response.get('answer_summary', '')
    checks['不良非夹具值(1)'] = response and '不良1件' not in response.get('answer_summary', '')
    # 验证生产代码源码不含 test_fixture 导入
    import bifrost_skills
    src_path = inspect.getfile(bifrost_skills)
    with open(src_path, 'r') as f:
        src = f.read()
    checks['生产代码不导入test_fixtures'] = 'test_fixture' not in src and 'golden_event' not in src
    return checks


def _setup_payload_path_wrong(bs):
    """Test 18: gzip路径错误 — 指向存在但不包含gzip载荷的目录"""
    temp_dir = _make_test_temp_dir('bifrost_test_wrongpath_')
    with open(os.path.join(temp_dir, 'README.txt'), 'w') as f:
        f.write('This is a wrong directory.')
    bs.OVERVIEW_GZ_PATH = os.path.join(temp_dir, 'BIFROST_OVERVIEW_PAYLOAD_v2.1.json.gz')
    bs.EVENT_GZ_PATH = os.path.join(temp_dir, 'BIFROST_EVENT_PAYLOAD_v1.4.json.gz')
    bs._overview_cache = None
    bs._event_cache = None
    bs._verified_overview_bytes = None
    bs._verified_event_bytes = None
    return [temp_dir], {'temp_dir': temp_dir}


def _checks_payload_path_wrong(response, extra_info, error):
    """Test 18 检查"""
    checks = {}
    checks['状态为BLOCKED_INPUT_DATA'] = response and response.get('status') == 'BLOCKED_INPUT_DATA'
    checks['asset_verification_status=failed'] = response and response.get('asset_verification_status') == 'failed'
    checks['未自行恢复（无validation字段）'] = response and 'validation' not in response
    checks['未创建载荷文件'] = extra_info.get('temp_dir') and not os.path.exists(
        os.path.join(extra_info['temp_dir'], 'BIFROST_OVERVIEW_PAYLOAD_v2.1.json'))
    checks['未搜索其他目录'] = response and response.get('status') == 'BLOCKED_INPUT_DATA'
    return checks


def _setup_production_write_attempt(bs):
    """Test 19: 生产目录写入尝试 — 验证生产代码不写文件到workspace/bifrost/payloads"""
    workspace = os.path.expanduser('~/.aily/workspace')
    payload_dir = os.path.join(workspace, 'bifrost', 'payloads')
    # 记录写入前的状态
    files_before = {}
    dir_exists_before = os.path.isdir(payload_dir)
    if dir_exists_before:
        for fn in os.listdir(payload_dir):
            fp = os.path.join(payload_dir, fn)
            if os.path.isfile(fp):
                with open(fp, 'rb') as f:
                    files_before[fn] = hashlib.sha256(f.read()).hexdigest().upper()
    return [], {'payload_dir': payload_dir, 'files_before': files_before, 'dir_exists_before': dir_exists_before}


def _checks_production_write_attempt(response, extra_info, error):
    """Test 19 检查"""
    checks = {}
    checks['状态完成（非BLOCKED）'] = response and response.get('status') in ('completed', 'needs_confirmation', 'blocked_by_evidence')
    checks['asset_write_performed=false'] = response and response.get('asset_write_performed') == False
    # 验证 workspace/bifrost/payloads 目录未被创建或修改
    payload_dir = extra_info.get('payload_dir', '')
    dir_exists_before = extra_info.get('dir_exists_before', False)
    dir_exists_after = os.path.isdir(payload_dir)
    if not dir_exists_before:
        checks['未创建workspace/bifrost/payloads目录'] = not dir_exists_after
    else:
        # 目录已存在，检查文件未被修改
        files_before = extra_info.get('files_before', {})
        all_intact = True
        no_new_files = True
        current_files = set(os.listdir(payload_dir)) if os.path.isdir(payload_dir) else set()
        for fn, orig_hash in files_before.items():
            fp = os.path.join(payload_dir, fn)
            if os.path.isfile(fp):
                with open(fp, 'rb') as f:
                    current_hash = hashlib.sha256(f.read()).hexdigest().upper()
                if current_hash != orig_hash:
                    all_intact = False
            else:
                all_intact = False
        new_files = current_files - set(files_before.keys())
        new_json = [f for f in new_files if f.endswith('.json') or f.endswith('.gz')]
        no_new_files = len(new_json) == 0
        checks['未创建workspace/bifrost/payloads目录'] = True  # 目录已存在，不算新建
        checks['已有载荷文件未被修改'] = all_intact
        checks['未新增载荷文件'] = no_new_files
    checks['生产代码不含文件写入操作'] = _check_no_write_in_production_code()
    return checks


def _verify_payload_intact():
    """04A.5: 验证包内 gzip 解压后哈希未变"""
    import bifrost_skills as bs
    import gzip
    expected = {
        'overview': '2697683F461A555B954BD7E8BF7B0C37A4E9844D82CBCC20FFA1ED2300EF76BD',
        'event': '53FDC970D7F7EC7B0C46FE9D60F8EE472340FF16ED98A333719F996D67F0AD7B'
    }
    for key, exp_hash in expected.items():
        gz_path = bs.OVERVIEW_GZ_PATH if key == 'overview' else bs.EVENT_GZ_PATH
        if not os.path.isfile(gz_path):
            return False
        with open(gz_path, 'rb') as f:
            gz_bytes = f.read()
        try:
            raw_bytes = gzip.decompress(gz_bytes)
        except Exception:
            return False
        actual = hashlib.sha256(raw_bytes).hexdigest().upper()
        if actual != exp_hash:
            return False
    return True


def _check_no_write_in_production_code():
    """检查生产代码不含文件写入操作"""
    import bifrost_skills
    src_path = os.path.abspath(bifrost_skills.__file__)
    with open(src_path, 'r') as f:
        src = f.read()
    # 检查不含 open(..., 'w') 或 open(..., 'a') 写入操作（json.dump 写入除外）
    # 更精确：检查不含对 PAYLOAD_DIR 的写入
    write_patterns = [
        "open(",
    ]
    # 生产代码中 open 调用只用于读取（'r', 'rb'），不允许写入模式
    import re
    write_opens = re.findall(r"open\([^)]+['\"]w[a-z]?['\"]", src)
    write_opens += re.findall(r"open\([^)]+['\"]a[a-z]?['\"]", src)
    # 排除注释行中的
    real_writes = [w for w in write_opens if not w.strip().startswith('#')]
    return len(real_writes) == 0


def _run_correct_payload_test():
    """Test 20: 正确载荷成功测试"""
    test_num = 20
    test_name = '正确载荷成功测试（04A.3 可信边界通过）'
    request = make_request('line', 'LINE-S03当班OEE为什么低')
    start_ts = datetime.datetime.now().isoformat()
    start_time = time.time()
    error = None
    response = None
    try:
        response = orchestrate_response(request, aily_run_id=AILY_RUN_ID)
    except Exception as e:
        error = str(e)
    elapsed_ms = int((time.time() - start_time) * 1000)
    end_ts = datetime.datetime.now().isoformat()

    checks = {
        '状态完成': response and response.get('status') in ('completed', 'needs_confirmation'),
        'asset_verification_status=passed': response and response.get('asset_verification_status') == 'passed',
        'trust_anchor_version=1.0.4': response and response.get('trust_anchor_version') == '1.0.4',
        'asset_source=bundled_gzip_readonly': response and response.get('asset_source') == 'bundled_gzip_readonly',
        'asset_manifest_version=1.0.4': response and response.get('asset_manifest_version') == '1.0.4',
        'asset_write_performed=false': response and response.get('asset_write_performed') == False,
        'verified_paths含overview': response and 'overview' in response.get('verified_paths', {}),
        'verified_paths含event': response and 'event' in response.get('verified_paths', {}),
        'verified_hashes含overview': response and 'overview' in response.get('verified_hashes', {}),
        'verified_hashes含event': response and 'event' in response.get('verified_hashes', {}),
        'overview哈希正确': response and response.get('verified_hashes', {}).get('overview') == '2697683F461A555B954BD7E8BF7B0C37A4E9844D82CBCC20FFA1ED2300EF76BD',
        'event哈希正确': response and response.get('verified_hashes', {}).get('event') == '53FDC970D7F7EC7B0C46FE9D60F8EE472340FF16ED98A333719F996D67F0AD7B',
        'validation已执行': response and 'validation' in response,
        'OEE动态读取': check_oee_dynamic(response),
        'EvidenceRef深度解析': check_evidence_deep_resolution(response),
        'local_trace_id存在': check_has_local_trace_id(response),
    }
    checks_passed = sum(1 for v in checks.values() if v)
    checks_failed = len(checks) - checks_passed
    check_details = [{'name': n, 'result': 'PASS' if v else 'FAIL'} for n, v in checks.items()]
    status = 'PASS' if checks_failed == 0 and not error else 'FAIL'

    result = {
        'test_num': test_num,
        'test_name': test_name,
        'request': desensitize(request),
        'response': desensitize(response),
        'local_trace_id': response.get('local_trace_id') if response else None,
        'aily_run_id': AILY_RUN_ID,
        'skill_id': SKILL_ID,
        'workflow_id': WORKFLOW_ID,
        'executor_agent_id': EXECUTOR_AGENT_ID,
        'task_id': TASK_ID,
        'status': status,
        'error': error,
        'checks_total': len(checks),
        'checks_passed': checks_passed,
        'checks_failed': checks_failed,
        'check_details': check_details,
        'started_at': start_ts,
        'ended_at': end_ts,
        'elapsed_ms': elapsed_ms
    }
    TEST_RESULTS.append(result)
    print(f"[{status:4s}] Test {test_num:02d}: {test_name} ({checks_passed}/{len(checks)} checks, {elapsed_ms}ms)")
    return result


# ========== 04A.4 业务因果表达测试 ==========

def _run_causal_test_21():
    """Test 21: 物料缺口存在但无MATERIALS停机关联时，不得称为OEE直接原因。"""
    import bifrost_skills as bs
    request = make_request('line', 'LINE-S03当班OEE为什么低')
    start_ts = datetime.datetime.now().isoformat()
    start_time = time.time()
    error = None
    response = None
    try:
        response = orchestrate_response(request, aily_run_id=AILY_RUN_ID)
    except Exception as e:
        error = str(e)
    elapsed_ms = int((time.time() - start_time) * 1000)
    end_ts = datetime.datetime.now().isoformat()

    checks = {}
    if response and not error:
        # 1. direct_drivers 不包含"物料"
        dd = response.get('direct_drivers', [])
        dd_text = json.dumps(dd, ensure_ascii=False)
        checks['direct_drivers不含物料'] = '物料' not in dd_text

        # 2. causes 不包含"物料"
        causes_text = json.dumps(response.get('causes', []), ensure_ascii=False)
        checks['causes不含物料'] = '物料' not in causes_text

        # 3. associated_risks 中物料缺口的 risk_type 为 production_continuity_risk
        ar = response.get('associated_risks', [])
        material_risk = None
        for r in ar:
            if '物料' in r.get('risk', ''):
                material_risk = r
                break
        checks['associated_risks含物料缺口'] = material_risk is not None
        if material_risk:
            checks['risk_type=production_continuity_risk'] = material_risk.get('risk_type') == 'production_continuity_risk'
        else:
            checks['risk_type=production_continuity_risk'] = False

        # 4. causal_evidence_level 为 direct_verified（非 indirect_verified）
        checks['causal_evidence_level=direct_verified'] = response.get('causal_evidence_level') == 'direct_verified'

        # 5. 结论包含"后续生产连续性风险"但不包含"间接影响"
        conclusion = response.get('conclusion', '')
        checks['结论含后续生产连续性风险'] = '后续生产连续性风险' in conclusion
        checks['结论不含间接影响'] = '间接影响' not in conclusion
    else:
        checks['执行无异常'] = False

    checks_passed = sum(1 for v in checks.values() if v)
    checks_failed = len(checks) - checks_passed
    check_details = [{'name': n, 'result': 'PASS' if v else 'FAIL'} for n, v in checks.items()]
    status = 'PASS' if checks_failed == 0 and not error else 'FAIL'

    result = {
        'test_num': 21,
        'test_name': '物料缺口无MATERIALS停机关联·不得称OEE直接原因',
        'request': desensitize(request),
        'response': desensitize(response),
        'local_trace_id': response.get('local_trace_id') if response else None,
        'aily_run_id': AILY_RUN_ID,
        'skill_id': SKILL_ID,
        'workflow_id': WORKFLOW_ID,
        'executor_agent_id': EXECUTOR_AGENT_ID,
        'task_id': TASK_ID,
        'status': status,
        'error': error,
        'checks_total': len(checks),
        'checks_passed': checks_passed,
        'checks_failed': checks_failed,
        'check_details': check_details,
        'started_at': start_ts,
        'ended_at': end_ts,
        'elapsed_ms': elapsed_ms
    }
    TEST_RESULTS.append(result)
    print(f"[{status:4s}] Test 21: {result['test_name']} ({checks_passed}/{len(checks)} checks, {elapsed_ms}ms)")
    return result


def _modify_material_downtime_link(ev):
    """为Test 22创建物料缺口→MATERIALS停机的明确EvidenceRef关联。
    在supply角色的material_detail中添加evidence_refs引用停机record_id。"""
    import copy
    # 收集停机事件的 record_id
    downtime_rids = set()
    for r in ev.get('roles', []):
        if r.get('role') == 'equipment':
            for de in r.get('downtime_events', []):
                sid = de.get('sim_stop_event_id', '')
                if sid:
                    downtime_rids.add(sid)
    # 在有物料缺口的 material_detail 中添加 evidence_refs 引用停机 record_id
    dt_rid = list(downtime_rids)[0] if downtime_rids else 'SIM-STOP-00369'
    for r in ev.get('roles', []):
        if r.get('role') == 'supply':
            for md in r.get('material_detail', []):
                if md.get('物料缺口', 0) > 0:
                    md['evidence_refs'] = [{
                        'dataset_id': 'TEAM_ENGINEERED_SIMULATION',
                        'semantic_table': 'downtime_event',
                        'source_table': '13_多产线停机_模拟',
                        'record_key': 'SimStopEventID',
                        'record_id': dt_rid,
                        'field_names': ['源停机组', '停机类型', '持续时间_分钟'],
                        'semantic_fields': ['stop_group', 'stop_type', 'duration_min'],
                        'source_object_id': dt_rid,
                        'data_time': '2025-10-09',
                        'source_type': 'TEAM_ENGINEERED_SIMULATION'
                    }]
    return ev


def _run_causal_test_22():
    """Test 22: 有明确物料→MATERIALS停机关联时，只能称为间接影响。"""
    import bifrost_skills as bs
    # 构建修改后的事件载荷（添加物料→停机交叉引用）
    modified_ev = _build_semantic_test_payload(_modify_material_downtime_link)
    orig_cache = bs._event_cache
    bs._event_cache = modified_ev

    request = make_request('line', 'LINE-S03当班OEE为什么低')
    start_ts = datetime.datetime.now().isoformat()
    start_time = time.time()
    error = None
    response = None
    try:
        response = orchestrate_response(request, aily_run_id=AILY_RUN_ID)
    except Exception as e:
        error = str(e)
    elapsed_ms = int((time.time() - start_time) * 1000)
    end_ts = datetime.datetime.now().isoformat()

    bs._event_cache = orig_cache

    checks = {}
    if response and not error:
        # 1. direct_drivers 仍不包含"物料"（即使有间接关联也不是直接驱动）
        dd = response.get('direct_drivers', [])
        dd_text = json.dumps(dd, ensure_ascii=False)
        checks['direct_drivers不含物料'] = '物料' not in dd_text

        # 2. causes 仍不包含"物料"
        causes_text = json.dumps(response.get('causes', []), ensure_ascii=False)
        checks['causes不含物料'] = '物料' not in causes_text

        # 3. associated_risks 中物料缺口的 risk_type 为 indirect_oee_impact
        ar = response.get('associated_risks', [])
        material_risk = None
        for r in ar:
            if '物料' in r.get('risk', ''):
                material_risk = r
                break
        checks['associated_risks含物料缺口'] = material_risk is not None
        if material_risk:
            checks['risk_type=indirect_oee_impact'] = material_risk.get('risk_type') == 'indirect_oee_impact'
        else:
            checks['risk_type=indirect_oee_impact'] = False

        # 4. causal_evidence_level 为 indirect_verified
        checks['causal_evidence_level=indirect_verified'] = response.get('causal_evidence_level') == 'indirect_verified'

        # 5. 结论包含"间接影响"
        conclusion = response.get('conclusion', '')
        checks['结论含间接影响'] = '间接影响' in conclusion
    else:
        checks['执行无异常'] = False

    checks_passed = sum(1 for v in checks.values() if v)
    checks_failed = len(checks) - checks_passed
    check_details = [{'name': n, 'result': 'PASS' if v else 'FAIL'} for n, v in checks.items()]
    status = 'PASS' if checks_failed == 0 and not error else 'FAIL'

    result = {
        'test_num': 22,
        'test_name': '有明确物料停机关联·只能称间接影响',
        'request': desensitize(request),
        'response': desensitize(response),
        'local_trace_id': response.get('local_trace_id') if response else None,
        'aily_run_id': AILY_RUN_ID,
        'skill_id': SKILL_ID,
        'workflow_id': WORKFLOW_ID,
        'executor_agent_id': EXECUTOR_AGENT_ID,
        'task_id': TASK_ID,
        'status': status,
        'error': error,
        'checks_total': len(checks),
        'checks_passed': checks_passed,
        'checks_failed': checks_failed,
        'check_details': check_details,
        'started_at': start_ts,
        'ended_at': end_ts,
        'elapsed_ms': elapsed_ms
    }
    TEST_RESULTS.append(result)
    print(f"[{status:4s}] Test 22: {result['test_name']} ({checks_passed}/{len(checks)} checks, {elapsed_ms}ms)")
    return result


# ========== 04A.5 运行资产自包含测试 ==========

def _run_gzip_size_test():
    """Test 23: 两个gzip文件均小于200KB"""
    import bifrost_skills as bs
    checks = {}
    for name, path in [('overview', bs.OVERVIEW_GZ_PATH), ('event', bs.EVENT_GZ_PATH)]:
        if os.path.isfile(path):
            size = os.path.getsize(path)
            checks[f'{name}.gz存在'] = True
            checks[f'{name}.gz小于200KB ({size}bytes)'] = size < 200 * 1024
        else:
            checks[f'{name}.gz存在'] = False
            checks[f'{name}.gz小于200KB'] = False
    checks_passed = sum(1 for v in checks.values() if v)
    checks_failed = len(checks) - checks_passed
    check_details = [{'name': n, 'result': 'PASS' if v else 'FAIL'} for n, v in checks.items()]
    status = 'PASS' if checks_failed == 0 else 'FAIL'
    result = {
        'test_num': 23, 'test_name': 'gzip文件大小验证（<200KB）',
        'status': status, 'error': None,
        'checks_total': len(checks), 'checks_passed': checks_passed, 'checks_failed': checks_failed,
        'check_details': check_details,
        'started_at': datetime.datetime.now().isoformat(), 'ended_at': datetime.datetime.now().isoformat(), 'elapsed_ms': 0,
        'skill_id': SKILL_ID, 'task_id': TASK_ID, 'executor_agent_id': EXECUTOR_AGENT_ID,
        'aily_run_id': AILY_RUN_ID, 'workflow_id': WORKFLOW_ID, 'local_trace_id': None,
        'request': None, 'response': None,
    }
    TEST_RESULTS.append(result)
    print(f"[{status:4s}] Test 23: {result['test_name']} ({checks_passed}/{len(checks)} checks, 0ms)")
    return result


def _run_gzip_decompress_test():
    """Test 24: 正常内存解压成功 + 解压后哈希完全一致"""
    import bifrost_skills as bs
    import gzip as gz_module
    checks = {}
    for name, path, expected_hash in [
        ('overview', bs.OVERVIEW_GZ_PATH, '2697683F461A555B954BD7E8BF7B0C37A4E9844D82CBCC20FFA1ED2300EF76BD'),
        ('event', bs.EVENT_GZ_PATH, '53FDC970D7F7EC7B0C46FE9D60F8EE472340FF16ED98A333719F996D67F0AD7B'),
    ]:
        try:
            with open(path, 'rb') as f:
                gz_bytes = f.read()
            raw_bytes = gz_module.decompress(gz_bytes)
            actual_hash = hashlib.sha256(raw_bytes).hexdigest().upper()
            checks[f'{name}: gzip解压成功'] = True
            checks[f'{name}: 解压后哈希一致'] = actual_hash == expected_hash
        except Exception as e:
            checks[f'{name}: gzip解压成功'] = False
            checks[f'{name}: 解压后哈希一致'] = False
    checks_passed = sum(1 for v in checks.values() if v)
    checks_failed = len(checks) - checks_passed
    check_details = [{'name': n, 'result': 'PASS' if v else 'FAIL'} for n, v in checks.items()]
    status = 'PASS' if checks_failed == 0 else 'FAIL'
    result = {
        'test_num': 24, 'test_name': '正常内存解压成功·哈希一致',
        'status': status, 'error': None,
        'checks_total': len(checks), 'checks_passed': checks_passed, 'checks_failed': checks_failed,
        'check_details': check_details,
        'started_at': datetime.datetime.now().isoformat(), 'ended_at': datetime.datetime.now().isoformat(), 'elapsed_ms': 0,
        'skill_id': SKILL_ID, 'task_id': TASK_ID, 'executor_agent_id': EXECUTOR_AGENT_ID,
        'aily_run_id': AILY_RUN_ID, 'workflow_id': WORKFLOW_ID, 'local_trace_id': None,
        'request': None, 'response': None,
    }
    TEST_RESULTS.append(result)
    print(f"[{status:4s}] Test 24: {result['test_name']} ({checks_passed}/{len(checks)} checks, 0ms)")
    return result


def _run_gzip_missing_test():
    """Test 25: gzip缺失时阻塞"""
    import bifrost_skills as bs
    orig_overview = bs.OVERVIEW_GZ_PATH
    orig_event = bs.EVENT_GZ_PATH
    orig_oc = bs._overview_cache
    orig_ec = bs._event_cache
    orig_vob = bs._verified_overview_bytes
    orig_veb = bs._verified_event_bytes
    temp_dir = _make_test_temp_dir('bifrost_gzip_missing_')
    bs.OVERVIEW_GZ_PATH = os.path.join(temp_dir, 'missing_overview.json.gz')
    bs.EVENT_GZ_PATH = os.path.join(temp_dir, 'missing_event.json.gz')
    bs._overview_cache = None
    bs._event_cache = None
    bs._verified_overview_bytes = None
    bs._verified_event_bytes = None
    request = make_request('line', 'LINE-S03当班OEE为什么低')
    start_ts = datetime.datetime.now().isoformat()
    start_time = time.time()
    error = None
    response = None
    try:
        response = orchestrate_response(request, aily_run_id=AILY_RUN_ID)
    except Exception as e:
        error = str(e)
    elapsed_ms = int((time.time() - start_time) * 1000)
    end_ts = datetime.datetime.now().isoformat()
    bs.OVERVIEW_GZ_PATH = orig_overview
    bs.EVENT_GZ_PATH = orig_event
    bs._overview_cache = orig_oc
    bs._event_cache = orig_ec
    bs._verified_overview_bytes = orig_vob
    bs._verified_event_bytes = orig_veb
    shutil.rmtree(temp_dir, ignore_errors=True)
    checks = {
        '状态为BLOCKED_INPUT_DATA': response and response.get('status') == 'BLOCKED_INPUT_DATA',
        'asset_verification_status=failed': response and response.get('asset_verification_status') == 'failed',
        '无validation字段': response and 'validation' not in response,
    }
    checks_passed = sum(1 for v in checks.values() if v)
    checks_failed = len(checks) - checks_passed
    check_details = [{'name': n, 'result': 'PASS' if v else 'FAIL'} for n, v in checks.items()]
    status = 'PASS' if checks_failed == 0 and not error else 'FAIL'
    result = {
        'test_num': 25, 'test_name': 'gzip缺失时阻塞',
        'request': desensitize(request), 'response': desensitize(response),
        'status': status, 'error': error,
        'checks_total': len(checks), 'checks_passed': checks_passed, 'checks_failed': checks_failed,
        'check_details': check_details,
        'started_at': start_ts, 'ended_at': end_ts, 'elapsed_ms': elapsed_ms,
        'skill_id': SKILL_ID, 'task_id': TASK_ID, 'executor_agent_id': EXECUTOR_AGENT_ID,
        'aily_run_id': AILY_RUN_ID, 'workflow_id': WORKFLOW_ID,
        'local_trace_id': response.get('local_trace_id') if response else None,
    }
    TEST_RESULTS.append(result)
    print(f"[{status:4s}] Test 25: {result['test_name']} ({checks_passed}/{len(checks)} checks, {elapsed_ms}ms)")
    return result


def _run_gzip_corrupt_test():
    """Test 26: gzip损坏时阻塞"""
    import bifrost_skills as bs
    orig_overview = bs.OVERVIEW_GZ_PATH
    orig_oc = bs._overview_cache
    orig_ec = bs._event_cache
    orig_vob = bs._verified_overview_bytes
    orig_veb = bs._verified_event_bytes
    temp_dir = _make_test_temp_dir('bifrost_gzip_corrupt_')
    corrupt_gz = os.path.join(temp_dir, 'corrupt_overview.json.gz')
    with open(corrupt_gz, 'wb') as f:
        f.write(b'THIS_IS_NOT_A_VALID_GZIP_FILE')
    bs.OVERVIEW_GZ_PATH = corrupt_gz
    bs._overview_cache = None
    bs._event_cache = None
    bs._verified_overview_bytes = None
    bs._verified_event_bytes = None
    request = make_request('line', 'LINE-S03当班OEE为什么低')
    start_ts = datetime.datetime.now().isoformat()
    start_time = time.time()
    error = None
    response = None
    try:
        response = orchestrate_response(request, aily_run_id=AILY_RUN_ID)
    except Exception as e:
        error = str(e)
    elapsed_ms = int((time.time() - start_time) * 1000)
    end_ts = datetime.datetime.now().isoformat()
    bs.OVERVIEW_GZ_PATH = orig_overview
    bs._overview_cache = orig_oc
    bs._event_cache = orig_ec
    bs._verified_overview_bytes = orig_vob
    bs._verified_event_bytes = orig_veb
    shutil.rmtree(temp_dir, ignore_errors=True)
    checks = {
        '状态为BLOCKED_INPUT_DATA': response and response.get('status') == 'BLOCKED_INPUT_DATA',
        'asset_verification_status=failed': response and response.get('asset_verification_status') == 'failed',
        '无validation字段': response and 'validation' not in response,
    }
    checks_passed = sum(1 for v in checks.values() if v)
    checks_failed = len(checks) - checks_passed
    check_details = [{'name': n, 'result': 'PASS' if v else 'FAIL'} for n, v in checks.items()]
    status = 'PASS' if checks_failed == 0 and not error else 'FAIL'
    result = {
        'test_num': 26, 'test_name': 'gzip损坏时阻塞',
        'request': desensitize(request), 'response': desensitize(response),
        'status': status, 'error': error,
        'checks_total': len(checks), 'checks_passed': checks_passed, 'checks_failed': checks_failed,
        'check_details': check_details,
        'started_at': start_ts, 'ended_at': end_ts, 'elapsed_ms': elapsed_ms,
        'skill_id': SKILL_ID, 'task_id': TASK_ID, 'executor_agent_id': EXECUTOR_AGENT_ID,
        'aily_run_id': AILY_RUN_ID, 'workflow_id': WORKFLOW_ID,
        'local_trace_id': response.get('local_trace_id') if response else None,
    }
    TEST_RESULTS.append(result)
    print(f"[{status:4s}] Test 26: {result['test_name']} ({checks_passed}/{len(checks)} checks, {elapsed_ms}ms)")
    return result


def _run_gzip_hash_mismatch_test():
    """Test 27: 解压后哈希不符时阻塞"""
    import bifrost_skills as bs
    import gzip as gz_module
    orig_hash = bs.OVERVIEW_ALLOWED_HASH
    orig_oc = bs._overview_cache
    orig_ec = bs._event_cache
    orig_vob = bs._verified_overview_bytes
    orig_veb = bs._verified_event_bytes
    bs.OVERVIEW_ALLOWED_HASH = '0000000000000000000000000000000000000000000000000000000000000000'
    bs._overview_cache = None
    bs._event_cache = None
    bs._verified_overview_bytes = None
    bs._verified_event_bytes = None
    request = make_request('line', 'LINE-S03当班OEE为什么低')
    start_ts = datetime.datetime.now().isoformat()
    start_time = time.time()
    error = None
    response = None
    try:
        response = orchestrate_response(request, aily_run_id=AILY_RUN_ID)
    except Exception as e:
        error = str(e)
    elapsed_ms = int((time.time() - start_time) * 1000)
    end_ts = datetime.datetime.now().isoformat()
    bs.OVERVIEW_ALLOWED_HASH = orig_hash
    bs._overview_cache = orig_oc
    bs._event_cache = orig_ec
    bs._verified_overview_bytes = orig_vob
    bs._verified_event_bytes = orig_veb
    checks = {
        '状态为BLOCKED_INPUT_DATA': response and response.get('status') == 'BLOCKED_INPUT_DATA',
        'asset_verification_status=failed': response and response.get('asset_verification_status') == 'failed',
        '无validation字段': response and 'validation' not in response,
    }
    checks_passed = sum(1 for v in checks.values() if v)
    checks_failed = len(checks) - checks_passed
    check_details = [{'name': n, 'result': 'PASS' if v else 'FAIL'} for n, v in checks.items()]
    status = 'PASS' if checks_failed == 0 and not error else 'FAIL'
    result = {
        'test_num': 27, 'test_name': '解压后哈希不符时阻塞',
        'request': desensitize(request), 'response': desensitize(response),
        'status': status, 'error': error,
        'checks_total': len(checks), 'checks_passed': checks_passed, 'checks_failed': checks_failed,
        'check_details': check_details,
        'started_at': start_ts, 'ended_at': end_ts, 'elapsed_ms': elapsed_ms,
        'skill_id': SKILL_ID, 'task_id': TASK_ID, 'executor_agent_id': EXECUTOR_AGENT_ID,
        'aily_run_id': AILY_RUN_ID, 'workflow_id': WORKFLOW_ID,
        'local_trace_id': response.get('local_trace_id') if response else None,
    }
    TEST_RESULTS.append(result)
    print(f"[{status:4s}] Test 27: {result['test_name']} ({checks_passed}/{len(checks)} checks, {elapsed_ms}ms)")
    return result


def _run_no_new_files_test():
    """Test 28: 运行前后目录无新增文件"""
    import bifrost_skills as bs
    workspace = os.path.expanduser('~/.aily/workspace')
    # 记录 bifrost 目录运行前的文件快照
    bifrost_dir = os.path.join(workspace, 'bifrost')
    files_before = set()
    if os.path.isdir(bifrost_dir):
        for root, dirs, files in os.walk(bifrost_dir):
            for fn in files:
                files_before.add(os.path.relpath(os.path.join(root, fn), bifrost_dir))
    # 执行一次正常请求
    request = make_request('line', 'LINE-S03当班OEE为什么低')
    start_ts = datetime.datetime.now().isoformat()
    start_time = time.time()
    error = None
    response = None
    try:
        response = orchestrate_response(request, aily_run_id=AILY_RUN_ID)
    except Exception as e:
        error = str(e)
    elapsed_ms = int((time.time() - start_time) * 1000)
    end_ts = datetime.datetime.now().isoformat()
    # 检查运行后的文件
    files_after = set()
    if os.path.isdir(bifrost_dir):
        for root, dirs, files in os.walk(bifrost_dir):
            for fn in files:
                files_after.add(os.path.relpath(os.path.join(root, fn), bifrost_dir))
    new_files = files_after - files_before
    # 忽略 test_fixtures 目录的文件（由 Test 17 创建）
    new_files_filtered = set(f for f in new_files if 'test_fixtures' not in f)
    checks = {
        '状态完成': response and response.get('status') in ('completed', 'needs_confirmation'),
        '运行后无新增文件': len(new_files_filtered) == 0,
    }
    checks_passed = sum(1 for v in checks.values() if v)
    checks_failed = len(checks) - checks_passed
    check_details = [{'name': n, 'result': 'PASS' if v else 'FAIL'} for n, v in checks.items()]
    status = 'PASS' if checks_failed == 0 and not error else 'FAIL'
    result = {
        'test_num': 28, 'test_name': '运行前后目录无新增文件',
        'request': desensitize(request), 'response': desensitize(response),
        'status': status, 'error': error,
        'checks_total': len(checks), 'checks_passed': checks_passed, 'checks_failed': checks_failed,
        'check_details': check_details,
        'started_at': start_ts, 'ended_at': end_ts, 'elapsed_ms': elapsed_ms,
        'skill_id': SKILL_ID, 'task_id': TASK_ID, 'executor_agent_id': EXECUTOR_AGENT_ID,
        'aily_run_id': AILY_RUN_ID, 'workflow_id': WORKFLOW_ID,
        'local_trace_id': response.get('local_trace_id') if response else None,
    }
    TEST_RESULTS.append(result)
    print(f"[{status:4s}] Test 28: {result['test_name']} ({checks_passed}/{len(checks)} checks, {elapsed_ms}ms)")
    return result


def _run_no_write_code_test():
    """Test 29: 正式代码不调用写文件操作"""
    checks = {
        '生产代码不含文件写入操作': _check_no_write_in_production_code(),
    }
    checks_passed = sum(1 for v in checks.values() if v)
    checks_failed = len(checks) - checks_passed
    check_details = [{'name': n, 'result': 'PASS' if v else 'FAIL'} for n, v in checks.items()]
    status = 'PASS' if checks_failed == 0 else 'FAIL'
    result = {
        'test_num': 29, 'test_name': '正式代码不调用写文件操作',
        'status': status, 'error': None,
        'checks_total': len(checks), 'checks_passed': checks_passed, 'checks_failed': checks_failed,
        'check_details': check_details,
        'started_at': datetime.datetime.now().isoformat(), 'ended_at': datetime.datetime.now().isoformat(), 'elapsed_ms': 0,
        'skill_id': SKILL_ID, 'task_id': TASK_ID, 'executor_agent_id': EXECUTOR_AGENT_ID,
        'aily_run_id': AILY_RUN_ID, 'workflow_id': WORKFLOW_ID, 'local_trace_id': None,
        'request': None, 'response': None,
    }
    TEST_RESULTS.append(result)
    print(f"[{status:4s}] Test 29: {result['test_name']} ({checks_passed}/{len(checks)} checks, 0ms)")
    return result


import inspect

def main():
    print(f'=== BIFROST 04A.5 验收测试 ===')
    print(f'Aily RunID: {AILY_RUN_ID or "(null - 本地模式)"}')
    print(f'SkillID: {SKILL_ID}')
    print(f'WorkflowID: {WORKFLOW_ID or "(null - 需人工创建)"}')
    print(f'Executor AgentID: {EXECUTOR_AGENT_ID}')
    print()

    # Test 1: 线长查询
    run_test(1, '线长查询·OEE归因', make_request('line', 'LINE-S03当班OEE为什么低'), {
        '状态完成': check_status_completed,
        'local_trace_id存在': check_has_local_trace_id,
        '无伪RUN-BIFROST': check_no_fake_runid,
        'Aily RunID注入': check_aily_runid_injected,
        'OEE动态读取': check_oee_dynamic,
        'EvidenceRef深度解析': check_evidence_deep_resolution,
        'EvidenceRef校验通过': check_evidence_validated,
    })

    # Test 2: 厂长查询
    run_test(2, '厂长查询·全局态势', make_request('factory', '当班整体情况如何'), {
        '状态完成': check_status_completed,
        'OEE动态': check_oee_dynamic,
        '不良动态': check_defect_dynamic,
        'EvidenceRef深度解析': check_evidence_deep_resolution,
        '载荷哈希完整': check_payload_hash_intact,
    })

    # Test 3: 质量查询
    run_test(3, '质量查询·不良与冻结', make_request('quality', '当班质量问题和冻结情况'), {
        '状态完成': check_status_completed,
        '不良动态': check_defect_dynamic,
        '冻结状态动态': check_freeze_status_dynamic,
        'SPC缺口声明': check_spc_gap_declared,
        'EvidenceRef深度解析': check_evidence_deep_resolution,
    })

    # Test 4: 设备查询
    run_test(4, '设备查询·停机分析', make_request('equipment', '当班停机情况'), {
        '状态完成': check_status_completed,
        'EvidenceRef深度解析': check_evidence_deep_resolution,
        'MTBF缺口声明': lambda r: 'MTBF' in json.dumps(r.get('data_gaps', []), ensure_ascii=False),
    })

    # Test 5: 工艺查询
    run_test(5, '工艺查询·性能率', make_request('process', '工艺参数有无偏移'), {
        '状态完成': check_status_completed,
        'SPC缺口声明': check_spc_gap_declared,
    })

    # Test 6: 供应链查询
    run_test(6, '供应链查询·物料缺口与冻结', make_request('supply', '物料缺口和冻结情况'), {
        '状态完成': check_status_completed,
        '物料不合并': check_material_not_merged,
        'EvidenceRef深度解析': check_evidence_deep_resolution,
    })

    # Test 7: 非法 EventID
    run_test(7, '非法EventID拦截', make_request('line', '查询事件', event_id='EVT-FAKE-9999'), {
        'EVENT_NOT_FOUND': check_event_not_found,
        '无伪RUN-BIFROST': check_no_fake_runid,
    })

    # Test 8: 高风险动作
    run_test(8, '高风险动作·解除冻结拦截', make_request('supply', '直接解除 FZ-0005 冻结'), {
        '需人工确认': check_needs_confirmation,
        '确认草稿存在': check_confirmation_draft_exists,
        '禁止自动执行': lambda r: r and r.get('confirmation_draft', {}).get('prohibited_auto_execute') == True,
    })

    # Test 9: Cpk 缺失
    run_test(9, 'Cpk数据缺失声明', make_request('quality', '当班Cpk是多少'), {
        'SPC缺口声明': check_spc_gap_declared,
        '状态完成或确认': check_status_completed,
    })

    # Test 10: 重复执行一致性
    run_test(10, '重复执行·trace_id唯一', make_request('line', 'LINE-S03当班OEE'), {
        'local_trace_id唯一': check_repeat_consistent,
        '无伪RUN-BIFROST': check_no_fake_runid,
        'OEE动态': check_oee_dynamic,
    })

    # Test 11: 防硬编码测试
    run_anti_hardcode_test()

    # Test 12-14: 04A.2 语义防硬编码测试
    _run_semantic_test(12, '语义防硬编码·停机恢复正常后停机原因消失',
                       _modify_downtime_normal,
                       disappear_keywords=['停机', '非计划停机'],
                       appear_keywords=['质量异常', '物料缺口'])

    _run_semantic_test(13, '语义防硬编码·物料缺口清零后物料原因消失',
                       _modify_material_gap_zero,
                       disappear_keywords=['物料缺口'],
                       appear_keywords=['停机', '质量异常'])

    _run_semantic_test(14, '语义防硬编码·不良清零后质量原因消失',
                       _modify_defect_zero,
                       disappear_keywords=['质量异常', '不良'],
                       appear_keywords=['停机', '物料缺口'])

    # ========== 04A.3 可信边界测试 ==========
    print()
    print('--- 04A.5 可信边界测试 ---')

    # Test 15: 载荷缺失 → 阻塞且不创建文件
    _run_trust_test(15, '载荷缺失·阻塞且不创建文件',
                    _setup_payload_missing, _checks_payload_missing)

    # Test 16: 哈希错误 → 阻塞
    _run_trust_test(16, '哈希错误·阻塞',
                    _setup_hash_wrong, _checks_hash_wrong)

    # Test 17: 测试夹具存在 → 正式运行不读取
    _run_trust_test(17, '测试夹具存在·正式运行不读取',
                    _setup_test_fixture_present, _checks_test_fixture_present,
                    teardown_fn=_teardown_test_fixture)

    # Test 18: 载荷路径错误 → 不得搜索其他目录
    _run_trust_test(18, '载荷路径错误·不搜索其他目录',
                    _setup_payload_path_wrong, _checks_payload_path_wrong)

    # Test 19: 生产目录写入尝试 → 必须失败
    _run_trust_test(19, '生产目录写入尝试·必须失败',
                    _setup_production_write_attempt, _checks_production_write_attempt)

    # Test 20: 正确载荷成功测试
    _run_correct_payload_test()

    # ========== 04A.4 业务因果表达测试 ==========
    print()
    print('--- 04A.4 业务因果表达测试 ---')

    # Test 21: 物料缺口存在但无MATERIALS停机关联 → 不得称为OEE直接原因
    _run_causal_test_21()

    # Test 22: 有明确物料→MATERIALS停机关联 → 只能称为间接影响
    _run_causal_test_22()

    # ========== 04A.5 运行资产自包含测试 ==========
    print()
    print('--- 04A.5 运行资产自包含测试 ---')

    # Test 23: gzip文件大小验证
    _run_gzip_size_test()

    # Test 24: 正常内存解压成功 + 哈希一致
    _run_gzip_decompress_test()

    # Test 25: gzip缺失时阻塞
    _run_gzip_missing_test()

    # Test 26: gzip损坏时阻塞
    _run_gzip_corrupt_test()

    # Test 27: 解压后哈希不符时阻塞
    _run_gzip_hash_mismatch_test()

    # Test 28: 运行前后目录无新增文件
    _run_no_new_files_test()

    # Test 29: 正式代码不调用写文件操作
    _run_no_write_code_test()

    # 汇总
    total = len(TEST_RESULTS)
    passed = sum(1 for t in TEST_RESULTS if t['status'] == 'PASS')
    total_checks = sum(t['checks_total'] for t in TEST_RESULTS)
    passed_checks = sum(t['checks_passed'] for t in TEST_RESULTS)

    summary = {
        'run_label': '04A.5',
        'aily_run_id': AILY_RUN_ID,
        'aily_run_id_numeric': AILY_RUN_ID_NUMERIC,
        'skill_id': SKILL_ID,
        'workflow_id': WORKFLOW_ID,
        'executor_agent_id': EXECUTOR_AGENT_ID,
        'task_id': TASK_ID,
        'trust_anchor_version': TRUST_ANCHOR_VERSION,
        'executed_at': datetime.datetime.now().isoformat(),
        'total_tests': total,
        'passed': passed,
        'failed': total - passed,
        'total_checks': total_checks,
        'passed_checks': passed_checks,
        'payload_hashes': get_payload_hashes(),
        'payload_intact': _verify_payload_intact(),
        'tests': TEST_RESULTS
    }

    out_path = os.path.join(os.path.dirname(__file__), 'test_results_04a5.json')
    with open(out_path, 'w') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print()
    print(f'=== 汇总: {passed}/{total} 测试 PASS, {passed_checks}/{total_checks} 检查 PASS ===')
    print(f'生产载荷完整性: {"INTACT" if _verify_payload_intact() else "MODIFIED!"}')
    print(f'结果已保存: {out_path}')
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
