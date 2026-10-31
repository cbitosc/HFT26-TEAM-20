import { Link } from "react-router-dom";
import { Activity, CheckCircle2, Layers, Target, Plus } from "lucide-react";
import { useDashboardExecutions } from "../api/hooks";
import { Spinner } from "../components/Spinner";
import { ErrorBox } from "../components/ErrorBox";
import { Empty } from "../components/Empty";
import { StalledBadge, StatusBadge } from "../components/Badge";
import type { DashboardExecution } from "../api/types";

function formatAccuracy(value: number | null): string {
  if (value === null) return "—";
  return `${value.toFixed(1)}%`;
}

interface Stats {
  total: number;
  best: number | null;
  improved: number;
  noImprovement: number;
}

function computeStats(items: DashboardExecution[], total: number): Stats {
  const accuracies = items
    .map((e) => e.best_hidden_accuracy)
    .filter((v): v is number => v !== null);
  return {
    total,
    best: accuracies.length ? Math.max(...accuracies) : null,
    improved: items.filter((e) => e.status === "completed").length,
    noImprovement: items.filter((e) => e.status === "completed_no_improvement")
      .length,
  };
}

function StatCard({
  icon,
  label,
  value,
  tone,
  glow,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  tone?: "ok" | "bad";
  glow?: boolean;
}) {
  return (
    <div className={`stat-card glow-transition ${glow ? "glow-green" : ""}`}>
      <span className="stat-tile">{icon}</span>
      <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
        <span className="stat-top">{label}</span>
        <span className={`stat-value ${tone ?? ""}`}>{value}</span>
      </div>
    </div>
  );
}

export function Home() {
  const { data, isLoading, isError, error, refetch } = useDashboardExecutions();
  const stats = data ? computeStats(data.items, data.total) : null;

  return (
    <section>
      {stats && (
        <div className="stat-grid">
          <StatCard
            icon={<Layers size={18} />}
            label="Total runs"
            value={String(stats.total)}
          />
          <StatCard
            icon={<Target size={18} />}
            label="Best hidden accuracy"
            value={stats.best === null ? "—" : `${stats.best.toFixed(0)}%`}
            glow={stats.best !== null && stats.best > 0}
          />
          <StatCard
            icon={<CheckCircle2 size={18} />}
            label="Improved runs"
            value={String(stats.improved)}
            tone="ok"
          />
          <StatCard
            icon={<Activity size={18} />}
            label="No improvement"
            value={String(stats.noImprovement)}
          />
        </div>
      )}

      <div className="panel">
        <div
          className="row"
          style={{ alignItems: "center", justifyContent: "space-between" }}
        >
          <div>
            <h2 style={{ marginBottom: "var(--s-1)" }}>Recent executions</h2>
            <p className="hint" style={{ margin: 0 }}>
              Best accuracy is the hidden-suite pass rate of each run&apos;s best
              version. Hidden test contents are never shown — only counts.
            </p>
          </div>
          <Link to="/new" style={{ flex: "0 0 auto" }}>
            <button type="button" className="primary">
              <Plus size={16} style={{ marginRight: 6, verticalAlign: "-3px" }} />
              New Task
            </button>
          </Link>
        </div>

        {isLoading && <Spinner label="Loading executions…" />}
        {isError && <ErrorBox error={error} onRetry={() => void refetch()} />}

        {data && data.items.length === 0 && (
          <Empty message="No executions yet. Create a task to start your first run." />
        )}

        {data && data.items.length > 0 && (
          <table style={{ marginTop: "var(--s-4)" }}>
            <thead>
              <tr>
                <th>Task</th>
                <th>Status</th>
                <th>Best hidden accuracy</th>
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((ex) => (
                <tr key={ex.id}>
                  <td>{ex.task_title}</td>
                  <td>
                    <StatusBadge status={ex.status} />{" "}
                    <StalledBadge stalled={ex.stalled} />
                  </td>
                  <td className="mono">{formatAccuracy(ex.best_hidden_accuracy)}</td>
                  <td className="muted">
                    {new Date(ex.created_at).toLocaleString()}
                  </td>
                  <td>
                    <Link to={`/executions/${ex.id}`}>Open</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}
