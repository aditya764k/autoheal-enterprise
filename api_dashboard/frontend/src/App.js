import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  getHealth,
  getContainers,
  getIncidents,
  getActions,
  getApprovals,
  getMetrics,
} from './api';
import ContainerGrid from './components/ContainerGrid';
import IncidentFeed from './components/IncidentFeed';
import ActionHistory from './components/ActionHistory';
import ApprovalPanel from './components/ApprovalPanel';
import MTTRChart from './components/MTTRChart';

const NAV_ITEMS = [
  { key: 'overview', label: 'Overview' },
  { key: 'incidents', label: 'Incidents' },
  { key: 'actions', label: 'Actions' },
  { key: 'approvals', label: 'Approvals' },
  { key: 'metrics', label: 'Metrics' },
];

const POLL_INTERVAL = 5000;

function timeAgoShort(isoString) {
  if (!isoString) return '';
  const diffSec = Math.max(0, Math.floor((Date.now() - new Date(isoString).getTime()) / 1000));
  if (diffSec < 5) return 'just now';
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  return `${Math.floor(diffMin / 60)}h ago`;
}

function App() {
  const [activeView, setActiveView] = useState('overview');
  const [online, setOnline] = useState(true);
  const [lastRefresh, setLastRefresh] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  // Data state — keep previous data visible during refresh
  const [containers, setContainers] = useState([]);
  const [incidents, setIncidents] = useState({ items: [], total: 0 });
  const [incidentPage, setIncidentPage] = useState(1);
  const [actions, setActions] = useState({ items: [], total: 0 });
  const [actionPage, setActionPage] = useState(1);
  const [approvals, setApprovals] = useState([]);
  const [metrics, setMetrics] = useState(null);

  const intervalRef = useRef(null);

  const fetchAll = useCallback(async () => {
    setRefreshing(true);

    const healthResult = await getHealth();
    if (healthResult.error) {
      setOnline(false);
      setRefreshing(false);
      return;
    }
    setOnline(true);

    const [cRes, iRes, aRes, apRes, mRes] = await Promise.all([
      getContainers(),
      getIncidents(incidentPage, 20),
      getActions(actionPage, 20),
      getApprovals(),
      getMetrics(),
    ]);

    if (cRes.data && !cRes.data[0]?.error) setContainers(cRes.data);
    if (iRes.data) setIncidents(iRes.data);
    if (aRes.data) setActions(aRes.data);
    if (apRes.data) setApprovals(apRes.data);
    if (mRes.data) setMetrics(mRes.data);

    setLastRefresh(new Date().toISOString());
    setRefreshing(false);
  }, [incidentPage, actionPage]);

  // Initial load + polling
  useEffect(() => {
    fetchAll();
    intervalRef.current = setInterval(fetchAll, POLL_INTERVAL);
    return () => clearInterval(intervalRef.current);
  }, [fetchAll]);

  const handleApprovalProcessed = (approvalId) => {
    setApprovals((prev) => prev.filter((a) => a.approval_id !== approvalId));
  };

  const pendingCount = approvals.length;

  const renderContent = () => {
    switch (activeView) {
      case 'overview':
        return (
          <>
            <ContainerGrid containers={containers} />
            {metrics && <MTTRChart metrics={metrics} />}
          </>
        );
      case 'incidents':
        return (
          <IncidentFeed
            incidents={incidents.items}
            page={incidentPage}
            total={incidents.total}
            limit={20}
            onPageChange={setIncidentPage}
          />
        );
      case 'actions':
        return (
          <ActionHistory
            actions={actions.items}
            page={actionPage}
            total={actions.total}
            limit={20}
            onPageChange={setActionPage}
          />
        );
      case 'approvals':
        return (
          <ApprovalPanel
            approvals={approvals}
            onApprovalProcessed={handleApprovalProcessed}
          />
        );
      case 'metrics':
        return <MTTRChart metrics={metrics} />;
      default:
        return null;
    }
  };

  const viewTitle = NAV_ITEMS.find((n) => n.key === activeView)?.label || '';

  return (
    <div className="app-layout">
      {/* ─── Sidebar ─────────────────────────────────────────────────────── */}
      <aside className="sidebar">
        <div className="sidebar-logo">
          <h1>AutoHeal</h1>
          <span>Enterprise Dashboard</span>
        </div>
        <nav className="sidebar-nav">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.key}
              className={`nav-item ${activeView === item.key ? 'active' : ''}`}
              onClick={() => setActiveView(item.key)}
            >
              {item.label}
              {item.key === 'approvals' && pendingCount > 0 && (
                <span
                  className="badge badge-yellow"
                  style={{ marginLeft: 8, fontSize: 10 }}
                >
                  {pendingCount}
                </span>
              )}
            </button>
          ))}
        </nav>
      </aside>

      {/* ─── Main ────────────────────────────────────────────────────────── */}
      <main className="main-content">
        <div className="main-header">
          <h2>{viewTitle}</h2>
          <div className="refresh-status">
            {online && <div className="pulse-dot" />}
            {refreshing
              ? 'Refreshing…'
              : lastRefresh
                ? `Updated ${timeAgoShort(lastRefresh)}`
                : ''}
          </div>
        </div>

        {!online && (
          <div className="offline-banner">
            Pipeline offline — API server is not responding. Check that uvicorn is running on port 8000.
          </div>
        )}

        {renderContent()}
      </main>
    </div>
  );
}

export default App;
