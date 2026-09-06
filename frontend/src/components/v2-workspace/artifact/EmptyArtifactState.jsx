// P09.1 Empty State：Conversation 尚未绑定 Artifact（Chat 仍可正常使用）。
export default function EmptyArtifactState({ onOpenSelector, onCreateStart }) {
  return (
    <div className="v2w-empty">
      <div className="v2w-empty-title">No test artifact selected</div>
      <p>
        Create or select a test artifact
        <br />
        to let the Agent work with test assets.
      </p>
      <div className="v2w-empty-actions">
        <button type="button" className="v2w-btn v2w-btn-primary" onClick={onCreateStart}>
          Create artifact
        </button>
        <button type="button" className="v2w-btn" onClick={onOpenSelector}>
          Select artifact
        </button>
      </div>
    </div>
  );
}
