# 07 — 变更日志

---

## [UNRELEASED] — 初始化文档

**日期**：2026-05-01

### Added
- 新增 `docs/00_PROJECT_CONTEXT.md` — 项目上下文文档
- 新增 `docs/01_REQUIREMENTS.md` — 需求规格文档
- 新增 `docs/06_CURRENT_STATUS.md` — 当前状态文档
- 新增 `docs/07_CHANGELOG.md` — 变更日志文档（本文件）
- 新增 `docs/08_AI_CODING_RULES.md` — AI 编码规则文档
- 新增 `docs/09_ACCEPTANCE_CHECKLIST.md` — 验收清单文档
- 新建 `docs/` 目录作为项目文档根目录

### Changed
- 无业务代码变更

---

## 版本记录规则

后续每次功能迭代，在本文件中按以下格式记录：

```markdown
## [VX.Y] — 简短标题

**日期**：YYYY-MM-DD

### Added
- 新增的功能

### Changed
- 修改的功能

### Fixed
- 修复的问题

### Deprecated
- 即将废弃的功能
```

---

## 历史版本（V1.0 ~ V1.5）

以下为文档建设之前的版本记录（基于 git log 回溯）：

| 版本 | Git Commit | 内容概要 |
|------|-----------|---------|
| V1.0 | `cad202f` ~ `37b2756` | Demo 初始化：FastAPI + React 框架搭建，用例 CRUD，LLM/规则代码生成，pytest 执行 |
| V1.1 | `7cfe88d` | README 更新 |
| V1.2 | `922e263` | 参数管理模块（parameter.py 在线编辑） |
| V1.3 | `ead52ef` | 场景管理模块（场景 CRUD + 步骤管理 + 场景执行） |
| V1.4 | `e8a9f32` | AI 分析模块（失败根因分析） |
| V1.5 | `6e2589d` | 报告模块（项目级测试报告生成） |
