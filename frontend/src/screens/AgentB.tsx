import { useState } from "react";
import { Link } from "react-router-dom";
import { Bot, Brain, Play } from "lucide-react";
import {
  useCreateTransferExperiment,
  useMemory,
  useTransferExperiment,
} from "../api/hooks";
import { Spinner } from "../components/Spinner";
import { ErrorBox } from "../components/ErrorBox";
import { Empty } from "../components/Empty";
import { HashChip } from "../components/CopyButton";
import type { TransferExecMetrics } from "../api/types";

function pct(v: number | null): string {
  return v === null ? "—" : `${v.toFixed(0)}%`;
}

function AccuracyBar({ label, metrics }: { label: string; metrics: TransferExecMetrics }) {
  const value = metrics.best_hidden_accuracy;
  const width = value === null ? 0 : Math.max(0, Math.min(100, value));
  const tone = width >= 100 ? "ok" : width > 0 ? "" : "neutral";
  return (
    <div className="pbar-row" style={{ gridTemplateColumns: "110px 1fr auto" }}>
      <span>{label}</span>
      <span className="pbar">
        <span className={`pbar-fill ${tone}`} style={{ width: `${width}%` }} />
      </span>
      <span className="mono">{pct(value)}</span>
    </div>
  );
}

function MemoryPanel() {
  const { data, isLoading, isError, error, refetch } = useMemory();
  return (
    <div className="panel">
      <div className="card-head">
        <Brain size={18} />
        <h3 style={{ margin: 0 }}>Learned lessons</h3>
      </div>
      <p className="hint">
        Lessons recorded from accepted improvements. Hidden-safe: only aggregate
        pass-rates, never hidden test names or contents.
      </p>
      {isLoading && <Spinner label="Loading memory…" />}
      {isError && <ErrorBox error={error} onRetry={() => void refetch()} />}
      {data && data.length === 0 && (
        <Empty message="No lessons yet. Accepted improvements on earlier runs become lessons here." />
      )}
      {data &&
        data.map((m) => (
          <div className="test-row" key={m.id}>
            <div className="node-head">
              {m.task_category && <span className="badge badge-neutral">{m.task_category}</span>}
              <span className="muted mono">from {m.source_execution_id.slice(0, 8)}</span>
            </div>
            <p style={{ margin: "var(--s-2) 0 0" }}>{m.content}</p>
          </div>
        ))}
    </div>
  );
}

