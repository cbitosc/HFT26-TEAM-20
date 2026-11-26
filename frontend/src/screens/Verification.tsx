import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { useEvidence } from "../api/hooks";
import { Spinner } from "../components/Spinner";
import { ErrorBox } from "../components/ErrorBox";
import { Empty } from "../components/Empty";
import { HashChip } from "../components/CopyButton";

export function Verification() {
  const { executionId } = useParams<{ executionId: string }>();
  const { data, isLoading, isError, error, refetch } = useEvidence(executionId);

  if (isLoading) return <Spinner label="Loading evidence…" />;
  if (isError) return <ErrorBox error={error} onRetry={() => void refetch()} />;
  if (!data) return <Empty message="No evidence." />;

  const c = data.commitment;

  return (
    <section>
      <div className="panel">
        <div className="row" style={{ alignItems: "center", justifyContent: "space-between" }}>
          <h2 style={{ margin: 0 }}>Verification</h2>
          <Link to={`/executions/${executionId}`} style={{ flex: "0 0 auto" }}>
            <button type="button" className="ghost">
              <ArrowLeft size={15} style={{ verticalAlign: "-2px", marginRight: 4 }} />
              Back to run
            </button>
          </Link>
        </div>
        <p className="hint" style={{ marginBottom: 0 }}>
          Read-only. These are the committed hashes and the typed evidence
          records. Hidden test contents never appear here.
        </p>
      </div>

      <div className="panel">
        <h3>Commitment</h3>
        {c ? (
          <>
            <div className="hash-grid glow-transition glow-purple">
              <HashChip label="Suite" value={c.suite_id} />
              <HashChip label="Suite #" value={c.suite_hash} />
              <HashChip label="Public #" value={c.public_suite_hash} />
              <HashChip label="Hidden #" value={c.hidden_suite_hash} />
              <HashChip label="Config #" value={c.evaluator_config_hash} />
            </div>
            <dl className="kv" style={{ marginTop: "var(--s-4)" }}>
              <dt>Scoring rule version</dt>
              <dd>{c.scoring_rule_version}</dd>
              <dt>Delta</dt>
              <dd>{c.delta}</dd>
              <dt>Committed at</dt>
              <dd>{c.committed_at}</dd>
              <dt>On-chain</dt>
              <dd>{c.onchain}</dd>
            </dl>
          </>
        ) : (
          <Empty message="No commitment recorded for this execution." />
        )}
      </div>

      <div className="panel">
        <h3>Scoring rule</h3>
        <dl className="kv">
          <dt>Version</dt>
          <dd>{data.scoring_rule.version}</dd>
          <dt>Formula</dt>
          <dd>{data.scoring_rule.formula}</dd>
          <dt>Delta</dt>
          <dd>{data.scoring_rule.delta}</dd>
        </dl>
      </div>

      <div className="panel">
        <h3>Evidence records</h3>
        {data.records.length === 0 ? (
          <Empty message="No decided evidence records yet." />
        ) : (
          data.records.map((r) => (
            <div className="test-row" key={r.id}>
              <div className="node-head">
                <strong className="mono">{r.status}</strong>
                <span className="muted mono">
                  candidate {r.candidate_version_id.slice(0, 8)}
                </span>
                {r.previous_best_version_id && (
                  <span className="muted mono">
                    prev {r.previous_best_version_id.slice(0, 8)}
                  </span>
                )}
              </div>
              {r.failed_terms.length > 0 && (
                <div className="term-chips">
                  {r.failed_terms.map((t, i) => (
                    <span className="chip" key={`${t.term}-${i}`} title={t.message}>
                      {t.term}
                    </span>
                  ))}
                </div>
              )}
              {r.bundles.length > 0 && (
                <div className="hint mono" style={{ marginTop: "var(--s-2)" }}>
                  bundle sha256: {r.bundles.map((b) => b.bundle_sha256).join(", ")}
                </div>
              )}
            </div>
          ))
        )}
      </div>

      <div className="panel">
        <h3>Invalid comparisons</h3>
        <p className="hint">
          These are not evidence about a revision — the comparison could not
          validly occur.
        </p>
        {data.invalid_comparisons.length === 0 ? (
          <Empty message="None." />
        ) : (
          data.invalid_comparisons.map((ic) => (
            <div className="test-row" key={ic.id}>
              <div className="node-head">
                <strong className="mono">invalid comparison</strong>
                <span className="muted mono">
                  candidate {ic.candidate_version_id.slice(0, 8)}
                </span>
              </div>
              <p className="muted">{ic.note}</p>
              {ic.reasons.length > 0 && (
                <div className="term-chips">
                  {ic.reasons.map((t, i) => (
                    <span className="chip" key={`${t.term}-${i}`} title={t.message}>
                      {t.term}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))
        )}
      </div>

      <div className="panel">
        <h3>Advisory proposals</h3>
        <p style={{ margin: 0 }}>
          {data.unvalidated_proposals} unvalidated Critic proposal
          {data.unvalidated_proposals === 1 ? "" : "s"}. Advisory only; not
          evidence of correctness.
        </p>
      </div>
    </section>
  );
}
