// 安全 Markdown 渲染（纯函数，无 DOM/React 依赖，便于 node:test）。
//
// 安全策略：不产生任何 HTML。renderMarkdown 只输出结构化数据
// （{type, children|text|items}），由组件侧映射为 React 元素；
// 所有文本经 React 文本节点输出 → 原始 HTML（含 <script>）只会被当作文本显示，
// 不可能注入执行。未启用 raw HTML。
//
// 支持：段落 / **bold** / `inline code` / ``` code block ``` / - 与 1. 列表。
// 容错：未闭合的 ** 或 ``` 退化为普通文本/代码块，不抛错。
export function parseInline(text) {
  const parts = [];
  const re = /(\*\*[^*]+\*\*|`[^`\n]+`)/g;
  let last = 0;
  let m;
  while ((m = re.exec(text))) {
    if (m.index > last) parts.push({ type: "text", text: text.slice(last, m.index) });
    const token = m[1];
    if (token.startsWith("**")) parts.push({ type: "bold", text: token.slice(2, -2) });
    else parts.push({ type: "code", text: token.slice(1, -1) });
    last = m.index + token.length;
  }
  if (last < text.length) parts.push({ type: "text", text: text.slice(last) });
  return parts;
}

const FENCE_OPEN = /^[ \t]*```([^\s`]*)[ \t]*$/;
const FENCE_CLOSE = /^[ \t]*```[ \t]*$/;
const LIST_ITEM = /^[ \t]*([-*]|\d+[.)])\s+(.*)$/;
const BULLET = "-*";

function isBullet(marker) {
  return marker.length === 1 && BULLET.includes(marker);
}

// 块级解析：返回 [{type:"paragraph", children:[segments]} | {type:"list",
// ordered, items:[segments]} | {type:"code", lang, text}]。
export function renderMarkdown(src) {
  const lines = String(src ?? "").split("\n");
  const blocks = [];
  let i = 0;

  const flushParagraph = (buf) => {
    if (!buf.length) return;
    const text = buf.join(" ");
    if (text.trim()) blocks.push({ type: "paragraph", children: parseInline(text) });
  };

  while (i < lines.length) {
    const line = lines[i];

    const fence = FENCE_OPEN.exec(line);
    if (fence) {
      const lang = fence[1];
      const buf = [];
      i += 1;
      while (i < lines.length && !FENCE_CLOSE.test(lines[i])) {
        buf.push(lines[i]);
        i += 1;
      }
      i += 1; // 跳过闭合行（未闭合则自然到 EOF）
      const text = buf.join("\n");
      if (text.trim()) blocks.push({ type: "code", lang, text });
      continue;
    }

    const item = LIST_ITEM.exec(line);
    if (item) {
      const ordered = !isBullet(item[1]);
      const items = [];
      while (i < lines.length) {
        const next = LIST_ITEM.exec(lines[i]);
        // 条目变成另一类型（有序→无序或反之）即列表结束；空行由外层负责分隔。
        if (!next || isBullet(next[1]) === ordered) break;
        items.push(parseInline(next[2]));
        i += 1;
      }
      if (items.length) blocks.push({ type: "list", ordered, items });
      continue;
    }

    if (line.trim() === "") {
      i += 1;
      continue;
    }

    const buf = [line];
    i += 1;
    while (i < lines.length && lines[i].trim() !== "" && !FENCE_OPEN.test(lines[i])
      && !LIST_ITEM.test(lines[i])) {
      buf.push(lines[i]);
      i += 1;
    }
    flushParagraph(buf);
  }
  flushParagraph([]);
  return blocks;
}
