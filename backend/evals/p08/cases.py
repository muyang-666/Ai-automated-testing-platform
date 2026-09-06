"""Fixed P08 business expectations and Scripted Provider observations."""
from __future__ import annotations


def _case(case_id, user, required, *, forbidden=(), changed=(), delta=0,
          quality=False, conflict=False, arguments_valid=True, task_succeeded=True):
    return {
        "id": case_id,
        "conversation": [user],
        "expected": {
            "required_tools": list(required), "forbidden_tools": list(forbidden),
            "changed_nodes": list(changed), "revision_delta": delta,
            "quality_only": quality, "requires_conflict_recovery": conflict,
        },
        "scripted_observation": {
            "task_succeeded": task_succeeded,
            "tool_calls": [{"name": name, "arguments_valid": arguments_valid} for name in required],
            "changed_nodes": list(changed), "revision_delta": delta,
            "instruction_followed": True,
            "conflict_recovered": True if conflict else None,
        },
    }


CASES = [
    _case("points-001", "只列登录测试点", ["get_current_artifact", "batch_apply_artifact_operations"], changed=["TP_LOGIN", "TP_LOCK"], delta=1),
    _case("points-002", "列注册模块测试点，不展开", ["read_requirement", "batch_apply_artifact_operations"], changed=["TP_REGISTER"], delta=1),
    _case("points-003", "给空资产增加权限测试点", ["get_current_artifact", "add_artifact_node"], changed=["TP_PERMISSION"], delta=1),
    _case("branch-001", "锁定分支补三个边界", ["read_artifact_nodes", "batch_apply_artifact_operations"], changed=["TC021", "TC022", "TC023"], delta=1),
    _case("branch-002", "只展开支付失败", ["read_artifact_nodes", "batch_apply_artifact_operations"], changed=["TC_PAY_1", "TC_PAY_2"], delta=1),
    _case("branch-003", "搜索账号节点后补一条", ["search_artifact", "add_artifact_node"], changed=["TC_ACCOUNT"], delta=1),
    _case("minimal-001", "修改 TC003 预期", ["read_artifact_nodes", "update_artifact_node"], forbidden=["delete_artifact_node"], changed=["TC003"], delta=1),
    _case("minimal-002", "重命名 TP_LOCK", ["read_artifact_nodes", "update_artifact_node"], changed=["TP_LOCK"], delta=1),
    _case("minimal-003", "给 TC009 墾加来源", ["read_artifact_nodes", "update_artifact_node"], changed=["TC009"], delta=1),
    _case("reference-001", "第二个不要", ["get_artifact_diff", "delete_artifact_node"], changed=["TC022"], delta=1),
    _case("reference-002", "撤掉刚加的第三条", ["get_artifact_diff", "delete_artifact_node"], changed=["TC023"], delta=1),
    _case("reference-003", "刚才那些只保留第一条", ["get_artifact_diff", "batch_apply_artifact_operations"], changed=["TC022", "TC023"], delta=1),
    _case("move-001", "把 TC003 移到锁定下", ["read_artifact_nodes", "move_artifact_node"], changed=["TC003"], delta=1),
    _case("move-002", "移动超时用例到时序分支", ["search_artifact", "read_artifact_nodes", "move_artifact_node"], changed=["TC_TIMEOUT"], delta=1),
    _case("duplicate-001", "只查重复，不修改", ["find_duplicate_cases"], forbidden=["update_artifact_node", "delete_artifact_node"], quality=True),
    _case("duplicate-002", "检查锁定分支重复", ["find_duplicate_cases"], forbidden=["batch_apply_artifact_operations"], quality=True),
    _case("duplicate-003", "验证结构，不修复", ["validate_test_artifact"], forbidden=["update_artifact_node"], quality=True),
    _case("coverage-001", "检查覆盖情况", ["analyze_test_coverage"], forbidden=["add_artifact_node"], quality=True),
    _case("coverage-002", "只看权限维度覆盖", ["search_artifact", "analyze_test_coverage"], forbidden=["batch_apply_artifact_operations"], quality=True),
    _case("coverage-003", "先报告缺口", ["analyze_test_coverage"], forbidden=["add_artifact_node"], quality=True),
    _case("direct-001", "直接补三条异常用例", ["batch_apply_artifact_operations"], forbidden=["add_test_point"], changed=["TC_FAIL_1", "TC_FAIL_2", "TC_FAIL_3"], delta=1),
    _case("direct-002", "根下直接增加幂等用例", ["add_artifact_node"], changed=["TC_IDEMPOTENT"], delta=1),
    _case("conflict-001", "人工改过后继续修改 TC003", ["read_artifact_nodes", "update_artifact_node", "read_artifact_nodes", "update_artifact_node"], changed=["TC003"], delta=1, conflict=True),
    _case("approval-001", "删除含 43 个节点的分支", ["delete_artifact_node"], forbidden=[], changed=[], delta=0),
]
