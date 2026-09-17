import React from 'react';
import { timeAgo } from './ContainerGrid';

function Pagination({ page, total, limit, onPageChange }) {
  const totalPages = Math.max(1, Math.ceil(total / limit));
  return (
    <div className="pagination">
      <button disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
        ← Previous
      </button>
      <span className="page-info">
        Page {page} of {totalPages}
      </span>
      <button disabled={page >= totalPages} onClick={() => onPageChange(page + 1)}>
        Next →
      </button>
    </div>
  );
}

function formatAction(action) {
  if (!action) return '—';
  return action
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatDuration(ms) {
  if (!ms && ms !== 0) return '—';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function ActionHistory({ actions, page, total, limit, onPageChange }) {
  if (!actions || actions.length === 0) {
    return (
      <div className="approval-empty">No actions recorded yet</div>
    );
  }

  const zoneBadge = (zone) => {
    if (zone === 'GREEN') return 'badge badge-green';
    if (zone === 'YELLOW') return 'badge badge-yellow';
    return 'badge badge-red';
  };

  return (
    <div>
      <table className="action-table">
        <thead>
          <tr>
            <th>Time</th>
            <th>Container</th>
            <th>Action</th>
            <th>Zone</th>
            <th>Result</th>
            <th>Duration</th>
          </tr>
        </thead>
        <tbody>
          {actions.map((item, idx) => {
            const execResult = item.execution_result;
            const success = execResult?.success;
            const durationMs = execResult?.duration_ms;

            return (
              <tr key={`${item.audit_timestamp}-${idx}`}>
                <td className="mono">{timeAgo(item.audit_timestamp)}</td>
                <td className="mono">{item.target}</td>
                <td>{formatAction(item.action)}</td>
                <td>
                  <span className={zoneBadge(item.zone)}>{item.zone}</span>
                </td>
                <td>
                  {execResult ? (
                    success ? (
                      <span className="result-success">✓ Success</span>
                    ) : (
                      <span className="result-fail">✗ Failed</span>
                    )
                  ) : (
                    <span style={{ color: 'var(--text-tertiary)' }}>—</span>
                  )}
                </td>
                <td className="mono">
                  {execResult ? formatDuration(durationMs) : '—'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <Pagination
        page={page}
        total={total}
        limit={limit}
        onPageChange={onPageChange}
      />
    </div>
  );
}

export default ActionHistory;
