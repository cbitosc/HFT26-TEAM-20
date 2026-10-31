import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowRight, Check, GitCompare, ShieldCheck, Star } from "lucide-react";
import {
  useCancelExecution,
  useExecutionTree,
  useVersion,
  useVersionEvaluations,
} from "../api/hooks";
import { Spinner } from "../components/Spinner";
import { ErrorBox } from "../components/ErrorBox";
import { Empty } from "../components/Empty";
import {
  AcceptanceBadge,
  PollingHint,
  StalledBadge,
  StatusBadge,
} from "../components/Badge";
import {
  isTerminal,
  type Counts,
  type EvaluationRead,
  type ExecutionStatus,
  type ExecutionTree,
  type VersionNode,
} from "../api/types";

const STAGES = ["Generate", "Evaluate", "Critique", "Revise", "Gate"] as const;

function rate(c: Counts | null | undefined): number | null {
  if (!c || c.total === 0) return null;
  return (c.passed / c.total) * 100;
}

function pct0(v: number | null): string {
  return v === null ? "—" : `${v.toFixed(0)}%`;
}

function activeStage(status: ExecutionStatus): number {
  if (isTerminal(status)) return STAGES.length; // all done
  switch (status) {
    case "generating_v1":
      return 0;
    case "evaluating_v1":
      return 1;
    case "critiquing":
    case "critiquing_v2":
      return 2;
    case "generating_v2":
    case "generating_v3":
      return 3;
    case "evaluating_v2":
    case "evaluating_v3":
    case "zk_proof":
    case "ipfs_publish":
    case "blockchain_register":
      return 4;
    default:
      return -1; // queued
  }
}

function Stepper({ status }: { status: ExecutionStatus }) {
  const active = activeStage(status);
  return (
    <div className="stepper" aria-label="Pipeline stage">
      {STAGES.map((s, i) => {
        const cls = i < active ? "done" : i === active ? "active" : "";
        return (
          <span className={`step ${cls}`} key={s}>
            {s}
          </span>
        );
      })}
    </div>
  );
}

function ProgressRow({ label, counts }: { label: string; counts: Counts | null }) {
  const pct = counts && counts.total > 0 ? (counts.passed / counts.total) * 100 : 0;
  const tone = pct >= 100 ? "ok" : pct > 0 ? "" : "neutral";
  return (
    <div className="pbar-row">
      <span>{label}</span>
      <span className="pbar">
        <span className={`pbar-fill ${tone}`} style={{ width: `${pct}%` }} />
      </span>
      <span className="mono">{counts ? `${counts.passed}/${counts.total}` : "—"}</span>
    </div>
  );
}

// ---- A: inline SVG score chart (aggregate score per version) ----
function ScoreChart({ versions }: { versions: VersionNode[] }) {
  const pts = versions.filter((v) => v.overall_score !== null);
  if (pts.length === 0) return null;
  const W = 320;
  const H = 150;
  const padX = 26;
  const padY = 20;
  const n = pts.length;
  const x = (i: number) => (n === 1 ? W / 2 : padX + (i * (W - 2 * padX)) / (n - 1));
  const y = (s: number) => H - padY - (s / 100) * (H - 2 * padY);
  const polyline = pts.map((v, i) => `${x(i)},${y(v.overall_score as number)}`).join(" ");
  const aria =
    "Aggregate score per version: " +
    pts.map((v) => `${v.label} ${(v.overall_score as number).toFixed(0)}`).join(", ");

  function kind(v: VersionNode): "accepted" | "rejected" | "baseline" {
    if (v.acceptance_status === "rejected") return "rejected";
    if (v.acceptance_status === "accepted" && v.parent_version_id !== null) return "accepted";
    return "baseline";
  }

  return (
    <svg role="img" aria-label={aria} viewBox={`0 0 ${W} ${H}`} className="hero-chart">
      <line x1={padX} y1={H - padY} x2={W - padX} y2={H - padY} stroke="var(--border)" strokeWidth="1" />
      <polyline points={polyline} fill="none" stroke="var(--border-strong)" strokeWidth="2" />
      {pts.map((v, i) => {
        const k = kind(v);
        const solid = k === "accepted";
        const color =
          k === "accepted" ? "#4c8dff" : k === "rejected" ? "var(--bad)" : "var(--neutral)";
        return (
          <circle
            key={v.id}
            cx={x(i)}
            cy={y(v.overall_score as number)}
            r="5"
            fill={solid ? "#4c8dff" : "var(--panel)"}
            stroke={color}
            strokeWidth="2"
          />
        );
      })}
    </svg>
  );
}

