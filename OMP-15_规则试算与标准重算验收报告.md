# OMP-15 规则试算与标准重算验收报告

## 本阶段完成

- 新增受限公式引擎：`.omp/rules/rule_engine.py`
- 新增规则集：`.omp/rules/rule_definitions_v1.json`
- 新增规则计算合同：`packages/contracts/schemas/rule_calculation.schema.json`
- 新增测试：`.omp/integration/test_rule_engine.py`
- 新增本地接口：`POST /api/rule-simulate`

## 支持能力

- OEE、良率、换产超时公式
- 目标值、预警值、严重值和高低方向
- 最小样本量与数据缺口
- 规则版本、生效时间、草稿/发布/退役状态
- 基线规则与候选规则的差异试算
- 只读、无写回、无任意代码执行

## 验收结果

- 规则引擎测试：4/4 PASS
- 公式白名单：通过
- 任意 Python/不安全运算拒绝：通过
- 规则版本差异试算：通过
- 最小样本量门控：通过
- 试算接口：`status=ok`
- 合同版本：`BIFROST-RULE-SIMULATION-v1`
- `readonly=true`
- `source_write_performed=false`

## 重要边界

当前试算接口已经能真实计算和比较新旧规则，但尚未把规则编辑控件放入正式 UI。正式发布仍需人工审批；历史事件不能被静默改写。
