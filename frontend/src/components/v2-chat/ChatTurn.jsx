import { messageFailure } from "./conversationErrors.js";
import ToolActivity from "./ToolActivity.jsx";
import { renderMarkdown } from "./markdownRender.js";

const TURN_BADGE = {
  queued: { text: "排队中", cls: "queued" },
  running: null,
  failed: { text: "失败", cls: "failed" },
  interrupted: { text: "已中断", cls: "interrupted" },
  cancelled: { text: "已取消", cls: "cancelled" },
  paused: { text: "已暂停", cls: "paused" },
};

// Markdown 结构化数据 → React 元素。markdownRender 只输出数据、无任何 HTML，
// 文本一律经 React 文本节点输出 → 原始 HTML 仅作文本显示，无法注入。
function InlineSegments({ segments }) {
  return segments.map((seg, index) => {
    if (seg.type === "break") return <br key={index} />;
    if (seg.type === "bold") return <strong key={index}>{seg.text}</strong>;
    if (seg.type === "code") return <code className="v2-md-code" key={index}>{seg.text}</code>;
    return <span key={index}>{seg.text}</span>;
  });
}

function MarkdownBlock({ block }) {
  if (block.type === "code") {
    return <pre className="v2-md-pre"><code>{block.text}</code></pre>;
  }
  if (block.type === "heading") {
    const Heading = `h${block.level}`;
    return <Heading className={`v2-md-heading v2-md-h${block.level}`}><InlineSegments segments={block.children} /></Heading>;
  }
  if (block.type === "divider") return <hr className="v2-md-divider" />;
  if (block.type === "table") {
    return (
      <div className="v2-md-table-wrap" tabIndex={0} role="region" aria-label="Markdown 表格">
        <table className="v2-md-table">
          <thead><tr>{block.headers.map((cell, index) => (
            <th key={index} data-align={block.align[index]}><InlineSegments segments={cell} /></th>
          ))}</tr></thead>
          <tbody>{block.rows.map((row, rowIndex) => (
            <tr key={rowIndex}>{row.map((cell, cellIndex) => (
              <td key={cellIndex} data-align={block.align[cellIndex]}><InlineSegments segments={cell} /></td>
            ))}</tr>
          ))}</tbody>
        </table>
      </div>
    );
  }
  if (block.type === "list") {
    const items = block.items.map((item, i) => (
      <li key={i}><InlineSegments segments={item} /></li>
    ));
    return block.ordered ? <ol className="v2-md-list">{items}</ol> : <ul className="v2-md-list">{items}</ul>;
  }
  return <p className="v2-md-p"><InlineSegments segments={block.children} /></p>;
}

function MarkdownBody({ text, streaming }) {
  const blocks = renderMarkdown(text);
  if (!blocks.length) return null;
  return (
    <div className={streaming ? "v2-md streaming" : "v2-md"}>
      {blocks.map((block, i) => <MarkdownBlock key={i} block={block} />)}
    </div>
  );
}

// 一个 Turn = 一条用户消息 + 该 Run 的工具活动 + 助手回复。
// 组件只消费 turnModel.buildConversationTurns 的结构化结果。
export default function ChatTurn({ turn }) {
  const badge = turn.status ? TURN_BADGE[turn.status] : null;
  return (
    <section className="v2-turn" data-status={turn.status || "idle"}>
      {turn.userMessage ? (
        <div className="v2-turn-user">
          <div className="v2-msg user">{turn.userText}</div>
        </div>
      ) : null}

      {badge?.text ? <span className={`v2-turn-badge ${badge.cls}`}>{badge.text}</span> : null}

      {turn.toolActivities?.length > 0 && (
        <div className="v2-turn-tools">
          {turn.toolActivities.map((activity) => (
            <ToolActivity key={`${activity.runId ?? ""}-${activity.toolCallId}`} activity={activity} />
          ))}
        </div>
      )}

      {turn.assistantTexts?.map((text, i) => <MarkdownBody key={i} text={text} />)}

      {turn.streamingText ? <MarkdownBody streaming text={turn.streamingText} /> : null}

      {turn.assistantMessage?.error_code ? (
        <div className="v2-turn-error" role="status">{messageFailure(turn.assistantMessage)}</div>
      ) : null}
    </section>
  );
}
