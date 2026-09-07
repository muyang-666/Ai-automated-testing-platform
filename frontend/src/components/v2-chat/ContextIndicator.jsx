export default function ContextIndicator({ context }) {
  if (!context) return null;
  return (
    <div className={`v2chat-context ${context.mismatch ? "is-mismatch" : ""}`}>
      <span><b>AI 上下文</b> {context.label}{context.pending ? "（发送时绑定）" : ""}</span>
      {context.warning && <span className="v2chat-context-warning">{context.warning}</span>}
    </div>
  );
}
