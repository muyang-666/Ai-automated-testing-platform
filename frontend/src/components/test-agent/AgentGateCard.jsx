import { Button, Checkbox, Input, InputNumber, Space, Tag } from "antd";
import { useState } from "react";

const TYPES = ["正常场景", "异常场景", "边界场景", "业务规则场景", "其他"];
const META = {
  confirm_case_generation_scope: ["范围确认", "确认本次用例生成范围", "确认并继续"],
  confirm_case_coverage_plan: ["覆盖计划", "确认测试覆盖计划", "确认覆盖计划"],
  save_generated_case_candidates: ["保存审批", "勾选候选后保存到用例管理", ""],
};

export default function AgentGateCard({ approval, loading, artifacts = [], onResolve }) {
  const request = approval?.request_json || {};
  const [types, setTypes] = useState(request.case_types || []);
  const [maxCases, setMaxCases] = useState(request.max_cases || 30);
  const [goal, setGoal] = useState(request.user_goal || "");
  const plan = artifacts.find((item) => item.id === approval?.artifact_id)?.payload_json?.coverage_plan || [];
  const [excluded, setExcluded] = useState([]);
  if (!approval || approval.status !== "pending") return null;
  const [eyebrow, title, label] = META[approval.action_code] || ["需要确认", approval.action_code, "确认"];
  const isScope = approval.action_code === "confirm_case_generation_scope";
  const isCoverage = approval.action_code === "confirm_case_coverage_plan";
  const isSave = approval.action_code === "save_generated_case_candidates";
  const valid = isScope ? types.length > 0 && maxCases >= 1 && maxCases <= 50 : !isCoverage || plan.length > excluded.length;
  const approve = () => onResolve("approved", isScope
    ? { approved: true, case_types: types, max_cases: maxCases, user_goal: goal }
    : isCoverage ? { approved: true, coverage_plan: plan.filter((_, index) => !excluded.includes(index)) } : { approved: true });

  return (
    <section className="test-agent-gate-card">
      <div className="test-agent-gate-eyebrow"><span>{eyebrow}</span><Tag color="gold">GATE</Tag></div>
      <h4>{title}</h4>
      {isScope && <div className="test-agent-gate-fields">
        <p>来源：{request.source?.title_or_name || `#${request.source?.id || ""}`}</p>
        <Checkbox.Group value={types} options={TYPES} onChange={setTypes} disabled={loading} />
        <label>最大候选数 <InputNumber aria-label="最大候选数" min={1} max={50} value={maxCases} onChange={setMaxCases} disabled={loading} /></label>
        <label>测试重点 <Input.TextArea aria-label="范围测试重点" value={goal} maxLength={500} rows={2} onChange={(event) => setGoal(event.target.value)} disabled={loading} /></label>
      </div>}
      {isCoverage && <div className="test-agent-gate-plan">
        <p>{request.clause_count} 个原子条款 · 可取消本轮无需生成的覆盖维度</p>
        {plan.map((item, index) => <Checkbox key={`${item.clause_id}-${index}`} checked={!excluded.includes(index)} disabled={loading}
          onChange={(event) => setExcluded((items) => event.target.checked ? items.filter((value) => value !== index) : [...items, index])}>
          {item.clause_id} · {item.dimension}
        </Checkbox>)}
      </div>}
      {(request.warnings || []).map((warning, index) => <p key={index} className="test-agent-warning">{warning}</p>)}
      {isSave && <p className="test-agent-gate-hint">产物面板显示本次待审批版本。仅勾选的用例会写入正式用例管理。</p>}
      <Space size={8} wrap>
        {!isSave && <Button type="primary" loading={loading} disabled={!valid} onClick={approve}>{label}</Button>}
        <Button danger disabled={loading} onClick={() => onResolve("rejected", { rejected: true })}>暂不继续</Button>
      </Space>
    </section>
  );
}
