# 新 V2 单任务提示词

当前路线使用 V2-P01～P10；完整任务边界见 [V2 主计划](../01_AGENT_DEVELOPMENT_PLAN.md)。

| 任务 | 提示词 | 状态 |
|---|---|---|
| V2-P01 | [源码行为基线与数据合同](V2-P01_CONTRACTS_CLAUDE_PROMPT.md) | 已准备，未执行；等待用户复制给 Claude Code |

每次只交付一个可独立执行的任务。Claude Code 先检查源码并简短说明范围，然后直接实施，完成后停止。Codex 默认负责讲解、提示词和审查，不替代实现。

提示词不是完成证据；实际状态以 [开发记录](../02_DEVELOPMENT_RECORD.md) 和 [验收清单](../03_ACCEPTANCE_CHECKLIST.md) 为准。旧 V2.1-Txx 提示词在 [旧路线归档](../../archive/PRE_PI_V2_2026-09-03/ARCHIVE_NOTICE.md)，不能作为当前实施命令。
