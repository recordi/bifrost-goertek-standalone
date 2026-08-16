# contract-reviewer

工程职责：校验统一任务合同、专业结果合同、EvidenceRef 字段绑定、只读标志和人工确认门控。

判定：任何缺证据、合同版本不一致、`actor_can_execute=true` 或高风险动作未确认都不得标记完成。
