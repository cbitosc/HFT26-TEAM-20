import { Bot, Rocket } from "lucide-react";

function ComingCard({
  icon,
  title,
  children,
  glow,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
  glow?: string;
}) {
  return (
    <div className={`panel coming-card glow-transition ${glow ?? ""}`}>
      <span className="icon-wrap">{icon}</span>
      <div className="card-head" style={{ marginBottom: 0 }}>
        <h3>{title}</h3>
        <span className="badge badge-neutral">Not available yet</span>
      </div>
      <p className="hint" style={{ margin: 0 }}>
        {children}
      </p>
    </div>
  );
}

export function PublishingPlaceholder() {
  return (
    <section>
      <div className="panel">
        <h2>Publishing &amp; Agent B</h2>
        <p className="hint" style={{ margin: 0 }}>
          These workflows do not exist in the backend yet, so there is nothing
          to show. No sample or placeholder data is displayed — these cards will
          light up once the real pipelines ship.
        </p>
      </div>

      <div className="coming-grid">
        <ComingCard icon={<Rocket size={22} />} title="Publishing" glow="glow-blue">
          Zero-knowledge proof generation, IPFS publication and on-chain
          registration of an evidence bundle. Coming next.
        </ComingCard>
        <ComingCard icon={<Bot size={22} />} title="Agent B" glow="glow-purple">
          Cross-agent knowledge transfer and attestations, so a second agent can
          inherit what this run learned. Coming next.
        </ComingCard>
      </div>
    </section>
  );
}
