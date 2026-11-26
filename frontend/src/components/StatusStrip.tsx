import { useStatus } from "../api/hooks";

function Pill({ label, state }: { label: string; state: "ok" | "bad" | "muted" }) {
  return <span className={`pill pill-${state}`}>{label}</span>;
}

export function StatusStrip() {
  const { data, isLoading, isError } = useStatus();

  if (isLoading) {
    return (
      <div className="pills">
        <span className="pill pill-muted">Checking status…</span>
      </div>
    );
  }
  if (isError || !data) {
    return (
      <div className="pills">
        <span className="pill pill-bad">Backend unavailable</span>
      </div>
    );
  }

  return (
    <div className="pills">
      <Pill label="Featherless" state={data.featherless_configured ? "ok" : "bad"} />
      <Pill label="Critic" state={data.critic_configured ? "ok" : "bad"} />
      <Pill
        label={`Evaluator: ${data.evaluator_mode}`}
        state={data.evaluator_mode === "subprocess" ? "ok" : "bad"}
      />
      <Pill
        label="Encryption"
        state={data.hidden_suite_encryption_available ? "ok" : "bad"}
      />
      <Pill label="Publishing: not available yet" state="muted" />
    </div>
  );
}
