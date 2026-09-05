import { messageFailure } from "./conversationErrors.js";
import ToolActivity from "./ToolActivity.jsx";

const TURN_BADGE = {
  queued: { text: "Queued", cls: "queued" },
  running: { text: "", cls: "running" },
  failed: { text: "Failed", cls: "failed" },
  interrupted: { text: "Interrupted", cls: "interrupted" },
  cancelled: { text: "Cancelled", cls: "cancelled" },
  paused: { text: "Paused", cls: "paused" },
};

// 一个 Turn = 一条用户消息 + 该 Run 的工具活动 + 助手回复。
// 组件只消费 turnModel.buildConversationTurns 的结构化结果。
export default function ChatTurn({ turn }) {
  const badge = TURN_BADGE[turn.status];
  return (
    <section className="v2-turn" data-status={turn.status || "idle"}>
      {turn.userMessage ? (
        <div className="v2-turn-user">
          <div className="v2-msg user">{turn.userText}</div>
          {badge?.text && <span className={`v2-turn-badge ${badge.cls}`}>{badge.text}</span>}
        </div>
      ) : null}

      {turn.toolActivities?.map((activity) => (
        <div key={activity.toolCallId} className="v2-turn-tools">
          <ToolActivity activity={activity} />
        </div>
      ))}

      {turn.streamingText ? (
        <div className="v2-turn-assistant">
          {turn.assistantTexts?.map((text, i) => <div className="v2-msg assistant" key={i}>{text}</div>)}
          <div className="v2-msg assistant streaming">{turn.streamingText}</div>
        </div>
      ) : (
        turn.assistantTexts?.length > 0 && (
          <div className="v2-turn-assistant">
            {turn.assistantTexts.map((text, i) => <div className="v2-msg assistant" key={i}>{text}</div>)}
          </div>
        )
      )}

      {turn.assistantMessage?.error_code ? (
        <div className="v2-turn-error" role="status">{messageFailure(turn.assistantMessage)}</div>
      ) : null}
    </section>
  );
}
