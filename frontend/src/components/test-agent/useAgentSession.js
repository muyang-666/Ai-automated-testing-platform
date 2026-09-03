import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "../../api/agent";
import { ACTIVE_STATUSES, currentApproval, errorText, listData, sessionStartErrorText } from "./agentContract";

const keyFor = (userId) => `testmind:agent:last-session:${userId}`;
const uid = () => crypto.randomUUID();

export default function useAgentSession(userId, opened) {
  const [session, setSession] = useState(null);
  const [history, setHistory] = useState([]);
  const [context, setContext] = useState(null);
  const [messages, setMessages] = useState([]);
  const [run, setRun] = useState(null);
  const [events, setEvents] = useState([]);
  const [steps, setSteps] = useState([]);
  const [artifacts, setArtifacts] = useState([]);
  const [approvals, setApprovals] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [syncError, setSyncError] = useState("");
  const epoch = useRef(0);
  const timer = useRef(null);
  const mounted = useRef(false);
  const initialized = useRef(false);
  const pending = useRef(null);
  const locking = useRef(false);
  const boundSession = useRef(null);
  const hasActiveRun = !!run && (ACTIVE_STATUSES.has(run.status) || run.status === "waiting_approval");

  const invalidate = useCallback(() => {
    epoch.current += 1;
    clearTimeout(timer.current);
    return epoch.current;
  }, []);

  const snapshot = useCallback(async (runId, sessionId, generation) => {
    const [next, ev, st, ar, ap] = await Promise.all([
      api.getAgentRun(runId), api.getAgentEvents(sessionId, { limit: 500 }),
      api.getAgentRunSteps(runId, { limit: 500 }), api.getAgentRunArtifacts(runId), api.getAgentRunApprovals(runId),
    ]);
    if (!mounted.current || epoch.current !== generation) return null;
    setRun(next.data);
    setEvents(listData(ev, "events").filter((item) => item.run_id === runId));
    setSteps(listData(st, "steps"));
    setArtifacts(listData(ar, "artifacts"));
    setApprovals(listData(ap, "approvals"));
    setSyncError("");
    return next.data;
  }, []);

  const watch = useCallback((runId, sessionId, generation) => {
    let failures = 0;
    const poll = async () => {
      if (!mounted.current || epoch.current !== generation) return;
      try {
        const value = await snapshot(runId, sessionId, generation);
        failures = 0;
        if (value && ACTIVE_STATUSES.has(value.status)) timer.current = setTimeout(poll, 1500);
      } catch (err) {
        if (!mounted.current || epoch.current !== generation) return;
        setSyncError(`状态同步失败：${errorText(err)}。可点击刷新重试。`);
        failures += 1;
        if (failures < 3) timer.current = setTimeout(poll, 2500);
      }
    };
    poll();
  }, [snapshot]);

  const resume = useCallback(async (sessionId) => {
    const generation = invalidate();
    setBusy(true);
    locking.current = true;
    setError("");
    try {
      const [detail, runs] = await Promise.all([api.getAgentSession(sessionId), api.getAgentSessionRuns(sessionId)]);
      if (!mounted.current || epoch.current !== generation) return;
      const value = detail.data;
      setSession(value);
      boundSession.current = value;
      setMessages(value.messages || []);
      const latest = listData(runs, "runs")[0];
      const input = latest?.input_json || value.context_json || {};
      setContext(input.source_id ? {
        sourceType: input.source_type, sourceId: input.source_id,
        projectId: value.project_id, sourceLabel: value.context_json?.source_label || `来源 #${input.source_id}`,
      } : null);
      setRun(latest || null);
      setArtifacts([]); setApprovals([]); setEvents([]); setSteps([]);
      localStorage.setItem(keyFor(userId), String(value.id));
      if (latest) watch(latest.id, value.id, generation);
    } catch (err) {
      if (epoch.current === generation) setError(`恢复会话失败：${errorText(err)}`);
    } finally {
      if (epoch.current === generation) { setBusy(false); locking.current = false; }
    }
  }, [invalidate, userId, watch]);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; initialized.current = false; invalidate(); };
  }, [invalidate]);

  useEffect(() => {
    if (!opened || initialized.current) return;
    initialized.current = true;
    const savedId = Number(localStorage.getItem(keyFor(userId)));
    if (savedId > 0) resume(savedId);
  }, [opened, resume, userId]);

  const newConversation = useCallback((nextContext = null) => {
    if (locking.current || hasActiveRun) return false;
    invalidate(); initialized.current = true; pending.current = null; boundSession.current = null;
    setSession(null); setContext(nextContext); setMessages([]); setRun(null);
    setEvents([]); setSteps([]); setArtifacts([]); setApprovals([]); setError(""); setSyncError("");
    localStorage.removeItem(keyFor(userId));
    return true;
  }, [hasActiveRun, invalidate, userId]);

  const send = async (content) => {
    if (locking.current || hasActiveRun) return false;
    if (!context?.sourceId || !context?.projectId) {
      setError("请先从需求管理或接口文档选择“交给 Agent”，为本次任务指定来源。");
      return false;
    }
    if (content.length > 500) { setError("本次测试目标最多 500 字。"); return false; }
    locking.current = true; setBusy(true); setError("");
    const generation = invalidate();
    if (!pending.current || pending.current.content !== content) pending.current = { content, key: uid(), messageSaved: false };
    const submission = pending.current;
    try {
      let value = boundSession.current || session;
      if (!value) {
        try {
          value = (await api.createAgentSession({
            project_id: context.projectId,
            title: `${context.sourceLabel || "用例生成"} · Agent`.slice(0, 200),
            context_json: { source_type: context.sourceType, source_id: context.sourceId, source_label: context.sourceLabel },
          })).data;
        } catch (err) {
          if (epoch.current === generation) {
            const status = err?.response?.status;
            if (status >= 400 && status < 500) {
              // 项目/来源已失效、被删除或无权限：清掉本次来源上下文，回到重新选择来源的空状态，
              // 不残留指向无效会话的本地记录，也不继续创建 Message/Run。
              boundSession.current = null;
              pending.current = null;
              setContext(null);
              setMessages([]);
            }
            setError(sessionStartErrorText(err));
          }
          return false;
        }
        boundSession.current = value;
        setSession(value);
        localStorage.setItem(keyFor(userId), String(value.id));
      }
      if (!submission.messageSaved) {
        const stored = (await api.appendAgentMessage(value.id, { content })).data;
        submission.messageSaved = true;
        setMessages((items) => [...items, stored]);
      }
      const created = (await api.createAgentRun(value.id, {
        input: { source_type: context.sourceType, source_id: context.sourceId,
          case_types: ["正常场景", "异常场景", "边界场景", "业务规则场景"], max_cases: 30, user_goal: content },
        idempotency_key: submission.key,
      })).data;
      if (epoch.current !== generation) return false;
      setRun(created); pending.current = null;
      watch(created.id, value.id, generation);
      return true;
    } catch (err) {
      if (epoch.current === generation) setError(errorText(err));
      return false;
    } finally {
      if (epoch.current === generation) { setBusy(false); locking.current = false; }
    }
  };

  const act = async (operation) => {
    if (locking.current || !run || !session) return;
    locking.current = true; setBusy(true); setError("");
    const generation = invalidate();
    try {
      await operation();
    } catch (err) {
      if (epoch.current === generation) setError(errorText(err));
    } finally {
      if (epoch.current === generation) {
        setBusy(false); locking.current = false;
        // 即使请求结果不确定，也先读取服务端状态，不重复执行写操作。
        watch(run.id, session.id, generation);
      }
    }
  };

  const approval = currentApproval(run, approvals);
  return {
    session, history, context, messages, run, events, steps, artifacts, approval, busy, error: error || syncError, hasActiveRun,
    savedCandidateIds: approvals.find((item) => item.action_code === "save_generated_case_candidates" && item.status === "approved")?.resolution_json?.candidate_ids || [],
    newConversation, send,
    refresh: () => { if (run && session) watch(run.id, session.id, invalidate()); },
    resolve: (decision, resolution) => act(() => api.resolveAgentApproval(approval.id, { decision, resolution })),
    cancel: () => act(() => api.cancelAgentRun(run.id)),
    save: (artifact, candidateIds) => {
      if (artifact.id !== approval?.artifact_id) { setError("当前产物不是待审批的用例版本，请刷新后重试。"); return; }
      return act(() => api.saveAgentCandidates(run.id, { candidate_ids: candidateIds }));
    },
    loadHistory: async () => {
      try { setHistory(listData(await api.getAgentSessions(), "sessions")); }
      catch (err) { setError(errorText(err)); }
    },
    resume: (id) => { if (!locking.current && !hasActiveRun) { pending.current = null; resume(id); } },
  };
}
