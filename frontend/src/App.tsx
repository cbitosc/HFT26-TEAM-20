import { Route, Routes, useLocation } from "react-router-dom";
import { Sidebar } from "./components/Sidebar";
import { StatusStrip } from "./components/StatusStrip";
import { ThemeToggle } from "./components/ThemeToggle";
import { Home } from "./screens/Home";
import { NewTask } from "./screens/NewTask";
import { RunView } from "./screens/RunView";
import { CompareView } from "./screens/CompareView";
import { Verification } from "./screens/Verification";
import { PublishingPlaceholder } from "./screens/Placeholder";
import { AgentB } from "./screens/AgentB";

const TITLES: { test: (p: string) => boolean; title: string }[] = [
  { test: (p) => p === "/", title: "Home" },
  { test: (p) => p === "/new", title: "New Task" },
  { test: (p) => p === "/publishing", title: "Publishing" },
  { test: (p) => p === "/agent-b", title: "Agent B" },
  { test: (p) => /\/compare\//.test(p), title: "Compare" },
  { test: (p) => /\/verification$/.test(p), title: "Verification" },
  { test: (p) => /^\/executions\//.test(p), title: "Run" },
];

function pageTitle(pathname: string): string {
  return TITLES.find((t) => t.test(pathname))?.title ?? "AutoEvolve";
}

export function App() {
  const { pathname } = useLocation();

  return (
    <div className="app-shell">
      <Sidebar />
      <header className="topbar">
        <h1 style={{ fontSize: "var(--fs-lg)", margin: 0 }}>{pageTitle(pathname)}</h1>
        <div className="topbar-right">
          <StatusStrip />
          <ThemeToggle />
        </div>
      </header>

      <main className="content">
        <div className="content-inner">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/new" element={<NewTask />} />
            <Route path="/executions/:executionId" element={<RunView />} />
            <Route
              path="/executions/:executionId/compare/:versionId"
              element={<CompareView />}
            />
            <Route
              path="/executions/:executionId/verification"
              element={<Verification />}
            />
            <Route path="/publishing" element={<PublishingPlaceholder />} />
          <Route path="/agent-b" element={<AgentB />} />
            <Route
              path="*"
              element={<div className="panel">Page not found.</div>}
            />
          </Routes>
        </div>
      </main>
    </div>
  );
}
