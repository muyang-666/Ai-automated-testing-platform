import { Button, Tooltip, message as toast } from "antd";
import { useEffect, useRef, useState } from "react";
import useAgentSession from "./useAgentSession";
import AgentArtifactPanel from "./AgentArtifactPanel";
import AgentConversation from "./AgentConversation";
import AgentGateCard from "./AgentGateCard";
import AgentRunTimeline from "./AgentRunTimeline";
import "./testAgent.css";

const STORAGE_KEY = "testmind:agent_widget";
const WELCOME = { id: "welcome", role: "assistant", content: "你好，我是 TestMind Agent。从需求或接口文档点击“交给 Agent”，我会与你确认范围、规划覆盖并生成可审核的候选用例。" };
const STATUS = { queued: "等待 Worker 执行", running: "Agent 正在工作", waiting_approval: "需要你的确认", succeeded: "用例已保存", failed: "任务失败", cancelled: "任务已取消", interrupted: "任务中断" };

function fit(size, position) {
  const width = Math.min(Math.max(size.width, 380), window.innerWidth - 24);
  const height = Math.min(Math.max(size.height, 460), window.innerHeight - 24);
  return {
    width, height,
    left: Math.max(12, Math.min(position?.left ?? window.innerWidth - width - 24, window.innerWidth - width - 12)),
    top: Math.max(12, Math.min(position?.top ?? window.innerHeight - height - 24, window.innerHeight - height - 12)),
  };
}

function readLayout() {
  let stored = {};
  try { stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}"); } catch { /* use defaults */ }
  const size = stored.size || { width: 460, height: 660 };
  if (!Number.isFinite(size.width) || !Number.isFinite(size.height)) return { ...fit({ width: 460, height: 660 }), minimized: true };
  return { ...fit(size, stored.position), minimized: stored.minimized ?? true };
}

function SparkIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.8c.5 4.8 2.5 6.8 7.2 7.2-4.7.5-6.7 2.5-7.2 7.2-.5-4.7-2.5-6.7-7.2-7.2 4.7-.4 6.7-2.4 7.2-7.2Z" /><path d="M18.4 15.5c.2 2.1 1.1 3 3.2 3.2-2.1.2-3 1.1-3.2 3.2-.2-2.1-1.1-3-3.2-3.2 2.1-.2 3-1.1 3.2-3.2Z" /></svg>;
}

