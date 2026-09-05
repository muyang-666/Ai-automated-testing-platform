import { useState } from "react";
import { CheckIcon, CloseIcon, SpinnerIcon } from "./ChatIcons.jsx";

const STATUS_ICON = { running: SpinnerIcon, success: CheckIcon, error: CloseIcon };

// 低干扰 inline 工具活动：只显示名称与状态；默认折叠，不渲染原始参数/日志。
export default function ToolActivity({ activity }) {
  const [open, setOpen] = useState(false);
  const status = activity.status === "error" ? "error"
    : activity.status === "running" ? "running" : "success";
  const StatusIcon = STATUS_ICON[status];
  return (
    <div className={`v2-tool ${status}`} data-status={status}>
      <button type="button" className="v2-tool-summary" onClick={() => setOpen((v) => !v)}
        aria-expanded={open}>
        <span className="v2-tool-icon"><StatusIcon /></span>
        <span className="v2-tool-name">{activity.toolName}</span>
        {status === "running" ? <span className="v2-tool-status">使用中…</span> : null}
        {status === "success" ? <span className="v2-tool-status">完成</span> : null}
        {status === "error" ? <span className="v2-tool-status">失败</span> : null}
      </button>
      {open && (
        <div className="v2-tool-details">
          {activity.errorCode ? <span>error: {activity.errorCode}</span> : null}
        </div>
      )}
    </div>
  );
}