function ExperimentResult({ experimentId }: { experimentId: string }) {
  const { data, isLoading, isError, error } = useTransferExperiment(experimentId);
  if (isLoading) return <div className="panel"><Spinner label="Loading experiment…" /></div>;
  if (isError) return <div className="panel"><ErrorBox error={error} /></div>;
  if (!data) return null;

  const m = data.metrics;
  const running = !m || !m.control.terminal || !m.treatment.terminal;
  const delta = m?.delta_best_hidden_accuracy ?? null;

  return (
    <div className="panel">
      <div className="card-head">
        <h3 style={{ margin: 0 }}>Transfer experiment</h3>
        {running ? (
          <span className="badge badge-running">running</span>
        ) : (
          <span className="badge badge-ok">complete</span>
        )}
      </div>
      <p className="hint">
        Same suite; the only difference is that the treatment run received{" "}
        {data.used_memory_ids.length} prior lesson
        {data.used_memory_ids.length === 1 ? "" : "s"} in its task description.
      </p>

      {m ? (
        <>
          <div className="pbar-wrap" style={{ maxWidth: 520 }}>
            <AccuracyBar label="control" metrics={m.control} />
            <AccuracyBar label="treatment" metrics={m.treatment} />
          </div>
          <p style={{ marginTop: "var(--s-3)" }}>
            Best hidden accuracy:{" "}
            <span className="mono">{pct(m.control.best_hidden_accuracy)}</span>{" "}
            <span className="muted">(control)</span> vs{" "}
            <span className="mono">{pct(m.treatment.best_hidden_accuracy)}</span>{" "}
            <span className="muted">(treatment)</span>
            {delta !== null && (
              <span
                className={`badge ${delta > 0 ? "badge-ok" : delta < 0 ? "badge-bad" : "badge-neutral"}`}
                style={{ marginLeft: "var(--s-2)" }}
              >
                {delta > 0 ? "+" : ""}
                {delta.toFixed(0)} pts
              </span>
            )}
          </p>
          {running && (
            <p className="hint">Both runs are still in progress — refreshing live.</p>
          )}
        </>
      ) : (
        <Spinner label="Waiting for the runs to produce results…" />
      )}

      <div className="row" style={{ marginTop: "var(--s-4)" }}>
        <Link to={`/executions/${data.control_execution_id}`}>
          <button type="button">Open control run</button>
        </Link>
        <Link to={`/executions/${data.treatment_execution_id}`}>
          <button type="button">Open treatment run</button>
        </Link>
      </div>

      {data.attestation && (
        <div style={{ marginTop: "var(--s-4)" }}>
          <div className="card-head">
            <h4 style={{ margin: 0 }}>Attestation</h4>
            <span className={`badge ${data.attestation.hash_valid ? "badge-ok" : "badge-bad"}`}>
              {data.attestation.hash_valid ? "hash valid" : "tampered"}
            </span>
            <span className="badge badge-neutral">on-chain: {data.attestation.onchain}</span>
          </div>
          <div className="hash-grid" style={{ marginTop: "var(--s-2)" }}>
            <HashChip label="Attestation #" value={data.attestation.payload_sha256} />
            {data.suite_hash && <HashChip label="Suite #" value={data.suite_hash} />}
          </div>
        </div>
      )}
    </div>
  );
}

export function AgentB() {
  const [baseTaskId, setBaseTaskId] = useState("");
  const [start, setStart] = useState(true);
  const [experimentId, setExperimentId] = useState<string | null>(null);
  const create = useCreateTransferExperiment();

  function onRun() {
    create.mutate(
      { base_task_id: baseTaskId.trim(), start },
      { onSuccess: (exp) => setExperimentId(exp.id) },
    );
  }

  return (
    <section>
      <div className="panel">
        <div className="card-head">
          <Bot size={20} />
          <h2 style={{ margin: 0 }}>Agent B — knowledge transfer</h2>
        </div>
        <p className="hint" style={{ marginBottom: 0 }}>
          Agent B solves a task twice on the same hidden suite: once cold
          (control) and once with prior lessons injected (treatment). The
          measured difference is real evaluator output, and the result is sealed
          in a hash-addressed attestation.
        </p>
      </div>

      <MemoryPanel />

      <div className="panel">
        <div className="card-head">
          <h3 style={{ margin: 0 }}>Run a transfer experiment</h3>
        </div>
        <div className="field">
          <label htmlFor="baseTaskId">Base task id (a task using a registered suite)</label>
          <input
            id="baseTaskId"
            className="mono"
            value={baseTaskId}
            onChange={(e) => setBaseTaskId(e.target.value)}
            placeholder="paste a task id"
          />
        </div>
        <label style={{ display: "flex", alignItems: "center", gap: "var(--s-2)", marginBottom: "var(--s-4)" }}>
          <input
            type="checkbox"
            style={{ width: "auto" }}
            checked={start}
            onChange={(e) => setStart(e.target.checked)}
          />
          Start both runs now (needs the LLM configured)
        </label>
        {create.isError && <ErrorBox error={create.error} />}
        <button
          type="button"
          className="primary"
          onClick={onRun}
          disabled={create.isPending || baseTaskId.trim().length === 0}
        >
          <Play size={15} style={{ verticalAlign: "-2px", marginRight: 6 }} />
          {create.isPending ? "Starting…" : "Run transfer experiment"}
        </button>
      </div>

      {experimentId && <ExperimentResult experimentId={experimentId} />}
    </section>
  );
}