export default function TestAgentWidget({ currentUser }) {
  const [layout, setLayout] = useState(readLayout);
  const [maximized, setMaximized] = useState(false);
  const [artifactPreference, setArtifactPreference] = useState(null);
  const [showHistory, setShowHistory] = useState(false);
  const [draft, setDraft] = useState("");
  const [selection, setSelection] = useState({ artifactId: null, ids: [] });
  const panelRef = useRef(null);
  const dragRef = useRef(null);
  const model = useAgentSession(currentUser.id, !layout.minimized);
  const modelRef = useRef(model);
  useEffect(() => { modelRef.current = model; });
  const showArtifacts = artifactPreference ?? (model.artifacts.length > 0);
  const shown = fit({ width: showArtifacts ? Math.max(760, layout.width) : layout.width, height: layout.height }, layout);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      minimized: layout.minimized, position: { left: layout.left, top: layout.top },
      size: { width: layout.width, height: layout.height },
    }));
  }, [layout]);

  useEffect(() => {
    const resize = () => { if (window.innerWidth > 760) setLayout((current) => ({ ...current, ...fit(current, current) })); };
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);

  useEffect(() => {
    if (!panelRef.current || maximized || window.innerWidth <= 760) return;
    const element = panelRef.current;
    const observer = new ResizeObserver(() => {
      const bounds = element.getBoundingClientRect();
      setLayout((previous) => {
        if (Math.abs(previous.width - bounds.width) < 1 && Math.abs(previous.height - bounds.height) < 1) return previous;
        return { ...previous, ...fit({ width: Math.round(bounds.width), height: Math.round(bounds.height) }, previous) };
      });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [layout.minimized, maximized]);

  useEffect(() => {
    const open = (event) => {
      const detail = event.detail || {};
      const next = { projectId: detail.projectId, sourceType: detail.sourceType, sourceId: detail.sourceId, sourceLabel: detail.sourceLabel };
      if (!modelRef.current.newConversation(next)) {
        toast.info("当前任务仍在执行或等待审批，请先完成或停止当前任务。");
      } else {
        setDraft(detail.prompt || "请根据当前文档生成测试用例。");
        setArtifactPreference(null); setSelection({ artifactId: null, ids: [] });
      }
      setLayout((current) => ({ ...current, minimized: false }));
    };
    window.addEventListener("test-agent:open", open);
    return () => window.removeEventListener("test-agent:open", open);
  }, []);

  const dragStart = (event) => {
    if (maximized || event.button !== 0 || event.target.closest("button") || window.innerWidth <= 760) return;
    dragRef.current = { x: event.clientX, y: event.clientY, left: shown.left, top: shown.top };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const dragMove = (event) => {
    if (!dragRef.current) return;
    const drag = dragRef.current;
    setLayout((current) => ({ ...current, ...fit(current, { left: drag.left + event.clientX - drag.x, top: drag.top + event.clientY - drag.y }) }));
  };

  const newChat = () => {
    if (!model.newConversation()) return;
    setDraft(""); setArtifactPreference(null); setSelection({ artifactId: null, ids: [] });
  };
  const send = async () => { if (await model.send(draft.trim())) setDraft(""); };
  const statusText = STATUS[model.run?.status] || "准备就绪";
  const caseArtifact = model.artifacts.find((artifact) => artifact.id === model.approval?.artifact_id);
  const saved = model.run?.status === "succeeded" && model.artifacts.some((artifact) => artifact.status === "saved");
  const MODEL_RECOVERABLE_RE = /返回内容为空|连续返回空内容|无法解析为 JSON|未通过 Schema|超时|限流/i;
  const llmRecoverableHint = model.run?.status === "failed" && MODEL_RECOVERABLE_RE.test(model.run.error_message || "")
    ? "\n\n提示：这通常是模型暂时没有有效返回。可重新点击“发送”重试一次；若连续多次仍失败，请检查该来源场景绑定的模型、API Key 与配额。"
    : "";
  const notices = [...model.messages];
  if (model.run) notices.push({ id: "current-status", role: "assistant", content: `${model.run.error_message || (saved ? "选中的候选已保存。你可以前往对应的用例管理页查看。" : statusText)}${llmRecoverableHint}` });

  if (layout.minimized) return (
    <button type="button" className="test-agent-launcher" onClick={() => setLayout((current) => ({ ...current, minimized: false }))} aria-label="打开 TestMind Agent">
      <span className="test-agent-launcher-icon"><SparkIcon /></span>
      <span><strong>Test Agent</strong><small>{statusText}</small></span>
      {model.hasActiveRun && <i />}
    </button>
  );

  return (
    <section ref={panelRef} className={`test-agent-window ${maximized ? "is-maximized" : ""} ${showArtifacts ? "has-artifacts" : ""}`}
      style={maximized ? { left: 16, top: 16, width: "calc(100vw - 32px)", height: "calc(100vh - 32px)" } : shown}
      aria-label="TestMind Agent 工作台" role="region">
      <header className="test-agent-window-header" onPointerDown={dragStart} onPointerMove={dragMove}
        onPointerUp={() => { dragRef.current = null; }} onPointerCancel={() => { dragRef.current = null; }}>
        <div className="test-agent-brand"><span><SparkIcon /></span><div><strong>TestMind Agent</strong><small>{model.session ? `会话 #${model.session.id}` : "测试协作空间"}</small></div></div>
        <div className="test-agent-window-actions">
          <Tooltip title="会话历史"><Button type="text" aria-label="会话历史" onClick={() => { setShowHistory(!showHistory); model.loadHistory(); }}>◷</Button></Tooltip>
          <Tooltip title="新建对话"><Button type="text" aria-label="新建对话" disabled={model.busy || model.hasActiveRun} onClick={newChat}>＋</Button></Tooltip>
          <Tooltip title="产物面板"><Button type="text" aria-label="切换产物面板" onClick={() => setArtifactPreference(!showArtifacts)}>▦</Button></Tooltip>
          <Tooltip title={maximized ? "恢复窗口" : "最大化"}><Button type="text" aria-label={maximized ? "恢复窗口" : "最大化"} onClick={() => setMaximized(!maximized)}>{maximized ? "❐" : "□"}</Button></Tooltip>
          <Tooltip title="最小化"><Button type="text" aria-label="最小化" onClick={() => setLayout((current) => ({ ...current, minimized: true }))}>—</Button></Tooltip>
        </div>
      </header>
      {showHistory && <div className="test-agent-history">
        <select aria-label="选择历史会话" value={model.session?.id || ""} disabled={model.busy || model.hasActiveRun}
          onChange={(event) => { if (event.target.value) { model.resume(Number(event.target.value)); setArtifactPreference(null); setShowHistory(false); } }}>
          <option value="">选择历史会话</option>
          {model.history.map((item) => <option key={item.id} value={item.id}>{item.title} · #{item.id}</option>)}
        </select>
        {model.hasActiveRun && <small>请先完成或停止当前任务</small>}
      </div>}
      {model.error && <div role="alert" className="test-agent-error">{model.error}</div>}
      <div className="test-agent-workspace">
        <main className="test-agent-main">
          <div className="test-agent-runbar">
            <div><span className={`test-agent-status-dot is-${model.run?.status || "idle"}`} /><span>{statusText}</span></div>
            <div><Button type="text" size="small" onClick={model.refresh} disabled={model.busy || !model.run}>刷新</Button>
              {model.hasActiveRun && <Button type="text" size="small" danger loading={model.busy} onClick={model.cancel}>停止</Button>}</div>
          </div>
          <AgentConversation messages={[WELCOME, ...notices]} draft={draft} onDraftChange={setDraft} onSend={send}
            sending={model.busy} disabled={model.busy || model.hasActiveRun} sourceContext={model.context}>
            {model.run?.status === "queued" && <p className="test-agent-queue-hint">已进入队列。长时间未变化时请确认独立 Agent Worker 已启动。</p>}
            <AgentGateCard key={model.approval?.id || "none"} approval={model.approval} loading={model.busy}
              artifacts={model.artifacts} onResolve={model.resolve} />
            {model.run && <details className="test-agent-progress"><summary>运行轨迹 · {model.steps.length} 步</summary><AgentRunTimeline run={model.run} events={model.events} /></details>}
          </AgentConversation>
        </main>
        {showArtifacts && <AgentArtifactPanel key={`${model.run?.id}-${model.approval?.artifact_id || "none"}`} artifacts={model.artifacts} approval={model.approval}
          selectedIds={saved ? model.savedCandidateIds : selection.artifactId === caseArtifact?.id ? selection.ids : []}
          onSelectionChange={(ids) => setSelection({ artifactId: caseArtifact?.id, ids })}
          onSave={(artifact) => model.save(artifact, selection.artifactId === artifact.id ? selection.ids : [])} saving={model.busy} />}
      </div>
      {!maximized && <div className="test-agent-resize-hint" aria-hidden="true" />}
    </section>
  );
}
