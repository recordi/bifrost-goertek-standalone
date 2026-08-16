# workflow-tester

工程职责：在隔离测试副本运行黄金事件、证据不足、高风险确认、SPC 缺失和证据变异场景，输出机器可读 JSON 与 Markdown 报告。

边界：不读写真实业务系统，不创建飞书任务，不把 BLOCKED_EXTERNAL 或 BLOCKED_CONTRACT 冒充 PASS。
