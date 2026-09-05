import { useEffect, useRef, useState } from "react";
import useConversationChat, { blocksToText } from "./useConversationChat";
import { messageFailure } from "./conversationErrors.js";
import "./v2Chat.css";

const QUEUE_BADGE = { queued: "排队中", paused: "已暂停", failed: "失败",
  interrupted: "已中断", cancelled: "已取消", running: "回答中", idle: "空闲" };
const TOOL_LABELS = { calculator: "计算器" };
const DEFAULT_LAYOUT = { width: 760, height: 620 };
const MIN_SIZE = { width: 420, height: 360 };

function storageKey(userId) {
  return `testmind:v2-chat-window:${userId || "anonymous"}`;
}

function fit(size, position) {
  const maxWidth = Math.max(MIN_SIZE.width, window.innerWidth - 24);
  const maxHeight = Math.max(MIN_SIZE.height, window.innerHeight - 24);
  const width = Math.min(Math.max(size.width, MIN_SIZE.width), maxWidth);
  const height = Math.min(Math.max(size.height, MIN_SIZE.height), maxHeight);
  return {
    width,
    height,
    left: Math.max(12, Math.min(position?.left ?? window.innerWidth - width - 24,
      window.innerWidth - width - 12)),
    top: Math.max(12, Math.min(position?.top ?? window.innerHeight - height - 24,
      window.innerHeight - height - 12)),
  };
}

function fitLauncher(position) {
  return {
    left: Math.max(12, Math.min(position?.left ?? window.innerWidth - 208, window.innerWidth - 196)),
    top: Math.max(12, Math.min(position?.top ?? window.innerHeight - 76, window.innerHeight - 58)),
  };
}

function readLayout(userId) {
  let stored = {};
  try { stored = JSON.parse(localStorage.getItem(storageKey(userId)) || "{}"); } catch { /* defaults */ }
  const size = stored.size || DEFAULT_LAYOUT;
  const safeSize = Number.isFinite(size.width) && Number.isFinite(size.height) ? size : DEFAULT_LAYOUT;
  const mode = ["normal", "minimized", "maximized"].includes(stored.mode) ? stored.mode : "minimized";
  const normal = fit(safeSize, stored.position);
  const launcher = fitLauncher(stored.launcherPosition);
  return {
    ...normal, mode,
    launcherLeft: launcher.left,
    launcherTop: launcher.top,
  };
}

