import { Routes, Route, NavLink } from "react-router-dom";
import { useState, useEffect } from "react";
import { get } from "./api/client.js";
import LiveFeed from "./pages/LiveFeed.jsx";
import GraphExplorer from "./pages/GraphExplorer.jsx";
import CaseQueue from "./pages/CaseQueue.jsx";
import Metrics from "./pages/Metrics.jsx";
import {
  OverviewIcon,
  GraphIcon,
  CaseQueueIcon,
  MetricsIcon,
  AlertTriangleIcon,
} from "./components/Icons.jsx";
import { useAuth } from "./context/AuthContext.jsx";

const NAV = [
  { to: "/",        icon: OverviewIcon,  label: "Overview"      },
  { to: "/graph",   icon: GraphIcon,     label: "Graph Explorer" },
  { to: "/cases",   icon: CaseQueueIcon, label: "Case Queue"    },
  { to: "/metrics", icon: MetricsIcon,   label: "Metrics"        },
];

export default function App() {
  const [apiOk, setApiOk] = useState(null);
  const { user, signOut } = useAuth();
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
          <h1>SENTRIX<br />FRAUD &amp; AML</h1>
        </div>
        <div className="sidebar-section-label">NAVIGATION</div>
        <nav className="sidebar-nav">
          {NAV.map((n) => {
            const Icon = n.icon;
            return (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.to === "/"}
                className={({ isActive }) => "nav-link" + (isActive ? " active" : "")}
              >
                <span className="nav-icon">
                  <Icon size={19} />
                </span>
                <span className="nav-label">{n.label}</span>
              </NavLink>
            );
          })}
        </nav>
      </aside>

      <div className="main-area">
        <header className="topbar">
          <span className="topbar-demo">
            <AlertTriangleIcon size={13} style={{ display: "inline-block", verticalAlign: "middle", marginRight: "4px" }} />
            SYNTHETIC DEMO
          </span>
          <div className="topbar-right">
            <div className="topbar-status">
              <div className={`status-dot${apiOk === false ? " error" : ""}`} />
              {apiOk === null ? "Checking API…" : apiOk ? "API Online" : "API Offline"}
            </div>
            {user && (
              <>
                <span className="topbar-user">{user.email}</span>
                <button
                  className="btn-logout"
                  onClick={signOut}
                  title="Sign out"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
                    <polyline points="16 17 21 12 16 7"/>
                    <line x1="21" y1="12" x2="9" y2="12"/>
                  </svg>
                  Sign Out
                </button>
              </>
            )}
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