// ---- A: hero card ----
function Hero({ tree }: { tree: ExecutionTree }) {
  const versions = tree.versions;
  const first = versions.find((v) => v.sequence === 1) ?? versions[0];
  const best = tree.best_version_id
    ? versions.find((v) => v.id === tree.best_version_id)
    : undefined;

  const firstHidden = rate(first?.hidden);
  const bestHidden = rate(best?.hidden) ?? tree.best_hidden_accuracy;
  const delta =
    firstHidden !== null && bestHidden !== null ? bestHidden - firstHidden : null;
  const bestPublic = rate(best?.public);

  const acceptedRevs = versions.filter(
    (v) => v.acceptance_status === "accepted" && v.parent_version_id !== null,
  ).length;
  const rejected = versions.filter((v) => v.acceptance_status === "rejected").length;

  // Summary built ONLY from real decisions.
  const summary = best
    ? `Best version is ${best.label} at ${pct0(bestHidden)} hidden accuracy. ` +
      `${acceptedRevs} revision${acceptedRevs === 1 ? "" : "s"} accepted, ${rejected} rejected.`
    : `No accepted best version yet. ${rejected} revision${rejected === 1 ? "" : "s"} rejected so far.`;

  return (
    <div className="hero">
      <div className="hero-left">
        <span className="hero-label">Hidden accuracy, best version</span>
        <div className="hero-metric">
          <span>{pct0(firstHidden)}</span>
          <ArrowRight size={26} aria-hidden="true" />
          <span>{pct0(bestHidden)}</span>
        </div>
        <div className="hero-row">
          {delta !== null && delta > 0 && (
            <span className="points-pill">+{delta.toFixed(0)} points</span>
          )}
          {bestPublic !== null && (
            <span className="hero-chip">public {bestPublic.toFixed(0)}%</span>
          )}
        </div>
        <p className="hero-summary">{summary}</p>
      </div>
      <ScoreChart versions={versions} />
    </div>
  );
}

// ---- D: ring gauges for P / C / Q ----
function RingGauge({
  label,
  value,
  dropped,
}: {
  label: string;
  value: number;
  dropped: boolean;
}) {
  const r = 32;
  const circ = 2 * Math.PI * r;
  const clamped = Math.max(0, Math.min(100, value));
  const offset = circ * (1 - clamped / 100);
  const color = dropped ? "var(--bad)" : "var(--accent)";
  return (
    <div className={`gauge ${dropped ? "dropped" : ""}`}>
      <svg viewBox="0 0 84 84" width="84" height="84" aria-hidden="true">
        <circle cx="42" cy="42" r={r} fill="none" stroke="var(--panel-hover)" strokeWidth="8" />
        <circle
          cx="42"
          cy="42"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="8"
          strokeDasharray={circ}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform="rotate(-90 42 42)"
        />
        <text x="42" y="47" textAnchor="middle" fontSize="15" fill="var(--text)" fontFamily="var(--font-mono)">
          {Math.round(value)}
        </text>
      </svg>
      <span className="g-label">{label}</span>
      {dropped && <span className="g-drop">previous → current</span>}
    </div>
  );
}

