# BIFROST：多角色生产数据洞察看板

这是 BIFROST 的独立可复现仓库，只包含本项目实际使用的看板、数据适配、规则、只读 AI 桥接、辅助分析合同和测试数据。

## 内容边界

- `.omp/`：BIFROST 的数据映射、质量门禁、指标规则、角色工作流、事件下钻和 AI 桥接；
- `output/bifrost-ui-runtime/`：可直接运行的看板前端；
- `test-inputs/`：团队工程化模拟数据和歌尔脱敏测试数据；
- `fixtures/`：数据质量与技能回归夹具；
- `docs/`：复现、架构、交付和验收文档。

同学项目中只有已经通过 BIFROST 合同、证据绑定和只读边界验证的辅助分析能力被保留在 `.omp/integration/` 和相关测试中；没有收录同学项目原始的独立服务、前端或无关业务模块。因此这是一个项目，不是两个项目的拼接仓库。

## 启动

```powershell
$env:BIFROST_TEST_INPUT_ROOT = (Resolve-Path '.\test-inputs').Path
D:\anaconda3\envs\langchain\python.exe .omp\integration\serve_bifrost_ui.py --port 4173
```

打开 <http://127.0.0.1:4173/>。

AI 助手读取本机 OMP 配置；模型不可用时会明确切换到本地数据解释模式，不伪造模型结论。

## 可复现数据

- `test-inputs/BIFROST_飞书导入数据包_v3_P0修复版_SIM-v2.2.xlsx`：三产线团队工程化测试数据；
- `test-inputs/歌尔可脱敏企业测试数据集.xlsx`：命题提供的五领域脱敏测试数据。

两套数据经过同一套字段映射、数据质量检查、证据绑定、指标规则和角色投影流程。映射未确认时系统保持待确认，不生成伪指标。

## 验证

```powershell
D:\anaconda3\envs\langchain\python.exe -m unittest discover .omp\integration
D:\anaconda3\envs\langchain\python.exe -m unittest discover .omp\workstreams
```

详细步骤见 `docs/BIFROST_项目代码与数据复现说明.md` 和 `docs/REPOSITORY_GUIDE.md`。
