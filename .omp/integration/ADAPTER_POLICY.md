# BIFROST 固定适配器策略

入口：`run_bifrost_adapter.py`

## 允许

- 无参数运行一个固定的 `orchestration_test_entry.py`
- 读取固定的 `.omp/integration/orchestration_test_results.json`
- 输出经过校验的 JSON 到标准输出

## 禁止

- 任何命令行参数
- 任意脚本路径、模块名或输入文件路径
- 写入 Skill、业务数据、测试输入、vendor、apps、packages、UI 或载荷
- 创建飞书任务、确认记录或外部系统记录
- 结果不通过时继续输出成功

适配器只在全部六项回归检查通过、三个专业任务均为只读且受保护目录哈希不变时返回 `status=PASS`。
