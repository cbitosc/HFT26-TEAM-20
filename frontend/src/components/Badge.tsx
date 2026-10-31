import type { ExecutionStatus } from "../api/types";
import { isTerminal } from "../api/types";

export function StatusBadge({ status }: { status: ExecutionStatus }) {
  let tone = "badge-running";
  if (status === "completed") tone = "badge-ok";
  else if (status === "completed_no_improvement") tone = "badge-neutral";
  else if (status === "failed") tone = "badge-bad";
  else if (status === "cancelled") tone = "badge-neutral";
  else if (status === "queued") tone = "badge-neutral";
  return <span className={`badge ${tone}`}>{status.replace(/_/g, " ")}</span>;
}

export function StalledBadge({ stalled }: { stalled: boolean }) {
  if (!stalled) return null;
  return <span className="badge badge-warn">stalled</span>;
}

export function AcceptanceBadge({
  value,
}: {
  value: "pending" | "accepted" | "rejected";
}) {
  const tone =
    value === "accepted"
      ? "badge-ok"
      : value === "rejected"
        ? "badge-bad"
        : "badge-neutral";
  return <span className={`badge ${tone}`}>{value}</span>;
}

// A clearly-labelled marker for any sample/preview data, per AGENTS.md.
export function SampleDataBadge() {
  return <span className="badge badge-sample">SAMPLE DATA</span>;
}

export function PollingHint({ status }: { status: ExecutionStatus }) {
  return (
    <span className="hint">{isTerminal(status) ? "Final" : "Live — refreshing"}</span>
  );
}
