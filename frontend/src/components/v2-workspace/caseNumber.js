// 展示编号：与后端 app/services/test_artifacts/case_number.py 同一格式
// TC-{ArtifactNode.id:06d}（Server identity 派生，移动/排序不变，无需抢号）。
export function formatCaseNumber(nodeId) {
  if (!Number.isInteger(nodeId) || nodeId <= 0) return "";
  return `TC-${String(nodeId).padStart(6, "0")}`;
}
