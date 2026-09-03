import { Button, Input } from "antd";
import { useEffect, useRef } from "react";

const { TextArea } = Input;

function messageText(item) {
  if (typeof item?.content === "string") return item.content;
  if (typeof item?.message === "string") return item.message;
  return "";
}

export default function AgentConversation({
  messages,
  draft,
  onDraftChange,
  onSend,
  sending,
  disabled,
  sourceContext,
  children,
}) {
  const listRef = useRef(null);

  useEffect(() => {
    const element = listRef.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [messages]);

  const handleKeyDown = (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      if (!disabled && draft.trim()) onSend();
    }
  };

  return (
    <div className="test-agent-conversation">
      {sourceContext && (
        <div className="test-agent-context-chip">
          <span>{sourceContext.sourceType === "requirement" ? "需求" : "接口文档"}</span>
          <strong>{sourceContext.sourceLabel || `#${sourceContext.sourceId}`}</strong>
        </div>
      )}

      <div className="test-agent-messages" ref={listRef}>
        {messages.map((item, index) => {
          const role = item.role || "assistant";
          return (
            <div className={`test-agent-message is-${role}`} key={item.id || `${role}-${index}`}>
              <div className="test-agent-message-avatar">{role === "user" ? "你" : "AI"}</div>
              <div className="test-agent-message-body">
                <p>{messageText(item)}</p>
                {item.created_at && (
                  <time>
                    {new Date(item.created_at).toLocaleTimeString("zh-CN", {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </time>
                )}
              </div>
            </div>
          );
        })}
        {children}
      </div>

      <div className="test-agent-composer">
        <TextArea
          value={draft}
          onChange={(event) => onDraftChange(event.target.value)}
          onKeyDown={handleKeyDown}
          autoSize={{ minRows: 2, maxRows: 5 }}
          placeholder={sourceContext ? "告诉 Agent 你的测试重点…" : "请先从需求或接口文档点击“交给 Agent”…"}
          disabled={disabled}
          maxLength={500}
          aria-label="测试目标"
        />
        <div className="test-agent-composer-footer">
          <span>Enter 发送 · Shift+Enter 换行</span>
          <Button type="primary" loading={sending} disabled={disabled || !draft.trim()} onClick={onSend}>
            发送
          </Button>
        </div>
      </div>
    </div>
  );
}
