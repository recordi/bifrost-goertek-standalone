# OMP 第二轮 Grok 双审查验收报告

日期：2026-08-14

## 结论

BIFROST 主链路已用修正后的脱敏测试夹具跑通。业务计算和硬性门禁通过，主链的多视口展示审查通过；同学 daemon 作为只读、非权威的能力桥接也能运行，但其独立生成的展示产物被界面审查拒绝，因此不能直接替换 BIFROST 正式 UI。

## 1. 测试边界

- 数据：`fixtures/goertek/omp-bridge-input.csv`
- 数据标签：`SYNTHETIC_GOERTEK_FIXTURE_V2`
- 性质：团队合成测试数据，不是歌尔内部业务数据
- 运行模式：只读；不写入正式 Skill、正式载荷或正式 UI
- 模型：`custom-grok/grok-4.6`，通过本地 OMP OpenAI-compatible Bridge 调用

## 2. 主链路结果

RunID：`run_01KZZ93N2EF5K1WENQ1Q4ZMPKA`

| 项目 | 结果 |
|---|---|
| 状态 | done |
| 阶段 | deliver |
| Gate 1/2/3/5 | 全部 PASS |
| 多视口展示审查 | pass |
| 计划/查询/事实复核/叙述/生成 | Grok 完成 |
| 证据与守恒校验 | 确定性程序完成 |

主链计算结果：

| 产线 | OEE | 首过良率 | 产出达成率 |
|---|---:|---:|---:|
| LINE-A02 | 74.9% | 94.21% | 88.5% |
| LINE-A01 | 72.1% | 94.72% | 93.4% |
| LINE-B01 | 68.8% | 91.89% | 94.7% |
| 全部 | 71.9% | 93.63% | 91.9% |

所有 OEE 值均位于指标定义域 `[0,1]`，并保留 `low_sample` 标记，未把小样本结果伪装成正式生产结论。

## 3. 同学能力桥接结果

RunID：`run_01KZZ9PX11B1YRYT10PDPGWTKG`

- daemon 状态：done
- 桥接状态：available
- `read_only=true`
- `non_authoritative=true`
- Gate 1/2/3/5：全部 PASS
- 独立展示审查：reject

拒绝原因主要是其独立生成 HTML 的展示规范问题（例如装饰性左边框、字体规范告警、截图输入不足），不是 BIFROST 主链的业务事实错误。

因此本轮确认的相容方式是：

```text
同学 Skill/daemon → 只读能力插件 → 返回审查意见
BIFROST 主链     → 事实、证据、权限、决策和正式 UI 的唯一权威
```

不能把同学 daemon 生成的 HTML 或未经过 BIFROST 事实绑定的结论直接合并进正式产品。

## 4. 本轮修正

此前测试夹具的 `ideal_cycle_time=1` 会造成 OEE 超过 100%，已调整为与 480 分钟班次相容的秒级节拍，并修复了停机时间、可用时间和实际产出的约束关系。

新增确定性检查：

```text
.omp/integration/validate_omp_fixture.py
```

它会检查字段、良品/不良守恒、停机/可用时间关系、首过良率边界和 OEE 定义域，避免让 Grok 解读明显不可能的数据。

## 5. 回归测试

- 测试夹具校验：PASS
- peer daemon bridge：6/6 PASS
- peer skill adapters：5/5 PASS
- governance precheck：3/3 PASS
- UI peer overlay：5/5 PASS

双审查仲裁结果：`PASS_WITH_PEER_ADVISORY`（见 `.omp/dual-review-v2.json`）。这表示主链可以通过本轮测试，但同学 daemon 只作为建议来源，不能改变主链结论。

## 6. 下一阶段建议

1. 保留主链的业务事实和正式 UI，不接收同学 daemon 的 HTML 成品。
2. 将同学能力限定为“只读业务/界面审查 Skill”，输出结构化 findings。
3. 增加一个确定性仲裁器：主链门禁失败或 Grok 审查出现 `must_fix` 时，一律标记需修复，不允许自动发布。
4. 下一轮应对真实 BIFROST UI 载荷做视觉审查，而不是只审查 Grok 临时生成的独立 HTML。
