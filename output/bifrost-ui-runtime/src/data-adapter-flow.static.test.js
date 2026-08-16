import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const dataSource = fs.readFileSync(path.join(here, "data.jsx"), "utf8");
const pageSource = fs.readFileSync(path.join(here, "pages.jsx"), "utf8");
const appSource = fs.readFileSync(path.join(here, "app.jsx"), "utf8");
const componentSource = fs.readFileSync(path.join(here, "components.jsx"), "utf8");

test("dynamic adapter keeps an explicit rollback path", () => {
  assert.match(dataSource, /preview_backup/);
  assert.match(dataSource, /function rollbackDynamicPayloads\(\)/);
  assert.match(dataSource, /preview_active = false/);
});

test("UI separates confirmation from applying a preview", () => {
  assert.match(pageSource, /runAdaptation\(true\)/);
  assert.match(pageSource, /applyPreview/);
  assert.match(pageSource, /mappingApproved/);
  assert.match(pageSource, /pendingMappingIds/);
  assert.match(pageSource, /确认全部待审核映射/);
  assert.match(pageSource, /rollbackPreview/);
});

test("dynamic ratios require an explicit value mode and bounded value", () => {
  assert.match(dataSource, /normalizeDynamicRatioMetric/);
  assert.match(dataSource, /value_mode_required/);
  assert.match(dataSource, /value_missing/);
  assert.match(dataSource, /ratio_out_of_range/);
  assert.match(dataSource, /percentage_out_of_range/);
  assert.match(dataSource, /adaptation_warnings/);
});

test("peer overlay is isolated unless its event, dataset, SHA and manifest pass", () => {
  assert.match(dataSource, /validatePeerOverlayPayload/);
  assert.match(dataSource, /manifest_source_sha_missing/);
  assert.match(dataSource, /manifest_payload_hash_mismatch/);
  assert.match(dataSource, /sha256Response/);
  assert.match(dataSource, /dataset_id_not_adapter_test/);
  assert.match(dataSource, /peer_overlay_error/);
  assert.match(pageSource, /辅助分析暂不可用/);
  assert.match(pageSource, /peer_role_projections/);
  assert.doesNotMatch(pageSource, /const roleSkills = \{/);
});

test("governance issues create readonly human-review drafts", () => {
  assert.match(pageSource, /\/api\/governance-action-draft/);
  assert.match(pageSource, /需人工确认/);
});

test("line role renders single-line OEE trend payloads", () => {
  assert.match(dataSource, /function buildSingleTrendOption\(chartData, lineId = null\)/);
  assert.match(pageSource, /trendChart\.type === "line"/);
  assert.match(pageSource, /buildSingleTrendOption\(data, effectiveScope\)/);
  assert.match(dataSource, /key === "__single_line__" \? \(line\.label \|\| "当前产线"\)/);
  assert.match(pageSource, /buildSingleTrendOption\(chart\.data, selectedDrilldownLine\)/);
});

test("role scope follows payload dimensions instead of a hardcoded line", () => {
  assert.match(dataSource, /function getDefaultScopeForRole\(role\)/);
  assert.match(dataSource, /function resolveScopeForRole\(role, requestedScope\)/);
  assert.match(pageSource, /const effectiveScope = resolveScopeForRole\(role, scope\)/);
  assert.match(appSource, /setScope\(resolveScopeForRole\(newRole, scope\)\)/);
  assert.doesNotMatch(appSource, /setScope\("LINE-S01"\)/);
});

test("line identity is not replaced by scenario-character labels", () => {
  assert.match(dataSource, /function displayLineLabel\(lineId, rawLabel\)/);
  assert.match(dataSource, /if \(datasetId === "TEAM_ENGINEERED_SIMULATION"/);
  assert.match(dataSource, /return t_scope\(lineId\)/);
  assert.match(dataSource, /function buildTrendOption/);
  assert.match(dataSource, /displayLineLabel\(key, line\.label\)/);
});

test("validated peer analysis becomes a first-class business finding", () => {
  assert.match(dataSource, /function buildValidatedDerivedInsights/);
  assert.match(dataSource, /formal_integration_status === "attached_additive"/);
  assert.match(dataSource, /does_not_replace_authoritative_metrics: true/);
  assert.match(dataSource, /source_task_status !== "needs_confirmation"/);
  assert.match(pageSource, /本角色分析结论/);
  assert.match(pageSource, /正式结论/);
  assert.match(pageSource, /formal_derived_insights\?\.formal_integration_status === "attached_additive"/);
  assert.match(pageSource, /关键指标/);
  assert.match(pageSource, /function businessEvidenceLabel\(ref(?:,\s*skillId(?:\s*=\s*""\s*)?)?\)/);
  assert.match(pageSource, /查看技术证据索引/);
});

test("factory dashboard supports line-to-detail drilldown", () => {
  assert.match(pageSource, /selectedDrilldownLine/);
  assert.match(pageSource, /点击查看该产线的班次、停机和质量明细/);
  assert.match(pageSource, /产线详情 ·/);
  assert.match(pageSource, /返回全厂总览/);
  assert.match(pageSource, /selectedLineStops/);
  assert.match(pageSource, /selectedLineDefects/);
  assert.match(pageSource, /row\.type \|\| row\.defect_type/);
  assert.match(pageSource, /displayBusinessReason\(row\.label/);
});

test("AI questions can select a business view and time window", () => {
  assert.match(appSource, /handleAiViewIntent/);
  assert.match(appSource, /last_7_shifts/);
  assert.match(appSource, /setCurrentPage\(nextPage\)/);
  assert.match(componentSource, /onViewIntent\?\.\(text\)/);
});

test("business charts translate raw downtime and defect codes", () => {
  assert.match(dataSource, /BUSINESS_REASON_LABELS/);
  assert.match(dataSource, /换产与调试/);
  assert.match(dataSource, /设备故障/);
  assert.match(dataSource, /displayBusinessReason\(r\.label \|\| r\.group/);
});
