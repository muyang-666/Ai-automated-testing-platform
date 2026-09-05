import { useEffect, useRef } from "react";
import { ArrowUpIcon, StopIcon } from "./ChatIcons.jsx";

// Composer：多行自动增长；Enter 发送 / Shift+Enter 换行；
// Running 时仍允许发送（follow-up 自动排队）；Stop 独立按钮。
export default function ChatComposer({
  value, onChange, onSubmit, onStop, disabled, stopping, placeholder, focusKey,
}) {
  const textareaRef = useRef(null);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [value]);

  useEffect(() => {
    if (disabled) return undefined;
    const frame = requestAnimationFrame(() => {
      textareaRef.current?.focus({ preventScroll: true });
    });
    return () => cancelAnimationFrame(frame);
  }, [disabled, focusKey]);

  const handleKeyDown = (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      if (!disabled) onSubmit();
    }
  };

  return (
    <div className="v2-composer">
      <textarea
        ref={textareaRef}
        rows={1}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder || "Ask TestMind"}
        disabled={disabled}
      />
      {stopping ? (
        <button type="button" className="v2-stop" onClick={onStop}>
          <StopIcon /><span>停止</span>
        </button>
      ) : null}
      <button type="button" className="v2-send" onClick={onSubmit} disabled={disabled}
        aria-label="发送" title="发送（Enter）">
        <ArrowUpIcon />
      </button>
    </div>
  );
}
