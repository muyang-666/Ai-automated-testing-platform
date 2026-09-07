import { domainSummaryLabel, revisionLabel } from "../v2-workspace/artifactChangeSummaryModel.js";

export default function ArtifactChangeSummary({ summary, currentArtifactId, onViewChanges }) {
  if (!summary?.artifacts?.length) return null;
  return (
    <div className="v2-turn-changes">
      {summary.artifacts.map((artifact) => (
        <div key={artifact.artifactId} className="v2-turn-change-row">
          <span><b>变更</b> {domainSummaryLabel(artifact.domainCounts, artifact.changeCounts)}</span>
          <span className="v2-turn-change-revision">{revisionLabel(artifact.fromRevision, artifact.toRevision)}</span>
          {artifact.artifactId === currentArtifactId && artifact.fromRevision != null ? (
            <button type="button" onClick={() => onViewChanges?.(artifact)}>查看变更</button>
          ) : null}
        </div>
      ))}
    </div>
  );
}
