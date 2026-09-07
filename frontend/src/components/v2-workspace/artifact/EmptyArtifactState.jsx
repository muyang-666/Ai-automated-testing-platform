// P09.1 Empty State：Conversation 尚未绑定 Artifact（Chat 仍可正常使用）。
export default function EmptyArtifactState({ onOpenSelector, onCreateStart }) {
  return (
    <div className="v2w-empty">
      <div className="v2w-empty-title">未选择测试资产</div>
      <p>
        新建或选择一个测试资产，
        <br />
        Agent 才能读取和修改测试内容。
      </p>
      <div className="v2w-empty-actions">
        <button type="button" className="v2w-btn v2w-btn-primary" onClick={onCreateStart}>
          新建测试资产
        </button>
        <button type="button" className="v2w-btn" onClick={onOpenSelector}>
          选择测试资产
        </button>
      </div>
    </div>
  );
}
