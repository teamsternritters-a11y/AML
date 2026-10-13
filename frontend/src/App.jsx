import { Routes, Route, NavLink, useNavigate } from "react-router-dom";
import { useState, useEffect } from "react";
import { get } from "./api/client.js";
import LiveFeed from "./pages/LiveFeed.jsx";
import GraphExplorer from "./pages/GraphExplorer.jsx";
import CaseQueue from "./pages/CaseQueue.jsx";
import Metrics from "./pages/Metrics.jsx";

const NAV = [
  { to: "/",        icon: "⚡", label: "Live Feed"      },
  { to: "/graph",   icon: "🕸",  label: "Graph Explorer" },
  { to: "/cases",   icon: "📋", label: "Cases"          },
  { to: "/metrics", icon: "📊", label: "Metrics"        },
];

export default function App() {
  const [apiOk, setApiOk] = useState(null);

  useEffect(() => {
    const check = () =>
      get("/health")
        .then(() => setApiOk(true))
        .catch(() => setApiOk(false));
    check();
    const t = setInterval(check, 15000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <h1>SYNESIS 26<br />FRAUD &amp; AML</h1>
        </div>
        <nav className="sidebar-nav">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.to === "/"}
              className={({ isActive }) => "nav-link" + (isActive ? " active" : "")}
            >
              <span className="nav-icon">{n.icon}</span>
              {n.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="main-area">
        <header className="topbar">
          <span className="topbar-demo">⚠ SYNTHETIC DEMO</span>
          <div className="topbar-status">
            <div className={`status-dot${apiOk === false ? " error" : ""}`} />
            {apiOk === null ? "Checking API…" : apiOk ? "API Online" : "API Offline"}
          </div>
        </header>
        <main className="page-content">
          <Routes>
            <Route path="/"        element={<LiveFeed />}      />
            <Route path="/graph"   element={<GraphExplorer />} />
            <Route path="/cases"   element={<CaseQueue />}     />
            <Route path="/metrics" element={<Metrics />}       />
          </Routes>
        </main>
      </div>
    </div>
  );
}