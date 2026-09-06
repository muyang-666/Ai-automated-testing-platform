"""Deterministic, read-only quality checks for P08 TestArtifact tools."""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from app.services.test_artifacts import artifact_service


def _flatten(root: dict | None) -> list[dict]:
    if root is None:
        return []
    result: list[dict] = []
    stack = [root]
    while stack:
        node = stack.pop()
        result.append(node)
        stack.extend(reversed(node.get("children") or []))
    return result


def _scope(nodes: list[dict], root_node_id: int | None) -> list[dict]:
    if root_node_id is None:
        return nodes
    by_id = {node["id"]: node for node in nodes}
    root = by_id.get(root_node_id)
    if root is None:
        return []
    return _flatten(root)


def validate_artifact(db: Session, *, artifact_id: int, requester,
                      root_node_id: int | None = None) -> dict:
    tree = artifact_service.get_tree(db, artifact_id=artifact_id, requester=requester)
    all_nodes = _flatten(tree["root"])
    nodes = _scope(all_nodes, root_node_id)
    issues: list[dict] = []
    if root_node_id is not None and not nodes:
        issues.append({"code": "node_not_found", "node_id": root_node_id,
                       "message": "指定节点不存在或已删除"})
    for node in nodes:
        if not str(node.get("title") or "").strip():
            issues.append({"code": "empty_title", "node_id": node["id"], "message": "节点标题为空"})
        if node.get("node_type") != "test_case":
            continue
        content = node.get("content") if isinstance(node.get("content"), dict) else {}
        if not content.get("steps"):
            issues.append({"code": "missing_steps", "node_id": node["id"], "message": "测试用例缺少步骤"})
        if not content.get("expected_results"):
            issues.append({"code": "missing_expected_results", "node_id": node["id"],
                           "message": "测试用例缺少可观察预期"})
    issues.sort(key=lambda item: (item.get("node_id") or 0, item["code"]))
    return {"artifact_id": artifact_id, "revision": tree["current_revision"],
            "checked_nodes": len(nodes), "issues": issues}


def _normalized(node: dict) -> str:
    content = node.get("content") if isinstance(node.get("content"), dict) else {}
    parts = [str(node.get("title") or ""), *(content.get("preconditions") or []),
             *(content.get("expected_results") or [])]
    for step in content.get("steps") or []:
        if isinstance(step, dict):
            parts.extend([str(step.get("action") or ""), str(step.get("data") or "")])
    return re.sub(r"[\W_]+", "", " ".join(parts).casefold(), flags=re.UNICODE)


# SequenceMatcher 全量两两比较为 O(n²)：候选数超过该上限时只分析前 N 个
# 确定性候选（保持树序遍历顺序），并在结果中明确 truncated（P08.1 规模保护）。
MAX_DUPLICATE_CANDIDATES = 200


def find_duplicates(db: Session, *, artifact_id: int, requester,
                    root_node_id: int | None = None, threshold: float = 0.88,
                    limit: int = 20, candidate_cap: int | None = None) -> dict:
    tree = artifact_service.get_tree(db, artifact_id=artifact_id, requester=requester)
    nodes = [node for node in _scope(_flatten(tree["root"]), root_node_id)
             if node.get("node_type") == "test_case"]
    total_cases = len(nodes)
    cap = MAX_DUPLICATE_CANDIDATES if candidate_cap is None else candidate_cap
    eligible: list[tuple[dict, str]] = []
    for node in nodes:
        normalized = _normalized(node)
        if normalized:
            eligible.append((node, normalized))
    # P08.2：eligible_cases=有内容的候选总数；analyzed_cases=真正进入两两比较的数量；
    # truncated 只表示确有候选被 cap 截断（仅当 eligible > cap 时为 True）。
    analyzed = eligible[:cap]
    pairs: list[dict] = []
    for index, (left, a) in enumerate(analyzed):
        for right, b in analyzed[index + 1:]:
            score = 1.0 if a == b else SequenceMatcher(None, a, b).ratio()
            if score >= threshold:
                pairs.append({"node_a": left["id"], "node_b": right["id"],
                              "reason": "normalized_content_similarity",
                              "score": round(score, 4)})
    pairs.sort(key=lambda pair: (-pair["score"], pair["node_a"], pair["node_b"]))
    return {"artifact_id": artifact_id, "revision": tree["current_revision"],
            "total_cases": total_cases, "eligible_cases": len(eligible),
            "analyzed_cases": len(analyzed), "truncated": len(eligible) > cap,
            "pairs": pairs[:limit]}


_DIMENSIONS = {
    "positive": ("正向", "正常", "成功", "positive", "happy"),
    "negative": ("异常", "失败", "错误", "拒绝", "negative"),
    "boundary": ("边界", "临界", "最大", "最小", "boundary"),
    "state_transition": ("状态", "转换", "锁定", "解锁", "state"),
    "permission": ("权限", "角色", "越权", "permission"),
    "timing": ("时序", "超时", "延迟", "时间", "timing"),
    "idempotency": ("幂等", "重复提交", "重试", "idempot"),
    "consistency": ("一致性", "事务", "同步", "consisten"),
}


def analyze_coverage(db: Session, *, artifact_id: int, requester,
                     root_node_id: int | None = None) -> dict:
    tree = artifact_service.get_tree(db, artifact_id=artifact_id, requester=requester)
    nodes = _scope(_flatten(tree["root"]), root_node_id)
    text = " ".join(
        f"{node.get('title', '')} {' '.join((node.get('content') or {}).get('tags') or [])}"
        for node in nodes if isinstance(node.get("content") or {}, dict)
    ).casefold()
    covered = [name for name, markers in _DIMENSIONS.items() if any(marker in text for marker in markers)]
    gaps = [{"type": name, "description": f"未发现{name}维度的明确测试设计"}
            for name in _DIMENSIONS if name not in covered]
    return {"artifact_id": artifact_id, "revision": tree["current_revision"],
            "analyzed_nodes": len(nodes), "covered": covered, "gaps": gaps}
