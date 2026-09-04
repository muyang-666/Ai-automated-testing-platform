# V2-P07 阶段执行任务书
## Test Artifact Core

> 数据模型以 05_TECHNICAL_DESIGN §6～§10 为准。

## Goal

建立与 Agent 解耦的长期 TestArtifact Domain。

无 LLM 也必须完成：

```text
create
→ add/update/delete/move
→ Revision
→ Diff
→ Undo
→ conflict
```

## Domain

```text
TestArtifact
ArtifactNode
ArtifactRevision
ArtifactOperation
```

Node 首期：

```text
root / group / test_point / test_case
```

推荐目录：

```text
backend/app/test_artifacts/
  models/
  schemas/
  services/
  repository/
  diff/
```

核心边界：

> Agent 使用 Artifact；Artifact 不依赖 Agent。

## Operations

支持：

```text
add_node
update_node
delete_node
move_node
restore
```

一次 batch = 一个事务 + 一个 Revision。

## Optimistic concurrency

所有写操作：

```text
expected_revision
```

不匹配：

```text
409 revision_conflict
```

数据库裁决，不依赖前端锁。

## Tree integrity

验证：

- parent same artifact；
- cycle forbidden；
- root rules；
- delete subtree；
- order；
- type constraints。

## Diff

支持：

```text
added / updated / deleted / moved
```

update 提供字段 before/after。

## Undo

Undo 产生新 Revision，不删除历史。

## SourceRef

支持通用：

```text
source_type/source_id/fragment_id/snapshot_hash
```

P07 不做复杂需求解析。

## API

基础：

```text
POST /test-artifacts
GET /test-artifacts/{id}
GET /test-artifacts/{id}/tree
POST /test-artifacts/{id}/operations
GET /test-artifacts/{id}/revisions
GET /test-artifacts/{id}/diff
POST /test-artifacts/{id}/undo
```

人工 UI 与未来 Agent Tool 必须共用同一 Application Service。

## Tests

完全 deterministic：

- create；
- 20 nodes；
- update/move/delete；
- cycle；
- batch rollback；
- diff；
- undo；
- stale revision；
- concurrent DB sessions；
- cross-user/project；
- migration。

## Stop boundary

不做：

- Agent Artifact Tools；
- LLM 生成；
- Skill；
- MindMap；
- CRDT；
- Git DAG。
