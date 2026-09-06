// P09.3B §2.1 / §58：FunctionCasePage Artifact 与 Conversation focus 不一致时的安全提交。
// 采用保守规则：普通 continuation 走最小白名单；资产操作/无法可靠判断时不静默提交错项目。

const CONTINUATION_PATTERNS = [
  /^(继续|接着说|接着讲|接着解释|解释一下|为什么|怎么设计|这个概念|这是啥|什么意思|详细说|再说一遍)/,
  /^(那|那如果)?(上一条|你刚才说的|你说的|刚才)|(第一|二|三|四|五)?点/,
];

const ASSET_KEYWORDS = [
  "补", "新增", "加", "删除", "删掉", "移除", "修改", "改", "更新", "创建", "移动", "统一",
  "用例", "模块", "测试点", "测试资产", "预期", "边界", "覆盖", "检查一下", "看看",
];

export function isLikelyPlainContinuation(content) {
  const text = String(content || "").trim();
  if (!text) return false;
  if (CONTINUATION_PATTERNS.some((pattern) => pattern.test(text))) return true;
  // 短疑问句且不含资产关键词 → 保守放行
  return text.endsWith("？") || text.endsWith("?");
}

export function looksLikeAssetDirective(content) {
  const text = String(content || "");
  return ASSET_KEYWORDS.some((keyword) => text.includes(keyword));
}

// 页面与 Conversation focus 一致或 Conversation 无 focus → 交给 submitTurn 正常流程。
// 不一致：仅明确普通 continuation 允许继续旧 Conversation A；其余一律要求切换/新建。
export function planSubmitWithMismatch({ content, mismatch, messageNeedsWorkspaceContext }) {
  if (!mismatch) return { allowed: true };
  if (messageNeedsWorkspaceContext) return { allowed: false, reason: "mismatch_workspace" };
  if (isLikelyPlainContinuation(content)) return { allowed: true };
  return {
    allowed: false,
    reason: "mismatch_asset",
    hint:
      "当前页面是「项目 B」，但 Agent 仍绑定「项目 A」。\n" +
      "请新建对话或切回对应项目，避免对错误的资产执行修改。",
  };
}
