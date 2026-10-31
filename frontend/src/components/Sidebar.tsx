import { Link, useLocation } from "react-router-dom";
import {
  Bot,
  GitCompare,
  GitBranch,
  Home as HomeIcon,
  ListPlus,
  Rocket,
  ShieldCheck,
  Zap,
  type LucideIcon,
} from "lucide-react";

interface NavEntry {
  label: string;
  to: string | null; // null => disabled
  icon: LucideIcon;
  soon?: boolean;
}

function matchExecutionId(pathname: string): string | null {
  const m = pathname.match(/^\/executions\/([^/]+)/);
  return m ? m[1] : null;
}

function matchVersionId(pathname: string): string | null {
  const m = pathname.match(/\/compare\/([^/]+)/);
  return m ? m[1] : null;
}

function isActive(pathname: string, to: string): boolean {
  if (to === "/") return pathname === "/";
  return pathname === to || pathname.startsWith(to + "/");
}

function Item({ entry, pathname }: { entry: NavEntry; pathname: string }) {
  const Icon = entry.icon;
  if (entry.to === null) {
    return (
      <span className="nav-item disabled" aria-disabled="true">
        <Icon size={18} />
        {entry.label}
        {entry.soon && <span className="badge badge-neutral soon">soon</span>}
      </span>
    );
  }
  return (
    <Link
      to={entry.to}
      className={`nav-item ${isActive(pathname, entry.to) ? "active" : ""}`}
    >
      <Icon size={18} />
      {entry.label}
    </Link>
  );
}

export function Sidebar() {
  const { pathname } = useLocation();
  const executionId = matchExecutionId(pathname);
  const versionId = matchVersionId(pathname);

  const main: NavEntry[] = [
    { label: "Home", to: "/", icon: HomeIcon },
    { label: "New Task", to: "/new", icon: ListPlus },
  ];

  const run: NavEntry[] = [
    {
      label: "Run",
      to: executionId ? `/executions/${executionId}` : null,
      icon: GitBranch,
    },
    {
      label: "Compare",
      to:
        executionId && versionId
          ? `/executions/${executionId}/compare/${versionId}`
          : null,
      icon: GitCompare,
    },
    {
      label: "Verification",
      to: executionId ? `/executions/${executionId}/verification` : null,
      icon: ShieldCheck,
    },
  ];

  const other: NavEntry[] = [
    { label: "Publishing", to: "/publishing", icon: Rocket },
    { label: "Agent B", to: null, icon: Bot, soon: true },
  ];

  return (
    <aside className="sidebar">
      <Link to="/" className="sidebar-logo">
        <Zap size={20} />
        AutoEvolve
      </Link>

      <nav className="sidebar-nav" aria-label="Primary">
        {main.map((e) => (
          <Item key={e.label} entry={e} pathname={pathname} />
        ))}
        <div className="nav-group-label">Current run</div>
        {run.map((e) => (
          <Item key={e.label} entry={e} pathname={pathname} />
        ))}
        <div className="nav-group-label">More</div>
        {other.map((e) => (
          <Item key={e.label} entry={e} pathname={pathname} />
        ))}
      </nav>

      <div className="sidebar-foot">HTTP to FastAPI only · hidden tests stay sealed</div>
    </aside>
  );
}
