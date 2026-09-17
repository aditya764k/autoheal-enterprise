/**
 * Format uptime_seconds → "Up 2h 14m" or "Up 3m" or "Down"
 */
export function formatUptime(seconds) {
  if (!seconds || seconds <= 0) return 'Down';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `Up ${h}h ${m}m`;
  return `Up ${m}m`;
}

function ContainerGrid({ containers }) {
  if (!containers || containers.length === 0) {
    return null;
  }

  const healthClass = (h) => {
    if (h === 'GREEN') return 'health-green';
    if (h === 'YELLOW') return 'health-yellow';
    return 'health-red';
  };

  const statusLabel = (s) => {
    if (s === 'running') return 'Running';
    if (s === 'restarting') return 'Restarting';
    if (s === 'exited') return 'Exited';
    return s;
  };

  const badgeClass = (h) => {
    if (h === 'GREEN') return 'badge badge-green';
    if (h === 'YELLOW') return 'badge badge-yellow';
    return 'badge badge-red';
  };

  return (
    <div className="container-grid">
      {containers.map((c) => (
        <div
          key={c.container_id || c.name}
          className={`container-card ${healthClass(c.health)}`}
        >
          <div className="container-name">{c.name}</div>
          <div className="container-image">{c.image}</div>
          <span className={badgeClass(c.health)}>
            {statusLabel(c.status)}
          </span>
          <div className="container-meta">
            <span className="container-uptime">{formatUptime(c.uptime_seconds)}</span>
            <span className="container-last-incident">
              {c.last_incident ? timeAgo(c.last_incident) : 'No incidents'}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * Simple relative time: "3 minutes ago", "2 hours ago", etc.
 */
function timeAgo(isoString) {
  if (!isoString) return '';
  const now = Date.now();
  const then = new Date(isoString).getTime();
  const diffSec = Math.max(0, Math.floor((now - then) / 1000));

  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin} minute${diffMin === 1 ? '' : 's'} ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr} hour${diffHr === 1 ? '' : 's'} ago`;
  const diffDays = Math.floor(diffHr / 24);
  return `${diffDays} day${diffDays === 1 ? '' : 's'} ago`;
}

export { timeAgo };
export default ContainerGrid;
