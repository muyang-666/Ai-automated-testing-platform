// P09.1 Artifact Workspace Store（数据状态；独立于 useConversationChat）。
//
// - artifacts / activeArtifact / tree / currentRevision / loading / error 集中在此；
// - Conversation → Artifact Focus 以服务端为准：focus 走 POST focus API，成功后才更新本地；
//   409 时保留旧 Artifact 与旧 MindMap（无乐观切换）；
// - Conversation/Artifact 快速切换用 request 序号 + 会话 id 裁决 late response，不覆盖当前。
import { useCallback, useEffect, useRef, useState } from "react";
import * as artifactApi from "../../../api/testArtifact";
import { focusConversationArtifact } from "../../v2-chat/conversationApi";
import {
  focusFailureMessage, isTreeLoadStale, shouldApplyResponse,
} from "../artifactWorkspaceModel";

export default function useArtifactWorkspace({
  conversationId, // 真实会话 id（local draft 会话传 null）
  focusedArtifactId, // conversation snapshot.focused_artifact_id（顶层）
  conversationProjectId,
  onConversationRefresh, // focus 成功后刷新会话快照（服务端为 Source of Truth）
}) {
  const [artifacts, setArtifacts] = useState(null);
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState(null);
  const [activeArtifact, setActiveArtifact] = useState(null); // TestArtifact summary
  const [tree, setTree] = useState(null); // {artifact_id,current_revision,root}
  const [treeLoading, setTreeLoading] = useState(false);
  const [treeError, setTreeError] = useState(null);
  const [unavailable, setUnavailable] = useState(false); // focused 404：不无限 retry
  const [focusError, setFocusError] = useState(null);
  const [busy, setBusy] = useState(false); // create 等操作锁
  const [treeNonce, setTreeNonce] = useState(0); // 成功加载树后 +1（fit view 触发点）

  const conversationToken = useRef(0);
  const treeSeq = useRef(0);
  const activeRef = useRef(null); // activeArtifact.id
  const treeLoadedRef = useRef(false);

  const active = conversationId == null ? null : activeArtifact;

  // 加载单个 Artifact 的摘要 + 树（序号裁决 A→B→C late response）
  const loadActive = useCallback(async (artifact, { fromFocus = false } = {}) => {
    if (!conversationId || !artifact?.id) return false;
    const seq = ++treeSeq.current;
    setTreeLoading(true);
    setTreeError(null);
    setUnavailable(false);
    if (!fromFocus) setFocusError(null);
    try {
      const [meta, treeResponse] = await Promise.all([
        artifactApi.getArtifact(artifact.id),
        artifactApi.getArtifactTree(artifact.id),
      ]);
      if (isTreeLoadStale({
        requestKey: conversationId, currentKey: conversationId,
        requestSeq: seq, currentSeq: treeSeq.current,
      })) return false;
      if (conversationToken.current === 0) return false;
      setActiveArtifact(meta.data);
      setTree(treeResponse.data);
      activeRef.current = meta.data.id;
      treeLoadedRef.current = true;
      setTreeNonce((n) => n + 1);
      return true;
    } catch (err) {
      if (isTreeLoadStale({
        requestKey: conversationId, currentKey: conversationId,
        requestSeq: seq, currentSeq: treeSeq.current,
      })) return false;
      if (conversationToken.current === 0) return false;
      if (err?.response?.status === 404) {
        // focused Artifact 已删除/不可访问：清展示、不无限 retry
        setActiveArtifact(null);
        setTree(null);
        activeRef.current = null;
        treeLoadedRef.current = false;
        setUnavailable(true);
      } else {
        setTreeError(String(err?.response?.data?.detail || err?.message || "加载失败"));
      }
      return false;
    } finally {
      if (seq === treeSeq.current) setTreeLoading(false);
    }
  }, [conversationId]);

  const resetForConversation = useCallback(() => {
    conversationToken.current += 1;
    treeSeq.current += 1;
    activeRef.current = null;
    treeLoadedRef.current = false;
    setActiveArtifact(null);
    setTree(null);
    setTreeLoading(false);
    setTreeError(null);
    setUnavailable(false);
    setFocusError(null);
  }, []);

  // 会话切换：清空旧树 → 骨架屏（不闪旧数据）→ 拉列表 + 按 focused 加载
  useEffect(() => {
    resetForConversation();
    if (!conversationId) {
      setArtifacts(null);
      return undefined;
    }
    const token = conversationToken.current; // 本次会话的稳定代次
    setListLoading(true);
    void (async () => {
      try {
        const response = await artifactApi.listArtifacts();
        if (conversationToken.current === token) {
          setArtifacts(response.data);
        }
      } catch (err) {
        if (conversationToken.current === token) {
          setListError(String(err?.response?.data?.detail || err?.message || "加载列表失败"));
        }
      } finally {
        if (conversationToken.current === token) setListLoading(false);
      }
    })();
    return undefined;
  }, [conversationId, resetForConversation]);

  // focused（来自后端 snapshot）变化 → 加载该 Artifact；已加载同 id 则跳过
  useEffect(() => {
    if (!conversationId || focusedArtifactId == null) return;
    if (activeRef.current === focusedArtifactId && treeLoadedRef.current) return;
    const candidate = artifacts?.find((item) => item.id === focusedArtifactId);
    if (candidate || artifacts === null) {
      void loadActive(candidate || { id: focusedArtifactId });
    }
  }, [conversationId, focusedArtifactId, artifacts, loadActive]);

  // focused 清空（未绑定 Artifact）→ 右侧 Empty State
  useEffect(() => {
    if (!conversationId) return;
    if (focusedArtifactId == null) {
      activeRef.current = null;
      treeLoadedRef.current = false;
      setActiveArtifact(null);
      setTree(null);
      setUnavailable(false);
      setTreeError(null);
    }
  }, [conversationId, focusedArtifactId]);

  const focusArtifact = useCallback(async (artifact) => {
    if (!conversationId || !artifact?.id) return;
    const token = conversationToken.current;
    setFocusError(null);
    try {
      await focusConversationArtifact(conversationId, artifact.id);
      if (!shouldApplyResponse({
        requestConversationId: conversationId, currentConversationId: conversationId,
        requestToken: token, currentToken: conversationToken.current,
      })) return false;
      const loaded = await loadActive(artifact, { fromFocus: true });
      if (loaded) {
        onConversationRefresh?.(); // 服务端已持久化；刷新快照让刷新/F5 一致
      }
      return loaded;
    } catch (err) {
      if (!shouldApplyResponse({
        requestConversationId: conversationId, currentConversationId: conversationId,
        requestToken: token, currentToken: conversationToken.current,
      })) return false;
      // 保持旧 Artifact/MindMap；只显示错误（409 guard 消息等）
      setFocusError(focusFailureMessage({
        httpStatus: err?.response?.status, detail: err?.response?.data?.detail,
      }));
      return false;
    }
  }, [conversationId, loadActive, onConversationRefresh]);

  const createArtifact = useCallback(async (title) => {
    if (!conversationId || !title?.trim()) return null;
    setBusy(true);
    setFocusError(null);
    try {
      const created = await artifactApi.createArtifact({
        title: title.trim(),
        project_id: conversationProjectId ?? null,
      });
      const artifact = created.data;
      const list = await artifactApi.listArtifacts();
      if (conversationToken.current !== 0) {
        setArtifacts(list.data);
      }
      await focusArtifact(artifact); // 创建成功 → 自动 focus → 读 tree → 显示 root
      return artifact;
    } catch (err) {
      setFocusError(String(err?.response?.data?.detail || err?.message || "创建失败"));
      return null;
    } finally {
      setBusy(false);
    }
  }, [conversationId, conversationProjectId, focusArtifact]);

  const reloadActive = useCallback(async () => {
    const current = activeRef.current;
    if (!conversationId || current == null) return false;
    return loadActive({ id: current }); // 手动刷新（GET artifact + GET tree）
  }, [conversationId, loadActive]);

  return {
    artifacts, listLoading, listError,
    active: active ? { ...active, tree } : null,
    tree,
    currentRevision: tree?.current_revision ?? activeArtifact?.current_revision ?? null,
    treeLoading, treeError, unavailable, focusError, busy, treeNonce,
    focusArtifact, createArtifact, reloadActive,
  };
}
