import React from 'react';
import { timeAgo } from './ContainerGrid';

function Pagination({ page, total, limit, onPageChange }) {
  const totalPages = Math.max(1, Math.ceil(total / limit));
  return (
    <div className="pagination">
      <button
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
      >
        ← Previous
      </button>
      <span className="page-info">
        Page {page} of {totalPages}
      </span>
      <button
        disabled={page >= totalPages}
        onClick={() => onPageChange(page + 1)}
      >
        Next →
      </button>
    </div>
  );
}

function IncidentFeed({ incidents, page, total, limit, onPageChange }) {
  if (!incidents || incidents.length === 0) {
    return (
      <div className="approval-empty">No incidents recorded yet</div>
    );
  }

  const severityBadge = (severity) => {
    const s = (severity || '').toUpperCase();
    if (s === 'CRITICAL') return 'badge badge-red';
    if (s === 'HIGH') return 'badge badge-yellow';
    return 'badge badge-blue';
  };

  const zoneBadge = (zone) => {
    if (zone === 'GREEN') return 'badge badge-green';
    if (zone === 'YELLOW') return 'badge badge-yellow';
    return 'badge badge-red';
  };

  return (
    <div>
      <div className="incident-list">
        {incidents.map((item, idx) => (
          <div className="incident-row" key={`${item.audit_timestamp}-${idx}`}>
            <div className="incident-left">
              <span className={severityBadge(item.severity)}>
                {item.severity || 'UNKNOWN'}
              </span>
            </div>
            <div className="incident-body">
              <div>
                <span className="incident-container">{item.target}</span>
                <span className="incident-type">{item.error_type}</span>
              </div>
              <div className="incident-cause">
                {item.root_cause || item.reasoning || '—'}
              </div>
            </div>
            <div className="incident-right">
              <span className="incident-time">
                {timeAgo(item.audit_timestamp)}
              </span>
              <span className={zoneBadge(item.zone)}>
                {item.zone}
              </span>
            </div>
          </div>
        ))}
      </div>
      <Pagination
        page={page}
        total={total}
        limit={limit}
        onPageChange={onPageChange}
      />
    </div>
  );
}

export default IncidentFeed;