export default function V2ChatPanel({ currentUser }) {
  const chat = useConversationChat(currentUser?.id);
  const [draft, setDraft] = useState("");
  const [layout, setLayout] = useState(() => readLayout(currentUser?.id));
  const panelRef = useRef(null);
  const dragRef = useRef(null);
  const launcherDragRef = useRef(null);
  const suppressLauncherClick = useRef(false);
  const canSend = !chat.busy && !!chat.active && chat.phase !== "paused"
    && chat.capabilities?.model_ready !== false;
  const shown = fit(layout, layout);

  useEffect(() => {
    localStorage.setItem(storageKey(currentUser?.id), JSON.stringify({
      mode: layout.mode,
      position: { left: layout.left, top: layout.top },
      launcherPosition: { left: layout.launcherLeft, top: layout.launcherTop },
      size: { width: layout.width, height: layout.height },
    }));
  }, [currentUser?.id, layout]);

  useEffect(() => {
    const keepVisible = () => setLayout((current) => {
      const launcher = fitLauncher({ left: current.launcherLeft, top: current.launcherTop });
      return {
        ...current, ...fit(current, current),
        launcherLeft: launcher.left, launcherTop: launcher.top,
      };
    });
    window.addEventListener("resize", keepVisible);
    return () => window.removeEventListener("resize", keepVisible);
  }, []);

  useEffect(() => {
    if (!panelRef.current || layout.mode !== "normal") return undefined;
    const observer = new ResizeObserver(() => {
      const bounds = panelRef.current?.getBoundingClientRect();
      if (!bounds) return;
      setLayout((current) => {
        if (Math.abs(current.width - bounds.width) < 1 && Math.abs(current.height - bounds.height) < 1) {
          return current;
        }
        return { ...current, ...fit(
          { width: Math.round(bounds.width), height: Math.round(bounds.height) }, current,
        ) };
      });
    });
    observer.observe(panelRef.current);
    return () => observer.disconnect();
  }, [layout.mode]);

  const dragStart = (event) => {
    if (layout.mode !== "normal" || event.button !== 0 || event.target.closest("button")) return;
    dragRef.current = { x: event.clientX, y: event.clientY, left: shown.left, top: shown.top };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const dragMove = (event) => {
    if (!dragRef.current) return;
    const drag = dragRef.current;
    setLayout((current) => ({ ...current, ...fit(current, {
      left: drag.left + event.clientX - drag.x,
      top: drag.top + event.clientY - drag.y,
    }) }));
  };

  const launcherDragStart = (event) => {
    if (event.button !== 0) return;
    launcherDragRef.current = {
      x: event.clientX, y: event.clientY,
      left: layout.launcherLeft, top: layout.launcherTop, moved: false,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const launcherDragMove = (event) => {
    const drag = launcherDragRef.current;
    if (!drag) return;
    const dx = event.clientX - drag.x;
    const dy = event.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 4) drag.moved = true;
    const next = fitLauncher({ left: drag.left + dx, top: drag.top + dy });
    setLayout((current) => ({
      ...current, launcherLeft: next.left, launcherTop: next.top,
    }));
  };

  const launcherDragEnd = () => {
    suppressLauncherClick.current = Boolean(launcherDragRef.current?.moved);
    launcherDragRef.current = null;
  };

  const submit = () => {
    const text = draft.trim();
    if (!text || !canSend) return;
    chat.send(text);
    setDraft("");
  };

  if (layout.mode === "minimized") {
    return (
      <button type="button" className="v2chat-launcher"
        style={{ left: layout.launcherLeft, top: layout.launcherTop }}
        onPointerDown={launcherDragStart} onPointerMove={launcherDragMove}
        onPointerUp={launcherDragEnd} onPointerCancel={launcherDragEnd}
        onClick={() => {
          if (suppressLauncherClick.current) { suppressLauncherClick.current = false; return; }
          setLayout((current) => ({ ...current, mode: "normal", ...fit(current, current) }));
        }}>
        <span className="v2chat-launcher-mark">AI</span>
        <span><strong>TestMind Agent</strong><small>{chat.STATE_LABELS[chat.phase] || "打开对话"}</small></span>
      </button>
    );
  }

  const panelStyle = layout.mode === "maximized"
    ? { left: 12, top: 12, width: "calc(100vw - 24px)", height: "calc(100vh - 24px)" }
    : shown;

  return (
    <section ref={panelRef}
      className={`v2chat-window ${layout.mode === "maximized" ? "is-maximized" : ""}`}
      style={panelStyle} role="region" aria-label="TestMind Agent 对话浮窗">
      <header className="v2chat-window-header" onPointerDown={dragStart} onPointerMove={dragMove}
        onPointerUp={() => { dragRef.current = null; }} onPointerCancel={() => { dragRef.current = null; }}>
        <div className="v2chat-brand">
          <span className="v2chat-brand-mark">AI</span>
          <div><strong>TestMind Agent</strong><small>{chat.STATE_LABELS[chat.phase] || "对话协作空间"}</small></div>
        </div>
        <div className="v2chat-window-actions">
          <button type="button" aria-label={layout.mode === "maximized" ? "恢复窗口" : "最大化"}
            title={layout.mode === "maximized" ? "恢复窗口" : "最大化"}
            onClick={() => setLayout((current) => ({
              ...current, mode: current.mode === "maximized" ? "normal" : "maximized",
            }))}>{layout.mode === "maximized" ? "❐" : "□"}</button>
          <button type="button" aria-label="最小化" title="最小化"
            onClick={() => {
              const launcher = fitLauncher();
              setLayout((current) => ({
                ...current, mode: "minimized",
                launcherLeft: launcher.left, launcherTop: launcher.top,
              }));
            }}>—</button>
        </div>
      </header>
      <div className="v2chat">
      <aside className="v2chat-side">
        <button className="v2chat-new" onClick={chat.newConversation} disabled={chat.busy}>＋ 新对话</button>
        <ul className="v2chat-list">
          {chat.conversations.map((c) => (
            <li key={c.id}
                className={chat.active?.id === c.id ? "v2chat-item active" : "v2chat-item"}
                onClick={() => chat.openConversation(c)}>
              {c.title}
            </li>
          ))}
        </ul>
      </aside>
      <main className="v2chat-main">
        <header className="v2chat-header">
          <span>{chat.active?.title || "V2 对话式 Test Agent"}</span>
          <span className="v2chat-status">
            {chat.snapshot ? `状态：${QUEUE_BADGE[chat.phase] || chat.phase}` : ""}
            {chat.capabilities?.tools?.length
              ? ` · 可用工具：${chat.capabilities.tools.map((name) => TOOL_LABELS[name] || name).join("、")}` : ""}
          </span>
        </header>
        {chat.error && <div className="v2chat-error">{chat.error}</div>}
        {chat.capabilities?.model_ready === false && (
          <div className="v2chat-config-warning">尚未配置 Agent 对话模型，请先前往“模型管理”完成绑定。</div>
        )}
        {chat.runError && chat.capabilities?.model_ready !== false
          && <div className="v2chat-error">{chat.runError}</div>}
        {chat.phase === "paused" && (
          <div className="v2chat-paused">上一轮失败/中断，后续消息已暂停（请新建对话或等待后续版本恢复）。</div>
        )}
        <div className="v2chat-messages">
          {chat.messages.map((m) => (
            <div key={m.id || m.sequence_no} className={`v2chat-msg role-${m.role}`}>
              <div className="v2chat-msg-label">{m.role === "user" ? "你" : m.role === "assistant" ? "AI" : "工具"}</div>
              <div className="v2chat-msg-body">
                {messageFailure(m) && <div className="v2chat-message-error" role="status">{messageFailure(m)}</div>}
                {m.role === "user" ? blocksToText(m.content)
                  : m.role === "assistant"
                    ? blocksToText(m.content).split("\n").map((line, i) => <div key={i}>{line}</div>)
                    : `结果：${blocksToText(m.content)}`}
              </div>
            </div>
          ))}
          {chat.streaming && (
            <div className="v2chat-msg role-assistant">
              <div className="v2chat-msg-label">AI</div>
              <div className="v2chat-msg-body v2chat-streaming">{chat.streaming}</div>
            </div>
          )}
          {chat.activity.map((a) => (
            <div key={a.id} className="v2chat-activity">{a.text}</div>
          ))}
        </div>
        <footer className="v2chat-footer">
          {(chat.phase === "running" || chat.phase === "queued") && (
            <button className="v2chat-stop" onClick={chat.cancel}>Stop</button>
          )}
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } }}
            placeholder={chat.phase === "paused" ? "队列已暂停" : "输入消息…（支持回答中继续发送，自动排队）"}
            disabled={!canSend}
          />
          <button className="v2chat-send" onClick={submit} disabled={!canSend}>发送</button>
        </footer>
      </main>
      </div>
    </section>
  );
}
