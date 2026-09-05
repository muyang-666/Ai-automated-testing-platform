import { useEffect, useRef, useState } from "react";
import ChatTurn from "./ChatTurn.jsx";
import { isNearBottom, shouldAutoScroll } from "./scrollPolicy.js";

const SCROLL_THRESHOLD = 80;

// 消息时间轴：维护 isNearBottom，按场景自动滚动（打开/发送强制到底；
// 流式仅在近底部跟随；用户上滚时显示"回到最新"，绝不强制拉回）。
export default function ChatTimeline({ turns, streaming, activeId, sendNonce }) {
  const containerRef = useRef(null);
  const intent = useRef(null); // "force" | "follow"
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

  const openedOnce = useRef(new Set());
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return undefined;
    el.addEventListener("scroll", updatePosition, { passive: true });
    updatePosition();
    // 首次打开/切换会话：强制定位到底部（不打扰用户主动查看历史）。
    if (!openedOnce.current.has(activeId)) {
      openedOnce.current.add(activeId);
      requestAnimationFrame(() => {
        scrollToBottom();
        setNearBottom(true);
        setJumpVisible(false);
      });
    }
    return () => el.removeEventListener("scroll", updatePosition);
  }, [activeId]);

  // 切换/打开/自己发送：强制到底；流式：近底部才跟随。
  // 状态更新放在 requestAnimationFrame 内，避免 effect 内同步 setState。
  useEffect(() => {
    if (!containerRef.current) return;
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
