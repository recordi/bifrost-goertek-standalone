# GENERATED FILE — DO NOT EDIT.
#
# Source: packages/contracts/schemas/*.schema.json
# Regenerate: pnpm --filter @bifrost/contracts gen
#
# Structural models only. Conditional (if/then) rules live in conditionals.py.

from __future__ import annotations

from enum import IntEnum, StrEnum
from typing import Any, Literal

from pydantic import (AnyUrl, AwareDatetime, BaseModel, ConfigDict, Field,
                      PositiveFloat, RootModel, confloat, conint, constr)


class Level(StrEnum):
    """
    失败时的处置级别。block 级断言失败则整个 run 停在数据层，不进制作。
    """
    block = 'block'
    warn = 'warn'


class AssertionSpec(RootModel[constr(pattern=r'^(row_count_gt:\d+|no_null:[A-Za-z_][A-Za-z0-9_]*|in_domain:[a-z][a-z0-9_]*|unique_key:[A-Za-z_][A-Za-z0-9_]*(,[A-Za-z_][A-Za-z0-9_]*)*|temporal_dense:[A-Za-z_][A-Za-z0-9_]*,(hour|day|week|month|quarter|year)|sum_reconcile:[A-Za-z_][A-Za-z0-9_]*,[A-Za-z_][A-Za-z0-9_]*)$', max_length=256)]):
    root: constr(pattern=r'^(row_count_gt:\d+|no_null:[A-Za-z_][A-Za-z0-9_]*|in_domain:[a-z][a-z0-9_]*|unique_key:[A-Za-z_][A-Za-z0-9_]*(,[A-Za-z_][A-Za-z0-9_]*)*|temporal_dense:[A-Za-z_][A-Za-z0-9_]*,(hour|day|week|month|quarter|year)|sum_reconcile:[A-Za-z_][A-Za-z0-9_]*,[A-Za-z_][A-Za-z0-9_]*)$', max_length=256)
    """
    断言表达式，形如 <断言名>:<参数>。合法断言名：row_count_gt（参数为整数）、no_null（参数为列名）、in_domain（参数为指标名，上下界取自 metrics.yml）、unique_key（参数为逗号分隔列名）、temporal_dense（参数为 列名,颗粒度）、sum_reconcile（参数为 部分列,总计列）。
    """


class Kind(StrEnum):
    """
    基准类型。target 对目标，period_over_period 环比，year_over_year 同比，peer 同类对比，benchmark 行业基准。
    """
    target = 'target'
    period_over_period = 'period_over_period'
    year_over_year = 'year_over_year'
    peer = 'peer'
    benchmark = 'benchmark'


class Kind1(StrEnum):
    """
    图表类型。
    """
    line = 'line'
    bar = 'bar'
    area = 'area'
    scatter = 'scatter'


class Marks(StrEnum):
    """
    承载数据的 SVG 元素类型，必须与 kind 匹配：line→path、area→path、bar→rect、scatter→circle。gate 2 按这个值去 DOM 里找要检查几何的元素。
    """
    path = 'path'
    rect = 'rect'
    circle = 'circle'


class Order(StrEnum):
    """
    x 轴排序方向，必须与序列的实际顺序一致。gate 2 会核对：声明 asc 但序列 x 实际递减即为不一致。none 表示不保证顺序，只对 category 轴合法。
    """
    asc = 'asc'
    desc = 'desc'
    none = 'none'


class Orientation(StrEnum):
    """
    bar 专用的方向。vertical 时数值映射到 y 轴，horizontal 时映射到 x 轴——几何反算的轴向据此选择。默认 vertical。
    """
    vertical = 'vertical'
    horizontal = 'horizontal'


class PlotRect(BaseModel):
    """
    绘图区在 SVG 用户坐标系中的矩形，即 domain 两端所对应的像素边界。内联 SVG 的几何反算需要它：value = domain[0] + (y_bottom - py) / height * (domain[1] - domain[0])。开发文档只写了「按 domain 反算」而没定义绘图区边界，若缺省则 gate 只能假定路径自身的坐标极值对应 domain 两端——那样「整条线整体平移或缩放」这类错误就查不出来。因此内联 SVG 强烈建议声明本字段；缺省时 gate 2 退化为极值归一化比对并记一条警告。ECharts 路径不需要它（DOM 由库生成，不走几何检查）。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    height: PositiveFloat
    """
    绘图区高度，必须为正。
    """
    width: PositiveFloat
    """
    绘图区宽度，必须为正。
    """
    x: float
    """
    绘图区左边界的 SVG x 坐标。
    """
    y: float
    """
    绘图区上边界的 SVG y 坐标。注意 SVG 的 y 轴向下增长，所以这里对应 domain 的上界。
    """


class FieldModel(StrEnum):
    """
    取序列的哪个字段作 x。period 对应 temporal 的 x 轴，category 对应 nominal/ordinal 的 x 轴。gate 2 会核对它与序列 x.semantic 是否相容。
    """
    period = 'period'
    category = 'category'


class Field1(StrEnum):
    """
    取序列的哪个字段作 y。当前只允许 value，即 series.y.values。
    """
    value = 'value'


class QualityFlag(RootModel[constr(pattern=r'^(missing_value|unit_inconsistent|duplicate_key|out_of_domain|temporal_gap|referential_broken)(:\d+)?$')]):
    root: constr(pattern=r'^(missing_value|unit_inconsistent|duplicate_key|out_of_domain|temporal_gap|referential_broken)(:\d+)?$')


class SampleValue(RootModel[constr(max_length=256)]):
    root: constr(max_length=256)


class DatasetId(RootModel[constr(pattern=r'^ds_[a-z0-9_]+$', max_length=96)]):
    root: constr(pattern=r'^ds_[a-z0-9_]+$', max_length=96)
    """
    数据集标识。查询里以 {{dataset_id}} 占位符出现，由 runner 替换为实际表引用——模型永远看不到真实连接串、库名或文件路径。
    """


class Kind2(StrEnum):
    """
    来源类型。Task 3 Step 2: 仅支持 csv/xlsx/parquet 文件格式，不支持 json/jsonl。
    """
    csv = 'csv'
    xlsx = 'xlsx'
    parquet = 'parquet'
    mysql = 'mysql'
    postgres = 'postgres'
    bitable = 'bitable'


class Row(RootModel[conint(ge=0)]):
    root: conint(ge=0)


class Evidence(BaseModel):
    """
    可复核的证据。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    note: constr(min_length=1, max_length=1000)
    """
    人类可读的判定说明。
    """
    rows: list[Row] | None = Field(None, max_length=100)
    """
    命中的行号（0 基，指源文件数据行）。
    """


class FixCost(StrEnum):
    """
    修复成本估计。
    """
    low = 'low'
    medium = 'medium'
    high = 'high'


class DefectType(StrEnum):
    """
    六类数据缺陷。D 类 skill 负责判定规则，契约只定义结构。
    """
    missing_value = 'missing_value'
    unit_inconsistent = 'unit_inconsistent'
    duplicate_key = 'duplicate_key'
    out_of_domain = 'out_of_domain'
    temporal_gap = 'temporal_gap'
    referential_broken = 'referential_broken'


class DefinitionRef(RootModel[constr(pattern=r'^metrics\.yml#[a-z][a-z0-9_]*@v\d+$')]):
    root: constr(pattern=r'^metrics\.yml#[a-z][a-z0-9_]*@v\d+$')
    """
    口径引用，格式 metrics.yml#<metric>@v<version>。它把每个数值钉死到某一版指标定义上，是事实评审判定「口径冲突的两个数被并列」的依据。
    """


class Type(StrEnum):
    """
    维度类型。categorical 用于分类，time 用于时间轴，geo 用于地理。
    """
    categorical = 'categorical'
    time = 'time'
    geo = 'geo'


class Value(RootModel[constr(max_length=128)]):
    root: constr(max_length=128)


class DisplayFormat(BaseModel):
    """
    显示格式。runner 按它生成 FactSet 的 display 字段——显示值由确定性代码产出，不由模型格式化，这消掉了一整类「同一个数在不同卡片精度不同」的事故。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    format: constr(pattern=r'^[0#,.]+%?$', max_length=32)
    """
    数字格式串，采用 numeral.js 风格，例如 0.0% / 0,0 / 0.00。
    """
    precision: conint(ge=0, le=10)
    """
    小数位数。gate 2 的精度白名单用它判定元素文本与 display 的差异是否可接受。
    """


class Dispute(BaseModel):
    """
    一条口径争议。有 resolved_by 表示已仲裁；没有则该指标的事实会被打上 disputed_definition 标记。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    note: constr(min_length=1, max_length=2000)
    """
    争议内容。
    """
    resolved_by: constr(max_length=2000) | None = None
    """
    仲裁结论。为空表示争议未决，该指标的事实要打 disputed_definition。
    """
    with_: constr(min_length=1, max_length=128) = Field(..., alias='with')
    """
    争议对方，通常是部门名。
    """


