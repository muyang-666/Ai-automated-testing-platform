import { useEffect, useRef, useState } from "react";
import ChatTurn from "./ChatTurn.jsx";
import { isNearBottom, shouldAutoScroll } from "./scrollPolicy.js";

const SCROLL_THRESHOLD = 80;

// 消息时间轴：维护 isNearBottom，按场景自动滚动。
// 切换/打开任意 Conversation 都默认滚到底（不做 per-conversation 只滚一次）；
// 自己发送强制到底；流式仅在近底部跟随；用户主动上滑看历史时绝不强制拉回，
// 只显示"↓ 回到最新"。
export default function ChatTimeline({ turns, streaming, activeId, sendNonce }) {
  const containerRef = useRef(null);
  const intent = useRef(null); // "force"（切换会话/自己发送时置位）
  const [nearBottom, setNearBottom] = useState(true);
  const [jumpVisible, setJumpVisible] = useState(false);

  const updatePosition = () => {
    const el = containerRef.current;
    if (!el) return;
    const bottom = isNearBottom(el.scrollTop, el.clientHeight, el.scrollHeight, SCROLL_THRESHOLD);
    setNearBottom(bottom);
    setJumpVisible(!bottom);
  };

  const scrollToBottom = (behavior = "auto") => {
    const el = containerRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior });
  };

  // activeId 每次变化（含从别的会话切回来）都默认滚到底。
  // 状态更新放在 requestAnimationFrame 内，避免 effect 内同步 setState。
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return undefined;
    el.addEventListener("scroll", updatePosition, { passive: true });
    updatePosition();
    intent.current = "force";
    requestAnimationFrame(() => {
      scrollToBottom();
      setNearBottom(true);
      setJumpVisible(false);
    });
    return () => el.removeEventListener("scroll", updatePosition);
  }, [activeId]);

  // 内容变化：intent=force（切换）或 sendNonce（自己发送）→ 强制到底；
  // 其余（流式/刷新）仅在近底部时跟随，用户上滑时不动。
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    if (intent.current === "force" || sendNonce > 0) {
      const force = intent.current === "force";
      intent.current = null;
      requestAnimationFrame(() => {
        scrollToBottom();
        if (force) { setNearBottom(true); setJumpVisible(false); }
      });
      return;
    }
    if (shouldAutoScroll({ eventKind: "stream", isNearBottomNow: nearBottom })) {
      requestAnimationFrame(scrollToBottom);
    }
    // 依赖 turns/streaming 内容变化（含流式文本增长）触发本 effect。
  }, [turns, streaming, activeId, sendNonce, nearBottom]);

  return (
    <div className="v2-timeline" ref={containerRef}>
      <div className="v2-timeline-inner">
        {!turns?.length && (
          <div className="v2-empty">开始新的对话…<br />可以直接提问，AI 会自主决定是否使用工具。</div>
        )}
        {turns?.map((turn) => (
          <ChatTurn key={`${turn.ownerSequence}-${turn.runId || "pending"}`} turn={turn} />
        ))}
        {jumpVisible && (
          <button type="button" className="v2-jump-bottom"
            onClick={() => { intent.current = "force"; scrollToBottom("smooth"); setJumpVisible(false); }}>
            ↓ 回到最新
          </button>
        )}
      </div>
    </div>
  );
}
