# BIFROST 外部测试输入

本目录仅用于在 OMP 隔离副本中运行字段映射 Skill 的能力回归，不属于任何 Skill 包，也不会被发布为 Skill 运行资产。

- `BIFROST_飞书导入数据包_v3_P0修复版_SIM-v2.2.xlsx`：团队工程化模拟数据
- `歌尔可脱敏企业测试数据集.xlsx`：官方提供的脱敏模拟数据

测试运行器通过 `BIFROST_TEST_INPUT_ROOT` 读取此目录；Skill 本身不携带或写回这些文件。
