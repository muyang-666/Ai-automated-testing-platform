// 独立开发入口；不被 App 或生产 index.html 引用，不改变生产鉴权。
import React from "react";
import { createRoot } from "react-dom/client";
import { Button } from "antd";
import TestAgentWidget from "../components/test-agent/TestAgentWidget";
import "antd/dist/reset.css";

export default function FixturePage() {
  const [info, setInfo] = React.useState(null);
  const refresh = () => fetch("http://127.0.0.1:8011/fixture/info").then((response) => response.json()).then(setInfo);
  const open = (sourceType, sourceId = 1) => window.dispatchEvent(new CustomEvent("test-agent:open", { detail: {
    projectId: 1, sourceType, sourceId,
    sourceLabel: sourceType === "requirement" ? "联调登录需求" : "联调登录接口",
    prompt: "请根据当前登录文档生成测试用例。",
  } }));
  return <div style={{ minHeight: "100vh", background: "#eef0f3", padding: 32, fontFamily: "sans-serif" }}>
    <h1>TestMind 前后端隔离联调</h1><p>临时 SQLite · Fake LLM · 真实 Agent API / Runtime / Worker · 仅开发入口</p>
    <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
      <Button onClick={() => open("requirement")}>需求用例生成</Button>
      <Button onClick={() => open("api_document")}>接口用例生成</Button>
      <Button onClick={() => open("requirement", 2)}>来源变更测试</Button>
      <Button onClick={refresh}>查询真实保存结果</Button>
      <Button onClick={() => fetch("http://127.0.0.1:8011/fixture/change-source", { method: "POST" }).then(refresh)}>修改隔离需求</Button>
    </div>
    {info && <pre style={{ whiteSpace: "pre-wrap" }} aria-label="真实数据库保存结果">{JSON.stringify(info, null, 2)}</pre>}
    <TestAgentWidget currentUser={{ id: "fixture", username: "fixture" }} />
  </div>;
}

if (import.meta.env.DEV && import.meta.env.VITE_API_BASE_URL === "http://127.0.0.1:8011") {
  createRoot(document.getElementById("root")).render(<React.StrictMode><FixturePage /></React.StrictMode>);
} else {
  document.getElementById("root").textContent = "仅允许使用指定的隔离联调服务。";
}