class FactFlag(RootModel[constr(pattern=r'^(low_sample|temporal_gap(:\d+[dhwm])?|disputed_definition|stale)$')]):
    root: constr(pattern=r'^(low_sample|temporal_gap(:\d+[dhwm])?|disputed_definition|stale)$')
    """
    事实标记，是评审的输入。low_sample 表示 row_count 低于指标声明阈值；temporal_gap 后可带天数如 temporal_gap:3d；disputed_definition 表示该指标在 metrics.yml 里有未决争议；stale 表示口径版本已落后。事实评审看到 low_sample 就应要求结论加注脚，gate 5 看到 low_sample 仍给强结论则阻断。
    """


class FactId(RootModel[constr(pattern=r'^[a-z0-9][a-z0-9_-]*(\.[a-z0-9][a-z0-9_-]*)+$', max_length=160)]):
    root: constr(pattern=r'^[a-z0-9][a-z0-9_-]*(\.[a-z0-9][a-z0-9_-]*)+$', max_length=160)
    """
    事实 id。命名规范 <metric>.<dim值以点连接，小写>.<时间>，序列加 .trend.<窗口>。禁止空格与中文，因为它要写进 HTML 属性并被 gate 2 静态解析。
    """


class Record(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    fields: dict[str, Any] = Field(..., min_length=1)
    """
    记录字段。键为多维表格的字段名，值的类型取决于字段配置（文本、数字、日期、多选等）。字段名与类型必须与目标表格的 schema 匹配。
    """


class FeishuBitableWrite(BaseModel):
    """
    飞书多维表格批量写入请求。用于将 FactSet 或治理报告写入飞书多维表格，单次上限 1000 条（飞书 API 限制）。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    app_token: constr(pattern=r'^[a-zA-Z0-9_-]+$', min_length=10, max_length=64)
    """
    多维表格的 app token。从飞书多维表格 URL 中提取，格式形如 bascn... 开头的字符串。
    """
    records: list[Record] = Field(..., max_length=1000, min_length=1)
    """
    待写入的记录数组。每条记录的 fields 对象的键为多维表格的字段名，值为对应类型的数据。单次请求上限 1000 条（飞书 API 限制），超过需分批。
    """
    table_id: constr(pattern=r'^[a-zA-Z0-9_-]+$', min_length=10, max_length=64)
    """
    表格 id。一个多维表格（app）下可包含多张表（table），格式形如 tbl... 开头的字符串。
    """


class Config(BaseModel):
    """
    卡片配置。控制展示模式和转发权限。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    enable_forward: bool | None = None
    """
    是否允许转发。默认允许，限制分发时设为 false。
    """
    wide_screen_mode: bool
    """
    是否启用宽屏模式。Bifrost 卡片统一开启以容纳图表与指标。
    """


class Element(BaseModel):
    model_config = ConfigDict(
        extra='allow',
    )
    actions: list[dict[str, Any]] | None = None
    """
    按钮列表。tag 为 action 时存在。
    """
    tag: constr(min_length=1, max_length=32)
    """
    元素标签。div 用于文本块，markdown 用于格式化文本，action 用于按钮组，hr 用于分隔线，chart 用于内嵌图表（自定义）。
    """
    text: dict[str, Any] | None = None
    """
    文本内容。tag 为 div 或 markdown 时存在。
    """


class Template(StrEnum):
    """
    主题色模板。blue 用于常规报告，green 用于正向结论，red 用于异常告警，yellow 用于提醒，grey 用于中性内容。
    """
    blue = 'blue'
    green = 'green'
    red = 'red'
    yellow = 'yellow'
    grey = 'grey'


class Title(BaseModel):
    """
    标题内容。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    content: constr(min_length=1, max_length=100)
    """
    标题文本，建议 20 字以内。
    """
    tag: Literal['plain_text']
    """
    文本类型。Bifrost 卡片标题统一使用纯文本。
    """


class Header(BaseModel):
    """
    卡片头部。承载标题与主题色。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    template: Template | None = None
    """
    主题色模板。blue 用于常规报告，green 用于正向结论，red 用于异常告警，yellow 用于提醒，grey 用于中性内容。
    """
    title: Title
    """
    标题内容。
    """


class FeishuCard(BaseModel):
    """
    飞书消息卡片 JSON 2.0 结构（Bifrost 使用的子集）。用于承载分析结论、关键数字、看板跳转和任务创建入口。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    config: Config
    """
    卡片配置。控制展示模式和转发权限。
    """
    elements: list[Element] = Field(..., max_length=50, min_length=1)
    """
    卡片元素列表。按顺序渲染，支持文本、图表、按钮等组件。
    """
    header: Header
    """
    卡片头部。承载标题与主题色。
    """


class Status(StrEnum):
    """
    交付状态。sent 表示已成功推送，failed 表示推送失败（网络错误、API 限流等），disabled 表示该岗位的推送配置已关闭。
    """
    sent = 'sent'
    failed = 'failed'
    disabled = 'disabled'


class Severity1(StrEnum):
    """
    严重度。must_fix 只能用于四类可客观判定的问题：口径违规、事实绑定失败、误导性编码、岗位越权。审美与措辞一律 should_fix——把主观偏好升格为阻断项会让评审失去公信力。
    """
    must_fix = 'must_fix'
    should_fix = 'should_fix'


class MemId(RootModel[constr(pattern=r'^mem_[0-9a-z]+$', max_length=64)]):
    root: constr(pattern=r'^mem_[0-9a-z]+$', max_length=64)
    """
    记忆条目 id。
    """


class Kind3(StrEnum):
    """
    记忆类型。conclusion 结论，business_exception 业务例外，definition_dispute 口径争议，rejected_proposal 被否决的提案，preference 偏好。
    """
    conclusion = 'conclusion'
    business_exception = 'business_exception'
    definition_dispute = 'definition_dispute'
    rejected_proposal = 'rejected_proposal'
    preference = 'preference'


class Layer(StrEnum):
    """
    记忆层级。task 只在本次运行内有效，project 跨运行但限本项目，org 跨项目。
    """
    task = 'task'
    project = 'project'
    org = 'org'


class Domain(BaseModel):
    """
    值域。in_domain 断言的 lo/hi 取自这里，不在断言里硬编码；gate 也用它判断 out_of_domain 缺陷。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    max: float
    """
    上界，含。
    """
    min: float
    """
    下界，含。
    """


class Type1(StrEnum):
    """
    指标类型。simple 单一聚合，ratio 分子分母，cumulative 累计，derived 由其它指标推导。
    """
    simple = 'simple'
    ratio = 'ratio'
    cumulative = 'cumulative'
    derived = 'derived'


class MetricExpr(BaseModel):
    """
    一个聚合表达式。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    expr: constr(min_length=1, max_length=2000)
    """
    SQL 聚合表达式，例如 sum(good_qty * ideal_cycle_time)。loader 会做白名单校验：拒绝 DDL/DML、文件读取函数与系统函数。
    """


class MetricsVersion(RootModel[conint(ge=1)]):
    root: conint(ge=1)
    """
    metrics.yml 的版本号，每次修改递增。FactSet 与 QuerySet 都要带上它，口径变更后旧产物可被识别为 stale。
    """


class Depth(StrEnum):
    """
    分析深度。
    """
    snapshot = 'snapshot'
    trend = 'trend'
    comparison = 'comparison'
    drilldown = 'drilldown'
    correlation = 'correlation'


class ExpectedShape(StrEnum):
    """
    预期的表达形态。它是 B 类图表选型 skill 的输入键，也是呈现评审 chart_fitness 维度的判定基准。
    """
    single_kpi = 'single_kpi'
    trend = 'trend'
    ranked_comparison = 'ranked_comparison'
    composition = 'composition'
    distribution = 'distribution'
    correlation = 'correlation'
    flow = 'flow'


class Ratio01(RootModel[confloat(ge=0.0, le=1.0)]):
    root: confloat(ge=0.0, le=1.0)
    """
    0 到 1 之间的比率。
    """


class Kind4(StrEnum):
    """
    评审类型。fact 是事实评审（看数值与口径），presentation 是呈现评审（看表达与视觉）。
    """
    fact = 'fact'
    presentation = 'presentation'


class Verdict(StrEnum):
    """
    结论。存在任一 must_fix 时必须为 reject——这条由 daemon 强制校验，模型自报 pass 不算数。
    """
    pass_ = 'pass'
    reject = 'reject'


class DecisionHorizon(StrEnum):
    """
    决策周期。它决定默认时间颗粒度与趋势窗口长度。
    """
    shift = 'shift'
    week = 'week'
    month = 'month'
    quarter = 'quarter'


class Density(StrEnum):
    """
    信息密度偏好。
    """
    low = 'low'
    medium = 'medium'
    high = 'high'


class Narrative(BaseModel):
    """
    叙述约束。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    max_conclusions: conint(ge=1, le=20)
    """
    结论条数上限。超过就是信息过载，呈现评审会扣 readability。
    """
    require_action: bool
    """
    每条结论是否必须带行动建议。呈现评审的 role_fit 维度据此判定。
    """
    style: constr(min_length=1, max_length=500)
    """
    叙述风格要求，自然语言，注入制作节点提示词。
    """


class FallbackPolicy(StrEnum):
    """
    轮次耗尽仍未通过时的处置。我们选 block 而不是 ship_best：仍有 must_fix 未清零时不发布、转人工。评审不能阻断就只是一份没人读的报告。
    """
    block = 'block'
    ship_best = 'ship_best'


class ScoreScale(IntEnum):
    """
    评分满分。
    """
    integer_10 = 10


class Rubric(BaseModel):
    """
    一套评分标准。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    fallback_policy: FallbackPolicy
    """
    轮次耗尽仍未通过时的处置。我们选 block 而不是 ship_best：仍有 must_fix 未清零时不发布、转人工。评审不能阻断就只是一份没人读的报告。
    """
    max_rounds: conint(ge=1, le=5)
    """
    最大评审轮次。
    """
    score_scale: ScoreScale
    """
    评分满分。
    """
    threshold: confloat(ge=0.0, le=10.0)
    """
    通过阈值。composite 低于它即使无 must_fix 也不算通过。
    """
    weights: dict[Literal['readability', 'chart_fitness', 'hierarchy', 'role_fit', 'craft', 'coverage', 'definition_consistency', 'sample_adequacy', 'anomaly_judgment'], confloat(ge=0.0, le=1.0)] = Field(..., min_length=1)
    """
    各维度权重，总和必须为 1（由 daemon 校验）。
    """


class RubricSet(BaseModel):
    """
    两类评审的评分标准集合。这是 daemon 重算 composite 与判定通过的唯一依据，不写在提示词里。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    fact: Rubric
    presentation: Rubric


class RunCreateRequest(BaseModel):
    """
    POST /api/projects/:id/runs 请求体。客户端只提供 brief、role_id、dataset_ids 和可选参数；daemon 内部加载 profile、role、metrics 和 factset。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    brief: constr(min_length=1, max_length=500)
    """
    用户提出的分析需求，如「分析本周各产线 OEE」
    """
    dataset_ids: list[DatasetId] = Field(..., max_length=10, min_length=1)
    """
    可用数据集 ID 列表，daemon 会为每个 dataset_id 生成或加载 Profile
    """
    params: dict[str, Any] | None = None
    """
    可选的渲染参数（如图表样式、分组维度），传递给 maker 节点
    """
    role_id: constr(pattern=r'^[a-z][a-z0-9_]*$')
    """
    角色 ID，引用 projects/<projectId>/roles/<role_id>.yml
    """


class RunId(RootModel[constr(pattern=r'^run_[0-9A-HJKMNP-TV-Z]{26}$')]):
    root: constr(pattern=r'^run_[0-9A-HJKMNP-TV-Z]{26}$')
    """
    单次运行标识。
    """


class Dim(StrEnum):
    """
    评分维度。presentation 用 readability / chart_fitness / hierarchy / role_fit / craft；fact 用 coverage / definition_consistency / sample_adequacy / anomaly_judgment。
    """
    readability = 'readability'
    chart_fitness = 'chart_fitness'
    hierarchy = 'hierarchy'
    role_fit = 'role_fit'
    craft = 'craft'
    coverage = 'coverage'
    definition_consistency = 'definition_consistency'
    sample_adequacy = 'sample_adequacy'
    anomaly_judgment = 'anomaly_judgment'


class Score(BaseModel):
    """
    一个维度的评分。evidence 必填——没有证据的分数是主观印象，无法复核也无法改进。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    dim: Dim
    """
    评分维度。presentation 用 readability / chart_fitness / hierarchy / role_fit / craft；fact 用 coverage / definition_consistency / sample_adequacy / anomaly_judgment。
    """
    evidence: constr(min_length=1, max_length=1000)
    """
    打这个分的具体依据，要指向产物里的具体位置或具体事实，不接受「整体不错」这类空话。
    """
    score: confloat(ge=0.0, le=10.0)
    """
    该维度得分，0 到 10。
    """


class Semantic(StrEnum):
    """
    列的语义类型。它是图表选型规则与 flint IR 的输入，不是存储类型。
    """
    nominal = 'nominal'
    ordinal = 'ordinal'
    quantitative = 'quantitative'
    ratio = 'ratio'
    temporal = 'temporal'
    identifier = 'identifier'
    geo = 'geo'


class Sensitivity(StrEnum):
    """
    敏感级别。与岗位画像的 max_sensitivity 联合决定字段可见性，是 gate 3 的判定依据之一。
    """
    public = 'public'
    internal = 'internal'
    confidential = 'confidential'


class Y1(BaseModel):
    """
    y 轴数值。gate 2 把 SVG 坐标按 ChartSpec 的 y.domain 反算回数值域后，与这里的 values 逐点比对，相对容差 2%。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    display_values: list[constr(max_length=64) | None] | None = None
    """
    各点的显示值，由 runner 按 display 段生成。图表标注数值时注入器用它，模型同样不参与格式化。
    """
    unit: constr(min_length=1, max_length=32)
    """
    单位。
    """
    values: list[float | None] = Field(..., min_length=1)
    """
    y 轴数值数组，原始数值未格式化，与 x.values 等长。null 表示该点缺失——缺失必须显式为 null，不许用 0 冒充，否则图会画出一条假的归零线。
    """


class Severity(StrEnum):
    """
    缺陷严重度。
    """
    low = 'low'
    medium = 'medium'
    high = 'high'
    critical = 'critical'


class SkillSlug(RootModel[constr(pattern=r'^[a-z][a-z0-9-]*$', max_length=64)]):
    root: constr(pattern=r'^[a-z][a-z0-9-]*$', max_length=64)
    """
    skill 文件名去掉扩展名，例如 a01-oee-loss-tree。skills/ 目录下的 id 一律用连字符分段（a01-、b02- 前缀），因此这里不能复用 common 的 Slug——Slug 只允许下划线，会把全部真实 skill id 判为非法。
    """


class Slug(RootModel[constr(pattern=r'^[a-z][a-z0-9_]*$', min_length=1, max_length=64)]):
    root: constr(pattern=r'^[a-z][a-z0-9_]*$', min_length=1, max_length=64)
    """
    小写标识符：字母开头，只含小写字母、数字和下划线。用于指标名、维度名、岗位 id 等一切需要写进配置与 HTML 属性的键。
    """


class SqlHash(RootModel[constr(pattern=r'^[0-9a-f]{8,64}$')]):
    root: constr(pattern=r'^[0-9a-f]{8,64}$')
    """
    产生该数值的查询指纹，用于溯源面板与跨事实口径一致性判定。同一 sql_hash 的事实必然出自同一次查询。
    """


class TimeGrain(StrEnum):
    """
    时间颗粒度。
    """
    hour = 'hour'
    day = 'day'
    week = 'week'
    month = 'month'
    quarter = 'quarter'
    year = 'year'


class Timestamp(RootModel[AwareDatetime]):
    root: AwareDatetime
    """
    ISO 8601 带时区偏移的时间戳，例如 2026-08-04T11:20:00+08:00。禁止裸的本地时间。
    """


class ViewportItem(RootModel[conint(ge=240, le=7680)]):
    root: conint(ge=240, le=7680)


class Viewport(RootModel[list[ViewportItem]]):
    """
    视口尺寸 [宽, 高]，单位 CSS 像素。
    """
    root: list[ViewportItem] = Field(..., max_length=2, min_length=2)
    """
    视口尺寸 [宽, 高]，单位 CSS 像素。
    """


class AssertionResult(BaseModel):
    """
    一条断言的执行结果。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    assertion: AssertionSpec
    """
    被执行的断言，与 QuerySet 里声明的字符串一致。
    """
    checked_rows: conint(ge=0)
    """
    实际检查的行数。
    """
    detail: constr(max_length=2000) | None = None
    """
    失败时的详情，必须带上足以定位问题的上下文：哪一列、命中多少行、期望范围是什么。失败信息要能指导下一步，而不是只报一个 false。
    """
    level: Level | None = 'block'
    """
    失败时的处置级别。block 级断言失败则整个 run 停在数据层，不进制作。
    """
    passed: bool
    """
    是否通过。
    """


class Baseline(BaseModel):
    """
    一个对比基准。注意 ref 与 offset 都是引用或时间偏移，不是数值——目标值本身也要走 FactSet，不能在计划里写死。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    kind: Kind
    """
    基准类型。target 对目标，period_over_period 环比，year_over_year 同比，peer 同类对比，benchmark 行业基准。
    """
    offset: constr(pattern=r'^-\d+(hour|day|week|month|quarter|year)$', max_length=32) | None = None
    """
    时间偏移，例如 -1week、-1year。只用于 period_over_period 与 year_over_year。
    """
    ref: Slug | None = None
    """
    基准指标名，例如 oee_target。它同样要在 metrics.yml 里定义，数值由 runner 查出来。
    """


class X(BaseModel):
    """
    x 轴映射。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    field: FieldModel
    """
    取序列的哪个字段作 x。period 对应 temporal 的 x 轴，category 对应 nominal/ordinal 的 x 轴。gate 2 会核对它与序列 x.semantic 是否相容。
    """
    series: FactId
    """
    引用的序列 id，必须存在于数据岛的 series 中，否则 E_BAD_CHART_SPEC。
    """


class Y(BaseModel):
    """
    y 轴映射。这是几何反算的核心：gate 2 把像素坐标按 domain 线性还原成数值，与序列 y.values 逐点比对，相对容差 2%。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    domain: list[float] | None = Field(None, max_length=2, min_length=2)
    """
    y 轴的数值域 [下界, 上界]，即绘图区上下边界分别代表的数值。zeroBased 为 false 时必填——没有它就无法把像素还原成数值，几何检查会整体失效。下界必须小于上界（由 gate 2 校验，JSON Schema 无法表达跨元素比较）。
    """
    field: Field1
    """
    取序列的哪个字段作 y。当前只允许 value，即 series.y.values。
    """
    series: FactId
    """
    引用的序列 id，必须存在于数据岛的 series 中。
    """
    zeroBased: bool
    """
    y 轴是否从 0 起。false 表示截断。gate 5 判定：bar 与 area 截断即阻断；line 允许截断，但会核对 domain 跨度与数据实际波动幅度的比值，超过 4 倍记轴放大警告。
    """


class ChartSpec(BaseModel):
    """
    图表的数据映射契约，由模型在制作节点写进元素的 data-bf-chart-spec 属性，不进 FactSet。FactSet 回答「数值是多少」，ChartSpec 回答「这些数值被怎样映射到像素」。缺了后者，gate 只能数点数，拦不住「数据在涨、线画成跌」——点数一个不差就能蒙混过关。有了它，gate 才能把 SVG 坐标按 domain 反算回数值域做逐点比对。同一份声明服务 gate 2 的几何检查与 gate 5 的截断判定，模型只写一次。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    dual_axis_justification: constr(min_length=8, max_length=500) | None = None
    """
    双轴图的正当性理由。gate 5 默认阻断同一图上量纲不同的两个 y 轴，除非这里给出理由。写「为了好看」不算理由，评审会驳回。
    """
    kind: Kind1
    """
    图表类型。
    """
    marks: Marks
    """
    承载数据的 SVG 元素类型，必须与 kind 匹配：line→path、area→path、bar→rect、scatter→circle。gate 2 按这个值去 DOM 里找要检查几何的元素。
    """
    order: Order
    """
    x 轴排序方向，必须与序列的实际顺序一致。gate 2 会核对：声明 asc 但序列 x 实际递减即为不一致。none 表示不保证顺序，只对 category 轴合法。
    """
    orientation: Orientation | None = 'vertical'
    """
    bar 专用的方向。vertical 时数值映射到 y 轴，horizontal 时映射到 x 轴——几何反算的轴向据此选择。默认 vertical。
    """
    plot_rect: PlotRect | None = None
    """
    绘图区在 SVG 用户坐标系中的矩形，即 domain 两端所对应的像素边界。内联 SVG 的几何反算需要它：value = domain[0] + (y_bottom - py) / height * (domain[1] - domain[0])。开发文档只写了「按 domain 反算」而没定义绘图区边界，若缺省则 gate 只能假定路径自身的坐标极值对应 domain 两端——那样「整条线整体平移或缩放」这类错误就查不出来。因此内联 SVG 强烈建议声明本字段；缺省时 gate 2 退化为极值归一化比对并记一条警告。ECharts 路径不需要它（DOM 由库生成，不走几何检查）。
    """
    series: list[FactId] | None = Field(None, min_length=1)
    """
    同一图表绑定的 FactSet 序列 id。所有序列必须共享 x 轴取值和 y.unit；省略时使用 x/y.series 的单序列兼容模式。
    """
    x: X
    """
    x 轴映射。
    """
    y: Y
    """
    y 轴映射。这是几何反算的核心：gate 2 把像素坐标按 domain 线性还原成数值，与序列 y.values 逐点比对，相对容差 2%。
    """


class ColumnProfile(BaseModel):
    """
    单列画像。只报告源文件中可计算的统计，不得填补未知值——未知就省略该键，不要写 0 或空串冒充。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    distinct_count: conint(ge=0)
    """
    去重后的取值个数。
    """
    dtype: constr(min_length=1, max_length=64)
    """
    物理类型，取 DuckDB 推断结果，例如 float64 / int64 / varchar / timestamp / boolean / date。
    """
    max: float | str | None = None
    """
    最大值。约定同 min。
    """
    min: float | str | None = None
    """
    最小值。数值列为 number，时间列为 ISO 字符串。无法计算时省略本键，不要填 null。
    """
    name: constr(min_length=1, max_length=256)
    """
    列名，保持源文件原样。
    """
    null_rate: Ratio01
    """
    空值占比。
    """
    p50: float | None = None
    """
    中位数，仅数值列有。
    """
    quality_flags: list[QualityFlag] | None = None
    """
    该列的质量标记，形如 out_of_domain:3，冒号后为命中行数。
    """
    sample_values: list[SampleValue] | None = Field(None, max_length=20)
    """
    样例值，统一转成字符串，供模型理解列内容。已按脱敏规则处理。
    """
    semantic: Semantic


class DatasetSource(BaseModel):
    """
    数据集来源。红线：契约中不得出现任何承载连接串、主机名、用户名或密码的字段。文件类来源只给项目内相对 uri；数据库与飞书类来源只给一个 connection_ref 别名，真实凭据由 runner 进程从环境变量解析，daemon 与任何 agent 运行时都接触不到。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    connection_ref: Slug | None = None
    """
    数据库或飞书来源的连接别名。它是一个 slug，不是连接串——runner 用它去环境变量里查真实凭据。别名的字符集不允许出现 :、/、@ 或点，结构上就装不下一个 DSN。
    """
    kind: Kind2
    """
    来源类型。Task 3 Step 2: 仅支持 csv/xlsx/parquet 文件格式，不支持 json/jsonl。
    """
    sheet: constr(max_length=128) | None = None
    """
    xlsx 的工作表名。
    """
    table: constr(pattern=r'^[A-Za-z0-9_.]+$', max_length=128) | None = None
    """
    数据库来源的表名或飞书多维表格的 table id。
    """
    uri: constr(pattern=r'^[A-Za-z0-9_-]+(/[A-Za-z0-9_-]+)*\.(xlsx|xlsm|csv|tsv|parquet)$', max_length=512) | None = None
    """
    文件类来源的项目内相对路径。路径段的字符集不含点，所以结构上装不下 .. 回溯段，也装不下 scheme://user:pass@host 形式的连接串；唯一允许的点是扩展名前的那个。模式刻意不使用正则先行断言，因为 pydantic 2 默认的 Rust 正则引擎不支持。
    """


class Defect(BaseModel):
    """
    数据缺陷。evidence 必须指向源数据中可复核的位置，不接受泛泛而谈的描述。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    column: constr(max_length=256) | None = None
    """
    涉及的列名。跨列缺陷（如 referential_broken）可省略并在 evidence.note 说明。
    """
    evidence: Evidence
    """
    可复核的证据。
    """
    fix_cost: FixCost
    """
    修复成本估计。
    """
    impact: constr(min_length=1, max_length=500)
    """
    该缺陷会污染哪些结论。写给洞察节点看，让它知道哪些方向不能碰。
    """
    severity: Severity
    type: DefectType


class Dimension(BaseModel):
    """
    维度。它把物理列名映射为业务语义名——模型只见语义名，物理列名由 loader 翻译。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    column: constr(min_length=1, max_length=256)
    """
    物理列名。
    """
    grain: TimeGrain | None = None
    """
    time 维度的颗粒度。
    """
    label: constr(max_length=128) | None = None
    """
    中文标签。gate 3 的越权字段检查要同时匹配 name 与 label，否则模型写中文标签就绕过了对英文字段名的检查。
    """
    name: Slug
    """
    维度的业务语义名，AnalysisPlan 与 QuerySet 引用这个名字。
    """
    sensitivity: Sensitivity | None = None
    """
    维度敏感级别，省略时视为 internal。与岗位画像的 max_sensitivity 联合决定可见性。
    """
    type: Type
    """
    维度类型。categorical 用于分类，time 用于时间轴，geo 用于地理。
    """
    values: list[Value] | None = None
    """
    categorical 维度的允许取值枚举。声明了就意味着出现其它取值是数据缺陷。
    """


class Fact(BaseModel):
    """
    一条标量事实。它同时携带原始数值、显示值、口径版本、查询指纹、样本量、标记——溯源面板要展示的全部信息都在这一条里，不需要回查别处。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    confidence: Ratio01 | None = None
    """
    可信度，由 runner 根据样本量与数据质量确定性地计算，不是模型的主观打分。
    """
    definition_ref: DefinitionRef
    """
    口径引用。两个 definition_ref 不同的数被并列时，事实评审的 definition_consistency 维度会扣分。
    """
    dims: dict[constr(pattern=r'^[a-z][a-z0-9_]*$', min_length=1, max_length=64), constr(max_length=128)]
    """
    维度取值。键是 metrics.yml 里的维度名，值是该维度的具体取值。
    """
    display: constr(min_length=1, max_length=64)
    """
    显示值，由 runner 按 metrics.yml 的 display 段生成，不由模型格式化。注入器把它填进 data-fact 元素的文本，gate 2 核对元素文本必须等于它或落在格式化差异白名单内。
    """
    flags: list[FactFlag] | None = None
    """
    事实标记，评审的输入。空数组表示无异常。
    """
    id: FactId
    """
    事实 id，写进 HTML 的 data-fact 属性。
    """
    metric: Slug
    """
    指标名。
    """
    row_count: conint(ge=0)
    """
    参与计算的样本量。低于指标的 low_sample_threshold 时 runner 打 low_sample 标记。
    """
    sql_hash: SqlHash
    """
    查询指纹。
    """
    unit: constr(min_length=1, max_length=32)
    """
    单位，取自指标定义。
    """
    value: float
    """
    原始数值，未经格式化。gate 2 重算 delta/ratio 等派生值时用它，不用 display。
    """


class FactEmission(BaseModel):
    """
    一条事实产出声明。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    id_template: constr(pattern=r'^[a-z0-9{}][a-z0-9_{}-]*(\.[a-z0-9{}][a-z0-9_{}-]*)+$', max_length=200)
    """
    事实 id 模板，例如 oee.{line}.{week}。模板变量必须来自 SELECT 的输出列，runner 会校验；变量替换后的结果必须满足 FactId 的字符规范。
    """
    metric: Slug
    """
    该事实对应的指标名，决定 unit、display 与 domain 从哪条指标定义取。
    """
    series: bool | None = False
    """
    true 表示这条产出的是序列（进 FactSet.series）而非标量事实（进 FactSet.facts）。默认 false。
    """
    value_column: constr(min_length=1, max_length=128)
    """
    取哪一个输出列作为事实的数值。
    """
    x_column: constr(max_length=128) | None = None
    """
    序列产出时的 x 轴列名。series 为 true 时必填。
    """


class FeishuDelivery(BaseModel):
    """
    飞书交付事件记录。orchestrator 完成后根据 role_profile 推送消息卡片，本契约记录推送目标、状态与关联资源。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    card_message_id: constr(pattern=r'^om_[a-zA-Z0-9_-]+$', max_length=128) | None = None
    """
    飞书消息 id。由飞书 API 返回，用于后续更新卡片或追踪交互。status 为 sent 时必填。
    """
    dashboard_url: AnyUrl | None = None
    """
    看板 URL。卡片中的「查看详情」按钮跳转目标。status 为 sent 时建议填写。
    """
    delivered_at: Timestamp | None = None
    """
    交付时间戳。status 为 sent 时必填。
    """
    error_message: constr(min_length=1, max_length=1000) | None = None
    """
    错误消息。status 为 failed 时必填，记录失败原因供排查。
    """
    role_id: Slug
    """
    岗位 id。与 role-profile.schema.json 的 role_id 对应。
    """
    run_id: RunId
    """
    本次运行的 id。一次运行可产生多条交付记录（推送给不同岗位）。
    """
    status: Status
    """
    交付状态。sent 表示已成功推送，failed 表示推送失败（网络错误、API 限流等），disabled 表示该岗位的推送配置已关闭。
    """


class Finding(BaseModel):
    """
    一条具体意见。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    code: constr(pattern=r'^[EW]_[A-Z][A-Z0-9_]*$', max_length=64)
    """
    问题码，大写下划线形式，例如 E_OVERFLOW、E_UNBOUND_NUMBER。它让同类问题可聚合统计。
    """
    evidence_ref: constr(max_length=500) | None = None
    """
    证据引用，通常是截图路径加区域坐标，格式 <路径>#x=<n>,y=<n>,w=<n>,h=<n>。视觉类 must_fix 应当带上它。
    """
    finding_id: constr(pattern=r'^f[0-9]+$', max_length=16)
    """
    意见在本次评审内的局部 id。
    """
    fix: constr(min_length=1, max_length=1000)
    """
    修复建议。要给出可执行的下一步，并说明不该怎么做——例如「缩短标签或改为两行布局，不要缩小字号」。一条能指导下一步的意见把一次驳回变成一次有效输入。
    """
    problem: constr(min_length=1, max_length=1000)
    """
    问题描述，要具体到可复核的程度，例如「数值文本溢出卡片右边界约 12px」而不是「排版有问题」。
    """
    severity: Severity1
    """
    严重度。must_fix 只能用于四类可客观判定的问题：口径违规、事实绑定失败、误导性编码、岗位越权。审美与措辞一律 should_fix——把主观偏好升格为阻断项会让评审失去公信力。
    """
    target: constr(pattern=r'^(data-bf-card:[a-z0-9][a-z0-9-]*|data-fact:[a-z0-9][a-z0-9_-]*(\.[a-z0-9][a-z0-9_-]*)+)$', max_length=200)
    """
    路由目标，必须指向 data-bf-card 锚点或 data-fact id，格式 data-bf-card:<锚点> 或 data-fact:<事实id>。没有 target 的意见无法路由到具体卡片做局部重写，视为无效并计入评审质量指标。
    """
    viewport: Viewport | None = None
    """
    该问题出现在哪个视口。视觉类问题必须带，否则制作节点不知道该在什么尺寸下验证修复。
    """


class GovernanceReport(BaseModel):
    """
    治理节点输出：质量评分 + 治理提议列表
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    profiled_at: Timestamp
    """
    输入 Profile 的时间戳（直接透传 Profile.profiled_at）
    """
    proposals: list[Defect]
    """
    治理提议列表，每条复用 Defect 结构（type/severity/evidence/impact/fix_cost）
    """
    quality_score: confloat(ge=0.0, le=1.0)
    """
    整体质量分（0.0-1.0），基于 Profile.defects 和新发现的治理问题计算
    """


class Scope(BaseModel):
    """
    适用范围。dims 限定这条记忆只在特定维度取值下成立。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    dims: dict[constr(pattern=r'^[a-z][a-z0-9_]*$', min_length=1, max_length=64), constr(max_length=128)] | None = None
    """
    维度限定，例如 { line: A02 } 表示这条记忆只适用于 A02 线。
    """
    metrics: list[Slug] | None = None
    """
    相关指标名，让洞察节点能按指标检索记忆。
    """
    project_id: constr(pattern=r'^[a-zA-Z0-9_-]+$', max_length=32)
    """
    所属项目。org 层记忆也要记录它最初来自哪个项目。
    """


class MemoryEntry(BaseModel):
    """
    一条记忆条目。红线的实现方式：记忆条目不允许含 value 字段，schema 层面就没有这个键，且 additionalProperties 为 false——需要数字就重新查。这条不靠纪律，靠契约。text 里也不该写具体数值，因为记忆会过期而数字不会自己更新，一个陈旧的数字比没有数字更危险。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    confirmed_by: constr(pattern=r'^user:[a-z0-9_-]+$', max_length=128) | None = None
    """
    确认人，格式 user:<用户名>。org 层记忆必须非空——跨项目生效的知识必须有人背书，不能由模型自行晋升。
    """
    created_at: Timestamp
    created_by: constr(pattern=r'^(agent:[a-z_]+|user:[a-z0-9_-]+)$', max_length=128)
    """
    创建者，格式 agent:<节点名> 或 user:<用户名>。
    """
    evidence_run: RunId | None = None
    """
    产生这条记忆的运行 id，供回溯当时的事实。要看当时的数字就去那次运行的 FactSet 里查，记忆本身不存数。
    """
    expires_at: Timestamp | None = None
    """
    过期时间。null 表示长期有效。业务例外类记忆建议设过期时间，因为产线情况会变。
    """
    kind: Kind3
    """
    记忆类型。conclusion 结论，business_exception 业务例外，definition_dispute 口径争议，rejected_proposal 被否决的提案，preference 偏好。
    """
    layer: Layer
    """
    记忆层级。task 只在本次运行内有效，project 跨运行但限本项目，org 跨项目。
    """
    mem_id: MemId
    scope: Scope
    """
    适用范围。dims 限定这条记忆只在特定维度取值下成立。
    """
    text: constr(min_length=1, max_length=2000)
    """
    记忆内容，写业务规律与判断，不写具体数值。例如「A02 每月首个周一低 OEE 是计划换型，非异常」——它描述的是一条规则，任何时候重新查数都能验证；如果写成「A02 上周 OEE 是 68.1%」，下周它就成了错误信息。
    """


class MetricTypeParams(BaseModel):
    """
    指标计算参数。ratio 需要 numerator 与 denominator；simple 与 cumulative 用 measure；derived 用 expr 引用其它指标。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    denominator: MetricExpr | None = None
    expr: constr(min_length=1, max_length=1000) | None = None
    """
    derived 指标的推导表达式，只能引用其它已定义指标名。
    """
    measure: MetricExpr | None = None
    numerator: MetricExpr | None = None
    window: TimeGrain | None = None
    """
    cumulative 指标的累计窗口。
    """


class Quality(BaseModel):
    """
    数据质量评估。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    defects: list[Defect]
    """
    数据缺陷列表。
    """
    score: Ratio01
    """
    质量综合评分，0 到 1 之间。
    """


class Profile(BaseModel):
    """
    单个数据集的 profiling 结果。HTTP /internal/profile 路由直接返回此契约，不再维护临时返回结构。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    columns: list[ColumnProfile] = Field(..., min_length=1)
    """
    列画像数组。
    """
    dataset_id: DatasetId
    generated_at: Timestamp
    """
    Profile 生成时间。
    """
    profile_id: constr(pattern=r'^pf_[a-z0-9_]+$', max_length=96)
    """
    Profile 标识，格式 pf_<slug>。
    """
    quality: Quality
    """
    数据质量评估。
    """
    row_count: conint(ge=0)
    """
    数据集行数。
    """


class Dataset1(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    dataset_id: DatasetId
    profiled_at: Timestamp | None = None
    """
    画像时间。与 computed_at 差距过大时该打 stale 标记。
    """
    quality_score: Ratio01 | None = None
    """
    该数据集的质量评分，来自 Profile。
    """
    row_count: conint(ge=0)
    """
    该数据集的行数。
    """


class Provenance(BaseModel):
    """
    血缘。溯源面板要展示的数据集来源信息。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    datasets: list[Dataset1] = Field(..., min_length=1)
    """
    参与计算的数据集及其质量信息。
    """
    run_id: RunId | None = None
    """
    产生本事实集的运行 id。
    """


class References(BaseModel):
    """
    声明引用。gate 3 会解析 SQL 并与这里逐项比对，声明与实际不一致即硬阻断——这防止模型偷偷查了没声明的字段。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    dimensions: list[Slug]
    """
    引用的维度名。
    """
    metrics: list[Slug] = Field(..., min_length=1)
    """
    引用的指标名。
    """


class Query(BaseModel):
    """
    一条查询。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    assertions: list[AssertionSpec] | None = None
    """
    要执行的数据断言。in_domain 的上下界取自 metrics.yml 的 domain，不在这里硬编码。任一 block 级断言失败则整个 run 停在数据层，不进制作——用错的数画图是纯浪费。
    """
    datasets: list[DatasetId] = Field(..., min_length=1)
    """
    本查询用到的数据集 id，必须与 SQL 里出现的 {{...}} 占位符集合一致。
    """
    emits_facts: list[FactEmission] = Field(..., min_length=1)
    """
    本查询会产出哪些事实。它让事实 id 可预测，制作节点才能在拿到 FactSet 索引前就知道该引用什么。
    """
    purpose: constr(min_length=1, max_length=500)
    """
    这条查询要得到什么，用业务语言写。
    """
    qid: constr(pattern=r'^q[0-9]+$', max_length=16)
    """
    回指 AnalysisPlan 里的问题 id。每条查询必须服务于一个已声明的问题，不允许无来由的查询。
    """
    query_id: constr(pattern=r'^qy[0-9]+$', max_length=16)
    """
    查询在本集内的局部 id。
    """
    references: References
    """
    声明引用。gate 3 会解析 SQL 并与这里逐项比对，声明与实际不一致即硬阻断——这防止模型偷偷查了没声明的字段。
    """
    sql: constr(min_length=1, max_length=20000)
    """
    SQL 语句。表引用必须用 {{dataset_id}} 占位符，由 runner 替换为实际表引用——模型不接触真实连接串、库名、文件路径。loader 白名单会拒绝 DDL/DML、read_csv/read_parquet 等文件函数与 system() 类函数。
    """


class QuerySet(BaseModel):
    """
    查询节点的输出。每条查询必须声明它引用了哪些指标与维度，声明与 SQL 实际内容不一致时 gate 3 硬阻断。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    metrics_version: MetricsVersion
    """
    生成本查询集时的口径版本。runner 执行前会核对当前 metrics.yml 版本，不一致则拒绝执行。
    """
    plan_id: constr(pattern=r'^pl_[0-9A-HJKMNP-TV-Z]{26}$')
    """
    来源计划 id。
    """
    queries: list[Query] = Field(..., min_length=1)
    """
    查询数组。
    """
    queryset_id: constr(pattern=r'^qs_[0-9A-HJKMNP-TV-Z]{26}$')
    """
    查询集 id。
    """


class DrilldownHint(BaseModel):
    """
    下钻方法提示，指向一个具体的分析方法与 skill。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    method: Slug
    """
    分析方法名，例如 loss_tree、pareto。
    """
    skill: SkillSlug
    """
    承载该方法的 skill slug。
    """


class Question(BaseModel):
    """
    一个业务问题。metrics 与 dims 必须来自 metrics.yml；expected_shape 是 B 类图表选型 skill 的输入键。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    baselines: list[Baseline] | None = None
    """
    对比基准。没有基准的数值无法判断好坏。
    """
    depth: Depth
    """
    分析深度。
    """
    dims: list[Slug]
    """
    涉及的维度名，必须在 metrics.yml 中已定义。
    """
    drilldown_hint: DrilldownHint | None = None
    """
    下钻方法提示，指向一个具体的分析方法与 skill。
    """
    expected_shape: ExpectedShape
    """
    预期的表达形态。它是 B 类图表选型 skill 的输入键，也是呈现评审 chart_fitness 维度的判定基准。
    """
    metrics: list[Slug] = Field(..., min_length=1)
    """
    涉及的指标名，必须在 metrics.yml 中已定义。
    """
    qid: constr(pattern=r'^q[0-9]+$', max_length=16)
    """
    问题在本计划内的局部 id，QuerySet 用它回指。
    """
    text: constr(min_length=1, max_length=500)
    """
    问题本身，用业务语言写。
    """
    why_it_matters: constr(min_length=1, max_length=500)
    """
    这个问题为什么值得问——它对应哪个决策。没有决策价值的问题不该进计划。
    """


class Review(BaseModel):
    """
    评审意见。两个评审节点共用结构，kind 区分。评审节点不产出 HTML——它没有写产物的能力，只有阻断发布的权力。评分维度与权重写在本 schema 的 rubric 段里，不写在提示词里。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    composite: confloat(ge=0.0, le=10.0)
    """
    综合分。由 daemon 按 rubric 权重重算，模型自报只作参考，偏差超过 0.01 记 composite_mismatch 警告。
    """
    findings: list[Finding]
    """
    具体意见。可以为空数组（verdict 为 pass 且无改进建议时）。
    """
    kind: Kind4
    """
    评审类型。fact 是事实评审（看数值与口径），presentation 是呈现评审（看表达与视觉）。
    """
    review_id: constr(pattern=r'^rv_[0-9A-HJKMNP-TV-Z]{26}$')
    """
    评审 id。
    """
    round: conint(ge=1, le=10)
    """
    评审轮次，从 1 起。超过 rubric 的 max_rounds 仍有 must_fix 未清零时按 fallback_policy 处置。
    """
    run_id: RunId
    scores: list[Score] = Field(..., min_length=1)
    """
    各维度评分。维度集合必须与 kind 对应的 rubric 权重键完全一致，不多不少。
    """
    verdict: Verdict
    """
    结论。存在任一 must_fix 时必须为 reject——这条由 daemon 强制校验，模型自报 pass 不算数。
    """


class LayoutHint(BaseModel):
    """
    布局提示。primary_viewport 是主视口，also_check 里的视口也要过呈现评审。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    also_check: list[Viewport] | None = Field(None, max_length=4)
    """
    附加视口。手机端也要过呈现评审时把 [390, 844] 放进来。
    """
    density: Density
    """
    信息密度偏好。
    """
    primary_viewport: Viewport
    """
    主视口，截图与呈现评审的基准。
    """


class RoleProfile(BaseModel):
    """
    岗位画像。它决定这个岗位该看什么、不该看什么、结论怎么写。forbidden_fields 与 max_sensitivity 是 gate 3 的硬约束，runner 在生成 FactSet 阶段就按它剔除越权字段——gate 3 是第二道防线，不是唯一防线。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    decision_horizon: DecisionHorizon
    """
    决策周期。它决定默认时间颗粒度与趋势窗口长度。
    """
    forbidden_fields: list[Slug] | None = None
    """
    禁止字段，gate 3 硬约束。检查时要同时匹配这里的字段名与 metrics.yml 里对应的 label。
    """
    label: constr(min_length=1, max_length=64)
    """
    岗位中文名。
    """
    layout_hint: LayoutHint | None = None
    """
    布局提示。primary_viewport 是主视口，also_check 里的视口也要过呈现评审。
    """
    max_sensitivity: Sensitivity
    """
    该岗位可见的最高敏感级别。高于此级别的指标与维度不进入 FactSet。
    """
    metrics_focus: list[Slug] = Field(..., min_length=1)
    """
    关注指标。必须都是 metrics.yml 里已定义的指标名。
    """
    narrative: Narrative
    """
    叙述约束。
    """
    questions_priority: list[constr(min_length=1, max_length=500)] | None = None
    """
    这个岗位最关心的问题，按优先级排列。洞察节点用它对齐 AnalysisPlan 的问题选取。
    """
    role_id: Slug
    """
    岗位标识。三个默认岗位：executive / plant_manager / supply_chain_lead。
    """


class X1(BaseModel):
    """
    x 轴。ChartSpec 的 x.field 为 period 时对应 semantic 为 temporal 的轴，为 category 时对应 nominal/ordinal 轴。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    name: Slug
    """
    x 轴对应的维度名。
    """
    semantic: Semantic
    """
    x 轴语义。gate 5 检查「时间间隔不等」时要先确认这是 temporal 轴。
    """
    values: list[Value] = Field(..., min_length=1)
    """
    x 轴取值，与 y.values 等长。
    """


class Series(BaseModel):
    """
    一条序列，供图表使用。x 与 y 等长是硬约束，由 runner 保证；gate 2 的几何检查会用 y.values 的长度与 SVG 点数比对。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    definition_ref: DefinitionRef
    dims: dict[constr(pattern=r'^[a-z][a-z0-9_]*$', min_length=1, max_length=64), constr(max_length=128)] | None = None
    """
    该序列固定的维度取值，例如 { line: A01 } 表示这是 A01 线的序列。
    """
    flags: list[FactFlag] | None = None
    """
    序列标记。
    """
    id: FactId
    """
    序列 id，命名加 .trend.<窗口> 后缀，写进 HTML 的 data-fact-series 属性。
    """
    metric: Slug
    row_count: conint(ge=0) | None = None
    """
    参与计算的样本量。
    """
    sql_hash: SqlHash
    x: X1
    """
    x 轴。ChartSpec 的 x.field 为 period 时对应 semantic 为 temporal 的轴，为 category 时对应 nominal/ordinal 轴。
    """
    y: Y1
    """
    y 轴数值。gate 2 把 SVG 坐标按 ChartSpec 的 y.domain 反算回数值域后，与这里的 values 逐点比对，相对容差 2%。
    """


class AnalysisPlan(BaseModel):
    """
    洞察节点的输出。只描述「该看什么」，不含任何 SQL、不含任何数值。红线：这个契约里没有任何可以承载业务数值的字段——想让模型在计划阶段就写数字，schema 层面就不成立。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    memory_refs: list[MemId] | None = None
    """
    引用的记忆条目 id。让「A02 每月首个周一低 OEE 是计划换型」这类知识可追溯到具体条目。
    """
    open_risks: list[constr(min_length=1, max_length=1000)] | None = None
    """
    已知风险，例如「A02 上周有 3 天数据缺失，结论需标注样本不足」。这是纯文字判断，不是数值。
    """
    plan_id: constr(pattern=r'^pl_[0-9A-HJKMNP-TV-Z]{26}$')
    """
    计划 id。
    """
    questions: list[Question] = Field(..., min_length=1)
    """
    要回答的业务问题。
    """
    role_id: Slug
    """
    本次分析服务的岗位。
    """
    run_id: RunId
    skills_used: list[SkillSlug] | None = None
    """
    本次调用的 skill slug 列表，供溯源与评测归因。
    """


class Dataset(BaseModel):
    """
    数据集的基本信息。由 runner 的 connector 层产出，不包含实际行数据，只有 schema 与元信息。red line: 不得出现任何连接串、主机名、用户名或密码。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    columns: list[ColumnProfile] = Field(..., min_length=1)
    """
    列画像数组。至少要有一列才算合法数据集，完全没列的表是错误状态。
    """
    dataset_id: DatasetId
    defects: list[Defect] | None = None
    """
    数据缺陷列表。
    """
    name: constr(min_length=1, max_length=256)
    """
    数据集名称，给人看的。
    """
    profiled_at: Timestamp | None = None
    """
    画像生成时间。
    """
    quality_score: Ratio01 | None = None
    """
    数据质量综合评分。由 profiling 层根据缺陷计算，可选字段——如果连接器只做了结构探测还没做质量分析，就省略本字段。
    """
    row_count: conint(ge=0)
    """
    行数。空表为 0，不要在无法获取行数时填 -1 或 null——无法获取说明连接器实现有问题，应该报错而不是返回半成品数据集。
    """
    source: DatasetSource


class FactSet(BaseModel):
    """
    runner 输出，纯确定性，无模型参与。这是产物层全部环节的唯一数值来源。红线：模型只写带 data-fact 绑定标记的结构，永远不写真实业务数字；数字由注入器从这里填入。facts 与 series 分开——标量事实用于 KPI 卡与文案，序列用于图表，两者共用 definition_ref 与 sql_hash，所以图表和文案的口径天然一致。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    assertion_results: list[AssertionResult] | None = None
    """
    断言执行结果，随 FactSet 返回，daemon 侧只做判定不重跑。
    """
    computed_at: Timestamp
    """
    计算时间。溯源面板展示它，也用于判定 stale。
    """
    facts: list[Fact]
    """
    标量事实数组。可以为空数组（某些运行只产序列），但键必须存在。
    """
    factset_id: constr(pattern=r'^fs_[0-9A-HJKMNP-TV-Z]{26}$')
    """
    事实集 id。注入器会把它写进 <html data-bf-factset-id>，产物与事实集从此绑定。
    """
    metrics_version: MetricsVersion
    """
    计算时的口径版本。
    """
    provenance: Provenance
    queryset_id: constr(pattern=r'^qs_[0-9A-HJKMNP-TV-Z]{26}$')
    """
    产生本事实集的查询集 id。
    """
    role_id: Slug
    """
    role_id 落在 FactSet 上：runner 在生成阶段就按岗位画像剔除了越权字段，产物层拿不到不该有的数。权限的第一道防线在这里，gate 3 是第二道。
    """
    series: list[Series] | None = None
    """
    序列数组，供图表使用。
    """


class Metric(BaseModel):
    """
    指标。这是口径的落点：一个数值意味着什么，完全由这里的定义决定。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    definition_note: constr(max_length=2000) | None = None
    """
    口径说明，写给人和模型共同读。
    """
    display: DisplayFormat
    """
    显示格式。runner 按它生成 display，模型不参与格式化。
    """
    disputes: list[Dispute] | None = None
    """
    口径争议的结构化落点。事实评审节点会读它，判定产物是否把口径冲突的两个数并列。这解决了「记得财务口径和生产口径一直有争议」这类只存在于人脑里的知识。
    """
    domain: Domain | None = None
    """
    值域。in_domain 断言的 lo/hi 取自这里，不在断言里硬编码；gate 也用它判断 out_of_domain 缺陷。
    """
    filter: constr(max_length=1000) | None = None
    """
    该指标固有的过滤条件，例如 status != 'test'。它是口径的一部分，查询节点不能省略。
    """
    label: constr(min_length=1, max_length=128)
    """
    中文标签。gate 3 的 E_FORBIDDEN_FIELD 要同时匹配 name 与 label，否则模型写「毛利率」就绕过了对 gross_margin 的检查。
    """
    low_sample_threshold: conint(ge=1) | None = None
    """
    样本量阈值。FactSet 的 row_count 低于它就打 low_sample 标记。省略时由 runner 用全局默认值，但对关键指标应显式声明——阈值是业务判断，不该由代码猜。
    """
    name: Slug
    """
    指标名。它同时是事实 id 的第一段，所以必须满足 slug 规范。
    """
    owner: constr(max_length=128) | None = None
    """
    口径归属部门。争议仲裁时要知道该找谁。
    """
    sensitivity: Sensitivity
    type: Type1
    """
    指标类型。simple 单一聚合，ratio 分子分母，cumulative 累计，derived 由其它指标推导。
    """
    type_params: MetricTypeParams | None = None
    unit: constr(min_length=1, max_length=32)
    """
    单位。gate 2 的单位换算白名单（%↔pp、元↔万元、件↔万件）以它为基准。
    """


class Metrics(BaseModel):
    """
    metrics.yml 的 schema。这是口径唯一事实源，查询节点只能引用这里定义的指标与维度。schema 约定抄 dbt MetricFlow，loader 自写，不引 dbt 依赖。
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    dimensions: list[Dimension] = Field(..., min_length=1)
    """
    维度定义。查询里的 GROUP BY 只能用这里声明的维度。
    """
    metrics: list[Metric] = Field(..., min_length=1)
    """
    指标定义。
    """
    version: MetricsVersion
    """
    每次修改递增。被 FactSet 的 definition_ref 引用，也让旧产物可被识别为 stale。
    """


class BifrostContracts(BaseModel):
    """
    Generated bundle of every Bifrost contract. Do not edit or commit; it exists only as codegen input so cross-file $refs resolve to one shared named type.
    """
    model_config = ConfigDict(
        extra='forbid',
    )
    AnalysisPlan_1: AnalysisPlan | None = Field(None, alias='AnalysisPlan')
    AssertionResult_1: AssertionResult | None = Field(None, alias='AssertionResult')
    AssertionSpec_1: AssertionSpec | None = Field(None, alias='AssertionSpec')
    Baseline_1: Baseline | None = Field(None, alias='Baseline')
    ChartSpec_1: ChartSpec | None = Field(None, alias='ChartSpec')
    ColumnProfile_1: ColumnProfile | None = Field(None, alias='ColumnProfile')
    Dataset_1: Dataset | None = Field(None, alias='Dataset')
    DatasetId_1: DatasetId | None = Field(None, alias='DatasetId')
    DatasetSource_1: DatasetSource | None = Field(None, alias='DatasetSource')
    Defect_1: Defect | None = Field(None, alias='Defect')
    DefectType_1: DefectType | None = Field(None, alias='DefectType')
    DefinitionRef_1: DefinitionRef | None = Field(None, alias='DefinitionRef')
    Dimension_1: Dimension | None = Field(None, alias='Dimension')
    DisplayFormat_1: DisplayFormat | None = Field(None, alias='DisplayFormat')
    Dispute_1: Dispute | None = Field(None, alias='Dispute')
    Fact_1: Fact | None = Field(None, alias='Fact')
    FactEmission_1: FactEmission | None = Field(None, alias='FactEmission')
    FactFlag_1: FactFlag | None = Field(None, alias='FactFlag')
    FactId_1: FactId | None = Field(None, alias='FactId')
    FactSet_1: FactSet | None = Field(None, alias='FactSet')
    FeishuBitableWrite_1: FeishuBitableWrite | None = Field(None, alias='FeishuBitableWrite')
    FeishuCard_1: FeishuCard | None = Field(None, alias='FeishuCard')
    FeishuDelivery_1: FeishuDelivery | None = Field(None, alias='FeishuDelivery')
    Finding_1: Finding | None = Field(None, alias='Finding')
    GovernanceReport_1: GovernanceReport | None = Field(None, alias='GovernanceReport')
    MemId_1: MemId | None = Field(None, alias='MemId')
    MemoryEntry_1: MemoryEntry | None = Field(None, alias='MemoryEntry')
    Metric_1: Metric | None = Field(None, alias='Metric')
    MetricExpr_1: MetricExpr | None = Field(None, alias='MetricExpr')
    MetricTypeParams_1: MetricTypeParams | None = Field(None, alias='MetricTypeParams')
    Metrics_1: Metrics | None = Field(None, alias='Metrics')
    MetricsVersion_1: MetricsVersion | None = Field(None, alias='MetricsVersion')
    Profile_1: Profile | None = Field(None, alias='Profile')
    Provenance_1: Provenance | None = Field(None, alias='Provenance')
    Query_1: Query | None = Field(None, alias='Query')
    QuerySet_1: QuerySet | None = Field(None, alias='QuerySet')
    Question_1: Question | None = Field(None, alias='Question')
    Ratio01_1: Ratio01 | None = Field(None, alias='Ratio01')
    Review_1: Review | None = Field(None, alias='Review')
    RoleProfile_1: RoleProfile | None = Field(None, alias='RoleProfile')
    Rubric_1: Rubric | None = Field(None, alias='Rubric')
    RubricSet_1: RubricSet | None = Field(None, alias='RubricSet')
    RunCreateRequest_1: RunCreateRequest | None = Field(None, alias='RunCreateRequest')
    RunId_1: RunId | None = Field(None, alias='RunId')
    Score_1: Score | None = Field(None, alias='Score')
    Semantic_1: Semantic | None = Field(None, alias='Semantic')
    Sensitivity_1: Sensitivity | None = Field(None, alias='Sensitivity')
    Series_1: Series | None = Field(None, alias='Series')
    Severity_1: Severity | None = Field(None, alias='Severity')
    SkillSlug_1: SkillSlug | None = Field(None, alias='SkillSlug')
    Slug_1: Slug | None = Field(None, alias='Slug')
    SqlHash_1: SqlHash | None = Field(None, alias='SqlHash')
    TimeGrain_1: TimeGrain | None = Field(None, alias='TimeGrain')
    Timestamp_1: Timestamp | None = Field(None, alias='Timestamp')
    Viewport_1: Viewport | None = Field(None, alias='Viewport')
