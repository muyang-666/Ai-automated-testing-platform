---
name: test-design
version: 1.0.0
description: Incremental test-design guidance for editing a TestArtifact safely.
---

# Testing knowledge

Consider the dimensions that are relevant to the user's request: positive paths, failures,
boundaries, state transitions, permissions, timing, idempotency, consistency, combinations,
preconditions, input data, and observable expected results. Do not add every dimension by
default. Use the requirement and the existing Artifact to decide what matters.

Test cases should state concrete preconditions, executable steps, and observable expected
results. Preserve source references when they explain why a node exists.

# Behavior rules

1. Read an existing node or branch before changing it, unless the latest ToolResult already
   contains the complete current data.
2. Make the smallest edit that satisfies the user's request.
3. Preserve the user's grouping, names, and ordering unless restructuring was requested.
4. There is no mandatory generation path. Add test points, direct test cases, validation,
   duplicate checks, or coverage analysis only when the user's goal calls for them.
5. Never silently delete a large human-authored branch. Explain the impact and respect policy.
6. Prefer one small atomic batch for several edits that express one intent.
7. On revision conflict, read the current revision and the relevant nodes, re-evaluate, then retry
   at most twice in total (bounded recovery). If the target module/node no longer exists or the
   original intent is no longer clear, do not recreate it and do not guess — ask the user which
   part to change.
8. Quality tools diagnose only. They do not change the Artifact.
9. If “this one”, “the second”, or another reference cannot be resolved from recent messages
   and the recent diff, ask the user instead of guessing.
10. If the trusted workspace hint has selected_module_id and the user says “这里”, “这个模块”,
    or “当前模块”, treat that ID as the likely scope and call read_artifact_nodes before working.
11. If selected_case_id exists and the user says “这个用例”, read that case before a minimal
    update. Without a selected case, search or ask instead of guessing.
12. When an explicit module name resolves uniquely, read it and work directly. When several
    modules remain plausible, read the outline and ask a short clarification without writing.
