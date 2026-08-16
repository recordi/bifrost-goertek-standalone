# BIFROST 规则试算器

这是规则配置的安全沙盒，不直接写入 Excel、语义数据面、Overview/Event 载荷或业务系统。

## 支持的规则

- 公式：数字、字段名、`+ - * / %`、括号、`sum/avg/count/min/max/abs`
- 阈值：目标值、预警值、严重值、判断方向、最小样本量
- 版本：`rule_version`、`effective_from`、`draft/published/retired`
- 试算：比较基线规则和候选规则，输出指标值、状态、数据缺口和受影响指标

禁止任意 Python、SQL、文件访问、网络调用、字符串函数和副作用函数。候选规则必须先通过试算与人工审批，才允许进入正式发布流程。