function ScoreBreakdown({
  evaluation,
  failedTerms,
}: {
  evaluation: EvaluationRead;
  failedTerms: VersionNode["failed_terms"];
}) {
  const d = evaluation.deterministic;
  const has = (term: string) => failedTerms.some((t) => t.term === term);
  return (
    <div>
      <h4 style={{ margin: "var(--s-2) 0" }}>Score breakdown</h4>
      <div className="gauges">
        <RingGauge
          label="P pass rate"
          value={d.test_pass_rate}
          dropped={has("no_dimension_regression:hidden_pass_rate")}
        />
        <RingGauge
          label="C correctness"
          value={d.correctness_score}
          dropped={has("no_dimension_regression:correctness")}
        />
        <RingGauge
          label="Q quality"
          value={d.code_quality_score}
          dropped={has("no_dimension_regression:code_quality")}
        />
      </div>
    </div>
  );
}

// ---- E: trust chain ----
function TrustChain({ tree }: { tree: ExecutionTree }) {
  const committed = tree.versions.length > 0; // commitment is recorded when the run starts
  const gated = Boolean(tree.best_version_id) || tree.versions.some((v) => v.decided);
  const steps = [
    { label: "Suite committed", done: committed, note: committed ? "hashes recorded" : "pending" },
    { label: "Evaluated & gated", done: gated, note: gated ? "decision recorded" : "pending" },
    { label: "ZK proof", done: false, note: "Not built yet" },
    { label: "Published on-chain", done: false, note: "Not built yet" },
  ];
  return (
    <div className="panel">
      <h3 style={{ marginTop: 0 }}>Trust chain</h3>
      <div className="trust">
        {steps.map((s, i) => (
          <div className={`trust-step ${s.done ? "done" : ""}`} key={s.label}>
            <span className="trust-num">{s.done ? <Check size={13} /> : i + 1}</span>
            <span className="trust-label">{s.label}</span>
            <span className="trust-note">{s.note}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function RunView() {
  const { executionId } = useParams<{ executionId: string }>();
  const { data, isLoading, isError, error, refetch } =
    useExecutionTree(executionId);
  const cancel = useCancelExecution(executionId ?? "");

  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    if (!data || selectedId) return;
    if (data.best_version_id) setSelectedId(data.best_version_id);
    else if (data.versions.length > 0)
      setSelectedId(data.versions[data.versions.length - 1].id);
  }, [data, selectedId]);

  if (isLoading) return <Spinner label="Loading run…" />;
  if (isError) return <ErrorBox error={error} onRetry={() => void refetch()} />;
  if (!data) return <Empty message="No run data." />;

  const terminal = isTerminal(data.status);
  const selected = data.versions.find((v) => v.id === selectedId) ?? null;
  const hasVersions = data.versions.length > 0;

  return (
    <section>
      <div className="panel">
        <div className="row" style={{ alignItems: "flex-start", justifyContent: "space-between" }}>
          <div>
            <h2 style={{ marginBottom: "var(--s-2)" }}>{data.task_title}</h2>
            <div className="node-head">
              <StatusBadge status={data.status} />
              <StalledBadge stalled={data.stalled} />
              <PollingHint status={data.status} />
            </div>
          </div>
          <div style={{ flex: "0 0 auto", display: "flex", gap: "var(--s-2)" }}>
            <Link to={`/executions/${executionId}/verification`}>
              <button type="button">
                <ShieldCheck size={15} style={{ verticalAlign: "-2px", marginRight: 4 }} />
                Verification
              </button>
            </Link>
            {!terminal && (
              <button
                type="button"
                className="danger"
                onClick={() => cancel.mutate()}
                disabled={cancel.isPending}
              >
                {cancel.isPending ? "Cancelling…" : "Cancel run"}
              </button>
            )}
          </div>
        </div>

        <div style={{ marginTop: "var(--s-4)" }}>
          <Stepper status={data.status} />
        </div>

        {cancel.isError && <ErrorBox error={cancel.error} />}
        {data.stalled && (
          <p className="warn-note">
            This run was claimed by an earlier server process and is not being
            resumed. Cancel it to close it out; everything recorded so far is
            kept.
          </p>
        )}
      </div>

      {hasVersions && <Hero tree={data} />}
      {hasVersions && <TrustChain tree={data} />}

      {!hasVersions ? (
        <div className="panel">
          <Empty message="No versions generated yet. This updates live while the run is active." />
        </div>
      ) : (
        <div className="run-layout">
          <div className="panel">
            <h3 style={{ marginTop: 0 }}>Versions</h3>
            <div className="timeline">
              {data.versions.map((node) => (
                <TreeNode
                  key={node.id}
                  node={node}
                  isBest={node.id === data.best_version_id}
                  selected={node.id === selectedId}
                  onSelect={() => setSelectedId(node.id)}
                />
              ))}
            </div>
          </div>

          {selected && (
            <VersionDetail node={selected} executionId={executionId ?? ""} />
          )}
        </div>
      )}
    </section>
  );
}

function TreeNode({
  node,
  isBest,
  selected,
  onSelect,
}: {
  node: VersionNode;
  isBest: boolean;
  selected: boolean;
  onSelect: () => void;
}) {
  const cls = isBest
    ? "is-best"
    : node.acceptance_status === "rejected"
      ? "is-rejected"
      : "";
  // A validated improvement = an accepted revision (not the baseline V1).
  const improved =
    node.acceptance_status === "accepted" && node.parent_version_id !== null;
  return (
    <div className={`timeline-node ${cls}`}>
      <div
        className={`node-card glow-transition ${selected ? "selected" : ""} ${improved ? "glow-green" : ""}`}
        onClick={onSelect}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") onSelect();
        }}
      >
        <div className="node-head">
          <strong>{node.label}</strong>
          <AcceptanceBadge value={node.acceptance_status} />
          {isBest && (
            <span className="badge badge-ok">
              <Star size={11} /> best
            </span>
          )}
          {node.overall_score !== null && (
            <span className="muted mono" style={{ marginLeft: "auto" }}>
              {node.overall_score.toFixed(1)}
            </span>
          )}
        </div>
        <div className="pbar-wrap">
          <ProgressRow label="public" counts={node.public} />
          <ProgressRow label="hidden" counts={node.hidden} />
        </div>
        {node.failed_terms.length > 0 && (
          <div className="term-chips">
            {node.failed_terms.map((t, i) => (
              <span className="chip" key={`${t.term}-${i}`} title={t.message}>
                {t.term}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

type Tab = "code" | "public" | "critic" | "metadata";

function VersionDetail({
  node,
  executionId,
}: {
  node: VersionNode;
  executionId: string;
}) {
  const version = useVersion(node.id);
  const evals = useVersionEvaluations(node.id);
  const [tab, setTab] = useState<Tab>("public");
  const latest =
    evals.data && evals.data.length > 0 ? evals.data[evals.data.length - 1] : null;

  const tabs: { key: Tab; label: string }[] = [
    { key: "code", label: "Code" },
    { key: "public", label: "Public tests" },
    { key: "critic", label: "Critic" },
    { key: "metadata", label: "Metadata" },
  ];

  return (
    <div className="panel">
      <div className="row" style={{ alignItems: "center", justifyContent: "space-between" }}>
        <h3 style={{ margin: 0 }}>{node.label} detail</h3>
        {node.parent_version_id && (
          <Link
            to={`/executions/${executionId}/compare/${node.id}`}
            style={{ flex: "0 0 auto" }}
          >
            <button type="button">
              <GitCompare size={15} style={{ verticalAlign: "-2px", marginRight: 4 }} />
              Compare with parent
            </button>
          </Link>
        )}
      </div>

      <p style={{ marginTop: "var(--s-3)" }}>
        {node.hidden
          ? `${node.hidden.passed} of ${node.hidden.total} hidden tests passed.`
          : "Hidden suite not evaluated yet."}{" "}
        <span className="hint">
          Hidden test names, inputs and per-test results are never shown — only
          these counts.
        </span>
      </p>

      {version.data?.changelog?.[0] && (
        <p className="hint mono" style={{ marginTop: 0 }}>
          {version.data.changelog[0]}
        </p>
      )}

      {latest && <ScoreBreakdown evaluation={latest} failedTerms={node.failed_terms} />}

      <div className="tabs" role="tablist">
        {tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            className={`tab ${tab === t.key ? "active" : ""}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Code */}
      <div className="tabpanel" role="tabpanel" hidden={tab !== "code"}>
        {version.isLoading && <Spinner label="Loading code…" />}
        {version.isError && <ErrorBox error={version.error} />}
        {version.data && (
          <>
            <p className="hint mono">sha256: {version.data.code_sha256}</p>
            <pre className="code">{version.data.code}</pre>
          </>
        )}
      </div>

      {/* Public tests */}
      <div className="tabpanel" role="tabpanel" hidden={tab !== "public"}>
        {evals.isLoading && <Spinner label="Loading evaluation…" />}
        {evals.isError && <ErrorBox error={evals.error} />}
        {latest && latest.test_results.length === 0 && (
          <p className="muted">No public test results recorded.</p>
        )}
        {latest && latest.test_results.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>Test</th>
                <th>Result</th>
              </tr>
            </thead>
            <tbody>
              {latest.test_results.map((r) => (
                <tr key={r.test_id}>
                  <td className="mono">{r.test_id}</td>
                  <td>
                    {r.passed ? (
                      <span className="badge badge-ok">pass</span>
                    ) : (
                      <span className="badge badge-bad">fail</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {latest && latest.failure_details.length > 0 && (
          <div style={{ marginTop: "var(--s-4)" }}>
            <h5 style={{ margin: "0 0 var(--s-2)" }}>Public failures</h5>
            {latest.failure_details.map((f, i) => (
              <div className="test-row" key={`${f.test_name}-${i}`}>
                <strong className="mono">{f.test_name}</strong>
                <div className="hint">expected: {f.expected}</div>
                <div className="hint">actual: {f.actual}</div>
                {f.exception && <div className="hint">exception: {f.exception}</div>}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Critic */}
      <div className="tabpanel" role="tabpanel" hidden={tab !== "critic"}>
        {node.critic_note ? (
          <>
            <div className="card-head">
              <h4 style={{ margin: 0 }}>Critic note</h4>
              <span className="badge badge-neutral">advisory</span>
            </div>
            <p className="advisory">{node.critic_note}</p>
            <p className="hint">
              Advisory only. It is not an evaluation result and does not affect
              the acceptance decision.
            </p>
          </>
        ) : (
          <p className="muted">
            No Critic note for this version. <span className="badge badge-neutral">advisory</span>
          </p>
        )}
      </div>

      {/* Metadata */}
      <div className="tabpanel" role="tabpanel" hidden={tab !== "metadata"}>
        <dl className="kv">
          <dt>Acceptance</dt>
          <dd>{node.acceptance_status}</dd>
          <dt>Overall score</dt>
          <dd>{node.overall_score !== null ? node.overall_score.toFixed(2) : "—"}</dd>
          <dt>Generator model</dt>
          <dd>{node.generator_model_id ?? "—"}</dd>
          <dt>Prompt tokens</dt>
          <dd>{node.generation_prompt_tokens ?? "—"}</dd>
          <dt>Completion tokens</dt>
          <dd>{node.generation_completion_tokens ?? "—"}</dd>
        </dl>
        {node.failed_terms.length > 0 && (
          <div className="term-chips" style={{ marginTop: "var(--s-3)" }}>
            {node.failed_terms.map((t, i) => (
              <span className="chip" key={`${t.term}-${i}`} title={t.message}>
                {t.term}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
