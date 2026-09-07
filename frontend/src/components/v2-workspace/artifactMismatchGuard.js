// P09.3B §2.1 修正（P09.3B.1 #1）：mismatch 时安全优先的分类规则。
// 判断顺序：workspace/reference 指令 → asset read/write 指令（含问句形式的资产问题）
// → 明确普通 continuation → 明确与当前 Artifact 无关的知识问答 → 其它默认 block。
// 不用复杂 NLP；全部为明确规则列表。

const WORKSPACE_REFERENCE_PATTERNS = [
  /这里/, /这边/, /这个模块/, /当前模块/, /这个用例/, /当前用例/,
  /选中的/, /所选/, /刚改的/, /刚才改的/,
];

const ASSET_DIRECTIVE_PATTERNS = [
  // 动词型指令
  /补/, /新增/, /添加/, /加一个/, /增加/, /创建/, /删除/, /删掉/, /移除/,
  /修改/, /改一下/, /更新/, /移动/, /统一/, /检查/, /看看覆盖/, /覆盖/,
  /把这个预期/, /预期改/, /按我/, /把我刚/, /做(几个|一条|一下)/,
  // 名词型资产问题（含问句）：提到 模块/用例/测试点/测试资产 即视为资产请求
  /模块/, /用例/, /测试点/, /测试资产/, /有哪些/, /哪些(边界|场景|用例)/,
  /这个(模块|用例|需求|资产)/, /当前(模块|项目).*(补|缺|加|改|查|做)/,
];

const CONVERSATION_CONTINUATION_PATTERNS = [
  /^继续/, /^接着/, /^再说一遍/, /^详细(解释|说明|讲讲)/, /^再举个例子/,
  /^为什么(你)?(刚才|这样|这么)/, /^这个概念是什么意思/, /^第二点/,
  /^第一点/, /^上一条/, /^你刚才说的/, /^你说的第/,
];

const GENERAL_KNOWLEDGE_PATTERNS = [
  /^什么是(边界值|等价类|状态迁移|场景法|判定表|正交|错误推测|探索性测试|冒烟|回归|覆盖率|优先级|测试用例|测试设计|单元测试|集成测试)/,
  /^(介绍一下|解释一下|讲讲)(边界值|等价类|状态迁移|测试|用例设计)/,
  /^(和|与)什么区别/,
];

export function looksLikeWorkspaceReference(content) {
  return WORKSPACE_REFERENCE_PATTERNS.some((pattern) => pattern.test(String(content || "")));
}

export function looksLikeAssetDirective(content) {
  return ASSET_DIRECTIVE_PATTERNS.some((pattern) => pattern.test(String(content || "")));
}

export function looksLikeConversationContinuation(content) {
  const text = String(content || "").trim();
  return CONVERSATION_CONTINUATION_PATTERNS.some((pattern) => pattern.test(text));
}

export function looksLikeGeneralKnowledgeQuestion(content) {
  const text = String(content || "").trim();
  return GENERAL_KNOWLEDGE_PATTERNS.some((pattern) => pattern.test(text));
}

export function isLikelyPlainContinuation(content) {
  // 保留导出兼容：仅允许明确 continuation（不再用“任意 ? 结尾”放行资产问题）
  return looksLikeConversationContinuation(content);
}

// 页面与 Conversation focus 不一致时决定是否允许提交。
export function planSubmitWithMismatch({ content, mismatch, messageNeedsWorkspaceContext }) {
  if (!mismatch) return { allowed: true };
  if (messageNeedsWorkspaceContext) return { allowed: false, reason: "mismatch_workspace" };
  const text = String(content || "");
  // 1) workspace/reference 指令
  if (looksLikeWorkspaceReference(text) || messageNeedsWorkspaceContext) {
    return { allowed: false, reason: "mismatch_workspace", hint: workspaceHint };
  }
  // 2) asset read/write 指令（问句形式的资产问题同样 block）
  if (looksLikeAssetDirective(text)) {
    return { allowed: false, reason: "mismatch_asset", hint: workspaceHint };
  }
  // 3) 明确普通 continuation
  if (looksLikeConversationContinuation(text)) return { allowed: true };
  // 4) 明确与当前 Artifact 无关的知识问答
  if (looksLikeGeneralKnowledgeQuestion(text)) return { allowed: true };
  // 5) 其它默认 block（安全优先）
  return { allowed: false, reason: "mismatch_default", hint: workspaceHint };
}

const workspaceHint =
  "当前页面是「项目 B」，但 Agent 仍绑定「项目 A」。\n" +
  "请新建对话或切回对应项目，避免对错误的资产执行修改。";
