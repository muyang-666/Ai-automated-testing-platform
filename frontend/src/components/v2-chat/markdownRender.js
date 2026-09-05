// 安全 Markdown 渲染（纯函数，无 DOM/React 依赖，便于 node:test）。
//
// 安全策略：只输出结构化数据，由 React 文本节点负责渲染；原始 HTML 永远
// 不会转换为 DOM。支持对话中常用的标题、段落/换行、分隔线、表格、列表、
// 粗体、行内代码和 fenced code block。

export function parseInline(text) {
  const parts = [];
  const re = /(\*\*[^*]+\*\*|`[^`\n]+`)/g;
  let last = 0;
  let match;
  while ((match = re.exec(text))) {
    if (match.index > last) parts.push({ type: "text", text: text.slice(last, match.index) });
    const token = match[1];
    if (token.startsWith("**")) parts.push({ type: "bold", text: token.slice(2, -2) });
    else parts.push({ type: "code", text: token.slice(1, -1) });
    last = match.index + token.length;
  }
  if (last < text.length) parts.push({ type: "text", text: text.slice(last) });
  return parts;
}

const FENCE_OPEN = /^[ \t]*```([^\s`]*)[ \t]*$/;
const FENCE_CLOSE = /^[ \t]*```[ \t]*$/;
const LIST_ITEM = /^[ \t]*([-*]|\d+[.)])\s+(.*)$/;
const HEADING = /^[ \t]{0,3}(#{1,6})\s+(.+?)[ \t]*#*[ \t]*$/;
const DIVIDER = /^[ \t]{0,3}(?:(?:-[ \t]*){3,}|(?:\*[ \t]*){3,}|(?:_[ \t]*){3,})$/;
const TABLE_DIVIDER_CELL = /^:?-{3,}:?$/;
const BULLET = "-*";

function isBullet(marker) {
  return marker.length === 1 && BULLET.includes(marker);
}

function parseParagraphLines(lines) {
  const children = [];
  lines.forEach((line, index) => {
    if (index > 0) children.push({ type: "break" });
    children.push(...parseInline(line));
  });
  return children;
}

// 按未转义且不在 inline-code 内的竖线拆分，避免 `a|b` 被误切。
function splitTableRow(line) {
  let source = String(line).trim();
  if (source.startsWith("|")) source = source.slice(1);
  if (source.endsWith("|") && !source.endsWith("\\|")) source = source.slice(0, -1);

  const cells = [];
  let cell = "";
  let inCode = false;
  for (let i = 0; i < source.length; i += 1) {
    const char = source[i];
    if (char === "\\" && source[i + 1] === "|") {
      cell += "|";
      i += 1;
    } else if (char === "`") {
      inCode = !inCode;
      cell += char;
    } else if (char === "|" && !inCode) {
      cells.push(cell.trim());
      cell = "";
    } else {
      cell += char;
    }
  }
  cells.push(cell.trim());
  return cells;
}

function tableDefinitionAt(lines, index) {
  if (index + 1 >= lines.length || !lines[index].includes("|")) return null;
  const headers = splitTableRow(lines[index]);
  const dividers = splitTableRow(lines[index + 1]);
  if (headers.length < 2 || headers.length !== dividers.length
    || !dividers.every((cell) => TABLE_DIVIDER_CELL.test(cell.replace(/\s/g, "")))) return null;
  const align = dividers.map((cell) => {
    const value = cell.replace(/\s/g, "");
    if (value.startsWith(":") && value.endsWith(":")) return "center";
    if (value.endsWith(":")) return "right";
    return "left";
  });
  return { headers, align };
}

function startsBlock(lines, index) {
  const line = lines[index] || "";
  return FENCE_OPEN.test(line) || LIST_ITEM.test(line) || HEADING.test(line)
    || DIVIDER.test(line) || Boolean(tableDefinitionAt(lines, index));
}

// 返回 heading / paragraph / divider / table / list / code 等结构化块。
export function renderMarkdown(src) {
  const lines = String(src ?? "").replace(/\r\n?/g, "\n").split("\n");
  const blocks = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    const fence = FENCE_OPEN.exec(line);
    if (fence) {
      const lang = fence[1];
      const buffer = [];
      i += 1;
      while (i < lines.length && !FENCE_CLOSE.test(lines[i])) {
        buffer.push(lines[i]);
        i += 1;
      }
      if (i < lines.length) i += 1;
      const text = buffer.join("\n");
      if (text.trim()) blocks.push({ type: "code", lang, text });
      continue;
    }

    const heading = HEADING.exec(line);
    if (heading) {
      blocks.push({ type: "heading", level: heading[1].length, children: parseInline(heading[2]) });
      i += 1;
      continue;
    }

    if (DIVIDER.test(line)) {
      blocks.push({ type: "divider" });
      i += 1;
      continue;
    }

    const table = tableDefinitionAt(lines, i);
    if (table) {
      const rows = [];
      i += 2;
      while (i < lines.length && lines[i].trim() && lines[i].includes("|")) {
        const cells = splitTableRow(lines[i]);
        if (cells.length !== table.headers.length) break;
        rows.push(cells.map(parseInline));
        i += 1;
      }
      blocks.push({
        type: "table",
        headers: table.headers.map(parseInline),
        align: table.align,
        rows,
      });
      continue;
    }

    const item = LIST_ITEM.exec(line);
    if (item) {
      const ordered = !isBullet(item[1]);
      const items = [];
      while (i < lines.length) {
        const next = LIST_ITEM.exec(lines[i]);
        if (!next || isBullet(next[1]) === ordered) break;
        items.push(parseInline(next[2]));
        i += 1;
      }
      if (items.length) blocks.push({ type: "list", ordered, items });
      continue;
    }

    if (!line.trim()) {
      i += 1;
      continue;
    }

    const buffer = [line];
    i += 1;
    while (i < lines.length && lines[i].trim() && !startsBlock(lines, i)) {
      buffer.push(lines[i]);
      i += 1;
    }
    blocks.push({ type: "paragraph", children: parseParagraphLines(buffer) });
  }

  return blocks;
}
