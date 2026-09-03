const EVENT_LABELS = {
  skill_selected: "已选择用例生成 Skill",
  phase_started: "开始执行阶段",
  tool_requested: "正在调用测试工具",
  tool_completed: "测试工具执行完成",
  tool_failed: "测试工具执行失败",
  artifact_created: "已生成结构化产物",
  approval_required: "等待你的确认",
  approval_resolved: "确认已提交",
  phase_completed: "阶段已完成",
  cases_saved: "候选用例已保存",
  scope_gate_requested: "等待确认生成范围",
  scope_gate_approved: "生成范围已确认",
  coverage_gate_requested: "等待确认覆盖计划",
  coverage_gate_approved: "覆盖计划已确认",
  save_gate_requested: "候选已生成，等待勾选保存",
  approval_approved: "审批通过，已重新排队",
  approval_rejected: "审批已拒绝",
  candidates_validated: "候选校验完成",
  candidates_deduplicated: "候选去重完成",
  run_cancelled: "任务已取消",
  step_started: "开始执行步骤",
  step_completed: "步骤执行完成",
  user_rejected: "你已结束本次任务",
  session_failed: "任务执行失败",
};

const STATUS_LABELS = {
  queued: "等待执行",
  running: "正在工作",
  waiting_approval: "等待确认",
  succeeded: "已完成",
  failed: "执行失败",
  cancelled: "已取消",
  interrupted: "执行中断",
};

function getEventLabel(event) {
  return (
    event?.display_text ||
    event?.message ||
    event?.payload_json?.message ||
    EVENT_LABELS[event?.event_type] ||
    event?.event_type ||
    "Agent 状态更新"
  );
}

export default function AgentRunTimeline({ run, events = [] }) {
  const currentStatus = run?.status || "idle";
  const visibleEvents = events.slice(-8);

  return (
    <section className="test-agent-timeline" aria-label="Agent 执行进度">
      <div className="test-agent-timeline-head">
        <span className={`test-agent-status-dot is-${currentStatus}`} />
        <strong>{STATUS_LABELS[currentStatus] || "准备就绪"}</strong>
        {run?.current_step && <span>{run.current_step}</span>}
      </div>

      {visibleEvents.length > 0 ? (
        <ol>
          {visibleEvents.map((event, index) => (
            <li key={event.id || `${event.event_type}-${index}`}>
              <span className="test-agent-timeline-marker" />
              <div>
                <p>{getEventLabel(event)}</p>
                {(event.created_at || event.timestamp) && (
                  <time>
                    {new Date(event.created_at || event.timestamp).toLocaleTimeString("zh-CN", {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </time>
                )}
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p className="test-agent-timeline-empty">任务启动后，这里会显示 Agent 的工作步骤。</p>
      )}
    </section>
  );
}
