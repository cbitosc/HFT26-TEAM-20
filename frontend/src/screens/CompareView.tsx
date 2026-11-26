import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, ArrowRight, AlertTriangle } from "lucide-react";
import { useExecutionTree, useVersion, useVersionDiff } from "../api/hooks";
import { Spinner } from "../components/Spinner";
import { ErrorBox } from "../components/ErrorBox";
import { Empty } from "../components/Empty";
import type { Counts, VersionNode } from "../api/types";

function rate(c: Counts | null): number | null {
  if (!c || c.total === 0) return null;
  return (c.passed / c.total) * 100;
}

function fmt(r: number | null): string {
  return r === null ? "—" : `${r.toFixed(1)}%`;
}

function DiffView({ unifiedDiff }: { unifiedDiff: string }) {
  const lines = unifiedDiff.split("\n");
  return (
    <pre className="code diff">
      {lines.map((line, i) => {
        let cls = "diff-line-ctx";
        if (line.startsWith("+") && !line.startsWith("+++")) cls = "diff-line-add";
        else if (line.startsWith("-") && !line.startsWith("---")) cls = "diff-line-del";
        return (
          <span key={i} className={cls}>
            <span
              className="muted"
              style={{ display: "inline-block", width: "2.5em", opacity: 0.5, userSelect: "none" }}
              aria-hidden="true"
            >
              {i + 1}
            </span>
            {line}
            {"\n"}
          </span>
        );
      })}
    </pre>
  );
}

export function CompareView() {
  const { executionId, versionId } = useParams<{
    executionId: string;
    versionId: string;
  }>();

  const tree = useExecutionTree(executionId);
  const diff = useVersionDiff(versionId);
  const [fullCode, setFullCode] = useState(false);
  const fullVersion = useVersion(fullCode ? versionId : undefined);

  if (tree.isLoading || diff.isLoading) return <Spinner label="Loading comparison…" />;
  if (tree.isError) return <ErrorBox error={tree.error} onRetry={() => void tree.refetch()} />;
  if (diff.isError) return <ErrorBox error={diff.error} onRetry={() => void diff.refetch()} />;
  if (!tree.data || !diff.data) return <Empty message="No comparison data." />;

  const candidate: VersionNode | undefined = tree.data.versions.find(
    (v) => v.id === versionId,
  );
  if (!candidate) return <Empty message="Version not found in this run." />;

  const parent = candidate.parent_version_id
    ? tree.data.versions.find((v) => v.id === candidate.parent_version_id)
    : undefined;

  const prevHidden = rate(parent?.hidden ?? null);
  const newHidden = rate(candidate.hidden);
  const prevPublic = rate(parent?.public ?? null);
  const newPublic = rate(candidate.public);

  const hiddenDelta =
    prevHidden !== null && newHidden !== null ? newHidden - prevHidden : null;
  const bannerTone =
    hiddenDelta === null ? "" : hiddenDelta >= 0 ? "ok" : "bad";

  const publicImproved =
    prevPublic !== null && newPublic !== null && newPublic > prevPublic;
  const hiddenImproved =
    prevHidden !== null && newHidden !== null && newHidden > prevHidden;
  const publicUpHiddenNot = publicImproved && !hiddenImproved;

  const gatePassed =
    candidate.acceptance_status === "accepted" &&
    candidate.failed_terms.length === 0;

  return (
    <section>
      <div className="row" style={{ alignItems: "center", justifyContent: "space-between" }}>
        <h2 style={{ margin: 0 }}>
          {parent ? `${parent.label} → ` : ""}
          {candidate.label}
        </h2>
        <Link to={`/executions/${executionId}`} style={{ flex: "0 0 auto" }}>
          <button type="button" className="ghost">
            <ArrowLeft size={15} style={{ verticalAlign: "-2px", marginRight: 4 }} />
            Back to run
          </button>
        </Link>
      </div>

      <div
        className={`banner glow-transition ${bannerTone} ${
          gatePassed
            ? "glow-green"
            : candidate.acceptance_status === "rejected"
              ? "glow-red"
              : ""
        }`}
      >
        <div>
          <div className="hint" style={{ marginBottom: "var(--s-2)" }}>
            Hidden accuracy (the figure the gate scores)
          </div>
          <div className="banner-metric">
            <span>{fmt(prevHidden)}</span>
            <ArrowRight size={26} aria-hidden="true" />
            <span>{fmt(newHidden)}</span>
            {hiddenDelta !== null && (
              <span className="banner-delta">
                {hiddenDelta >= 0 ? "+" : ""}
                {hiddenDelta.toFixed(1)} pts
              </span>
            )}
          </div>
        </div>
        <div style={{ marginLeft: "auto", textAlign: "right" }}>
          <div className="hint">Public accuracy (context only)</div>
          <div className="mono" style={{ fontSize: "var(--fs-lg)" }}>
            {fmt(prevPublic)} → {fmt(newPublic)}
          </div>
        </div>
      </div>

      {publicUpHiddenNot && (
        <div className="banner warn">
          <AlertTriangle size={20} aria-hidden="true" />
          <span>
            Public accuracy improved but hidden accuracy did not. The decision is
            driven by the hidden suite, not the public one.
          </span>
        </div>
      )}

      <div className="panel">
        <h3>Gate result</h3>
        {gatePassed ? (
          <p style={{ margin: 0 }}>
            <span className="badge badge-ok">accepted</span> All gate terms held.
          </p>
        ) : (
          <>
            <p>
              <span className="badge badge-bad">{candidate.acceptance_status}</span>{" "}
              {candidate.failed_terms.length} failed term
              {candidate.failed_terms.length === 1 ? "" : "s"}.
            </p>
            {candidate.failed_terms.length > 0 && (
              <div className="term-chips">
                {candidate.failed_terms.map((t, i) => (
                  <span className="chip" key={`${t.term}-${i}`} title={t.message}>
                    {t.term}
                  </span>
                ))}
              </div>
            )}
          </>
        )}
      </div>

      <div className="panel">
        <div className="row" style={{ alignItems: "center", justifyContent: "space-between" }}>
          <h3 style={{ margin: 0 }}>
            Diff{" "}
            <span className="hint">
              ({diff.data.against_version_id ? `against ${diff.data.against}` : "no parent"})
            </span>
          </h3>
          <button type="button" onClick={() => setFullCode((v) => !v)} style={{ flex: "0 0 auto" }}>
            {fullCode ? "Show diff only" : "Show full file"}
          </button>
        </div>

        {fullCode ? (
          fullVersion.isLoading ? (
            <Spinner label="Loading full file…" />
          ) : fullVersion.isError ? (
            <ErrorBox error={fullVersion.error} />
          ) : (
            <pre className="code">{fullVersion.data?.code}</pre>
          )
        ) : diff.data.unified_diff.trim() === "" ? (
          <Empty message="No textual difference." />
        ) : (
          <DiffView unifiedDiff={diff.data.unified_diff} />
        )}
      </div>

      <div className="panel">
        <h3>Changelog</h3>
        {diff.data.changelog.length === 0 ? (
          <Empty message="No changelog entries." />
        ) : (
          <ul style={{ margin: 0 }}>
            {diff.data.changelog.map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
