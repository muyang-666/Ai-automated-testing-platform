const TOOL_LABELS = {
  get_current_artifact: "读取当前测试资产",
  read_artifact_outline: "读取测试结构",
  read_artifact_nodes: "读取测试用例",
  search_artifact: "搜索测试资产",
  get_artifact_diff: "读取最近变更",
  read_requirement: "读取需求",
  add_artifact_node: "新增测试项",
  update_artifact_node: "更新测试项",
  delete_artifact_node: "删除测试项",
  move_artifact_node: "移动测试项",
  batch_apply_artifact_operations: "批量修改测试资产",
  validate_test_artifact: "检查测试资产",
  analyze_test_coverage: "检查测试覆盖",
  find_duplicate_cases: "检查重复用例",
  load_skill: "加载测试设计规则",
  calculator: "计算",
};

export function toolDisplayName(name) {
  return TOOL_LABELS[name] || "使用工具";
}
