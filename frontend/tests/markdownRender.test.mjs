import { test } from "node:test";
import assert from "node:assert/strict";
import { parseInline, renderMarkdown } from "../src/components/v2-chat/markdownRender.js";

test("paragraph + bold + inline code 解析", () => {
  const [block] = renderMarkdown("请使用 **pytest** 跑 `tests/a.py`");
  assert.equal(block.type, "paragraph");
  assert.deepEqual(block.children, [
    { type: "text", text: "请使用 " },
    { type: "bold", text: "pytest" },
    { type: "text", text: " 跑 " },
    { type: "code", text: "tests/a.py" },
  ]);
});

test("代码块：含语言标注与多行内容", () => {
  const [block] = renderMarkdown("```python\ndef f():\n    return 1\n```");
  assert.equal(block.type, "code");
  assert.equal(block.lang, "python");
  assert.equal(block.text, "def f():\n    return 1");
});

test("无序与有序列表", () => {
  const [ul] = renderMarkdown("- 甲\n- 乙\n\n后续");
  assert.equal(ul.type, "list");
  assert.equal(ul.ordered, false);
  assert.equal(ul.items.length, 2);
  assert.deepEqual(ul.items[0], [{ type: "text", text: "甲" }]);

  const [ol, p] = renderMarkdown("1. 一步\n2. 二步\n\n正文");
  assert.equal(ol.type, "list");
  assert.equal(ol.ordered, true);
  assert.equal(ol.items.length, 2);
  assert.equal(p.type, "paragraph");
  assert.deepEqual(p.children, [{ type: "text", text: "正文" }]);
});

test("混排：加粗列表项 + 代码块后的段落", () => {
  const blocks = renderMarkdown("- **关键** 步骤\n- 直接 `x`\n\n```bash\necho hi\n```\n\n收尾");
  assert.equal(blocks.length, 3);
  assert.equal(blocks[0].type, "list");
  assert.deepEqual(blocks[0].items[0], [
    { type: "bold", text: "关键" },
    { type: "text", text: " 步骤" },
  ]);
  assert.equal(blocks[1].type, "code");
  assert.deepEqual(blocks[2].children, [{ type: "text", text: "收尾" }]);
});

// 安全：无任何 HTML 输出；原始 HTML 只会成为纯文本（组件以 React 文本节点渲染）。
test("raw HTML 不会产生 html 类型，只会以文本保留", () => {
  const blocks = renderMarkdown('<script>alert("x")</script> 与 <b>加粗标签</b>');
  const hasHtml = JSON.stringify(blocks).includes('"type":"html"');
  assert.equal(hasHtml, false);
  assert.equal(blocks[0].children[0].text, '<script>alert("x")</script> 与 <b>加粗标签</b>');
});

test("容错：未闭合 bold/code fence 不抛错", () => {
  assert.doesNotThrow(() => renderMarkdown("**未闭合加粗"));
  const blocks = renderMarkdown("```python\n没有闭合围栏");
  assert.equal(blocks[0].type, "code");
  assert.equal(blocks[0].text, "没有闭合围栏");
  assert.equal(renderMarkdown("").length, 0);
  assert.equal(renderMarkdown(null).length, 0);
});

test("parseInline 空串返回空数组", () => {
  assert.deepEqual(parseInline(""), []);
  assert.deepEqual(parseInline("纯文本"), [{ type: "text", text: "纯文本" }]);
});
