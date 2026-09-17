import React, { useState } from 'react';
import { postApprove } from '../api';
import { timeAgo } from './ContainerGrid';

function formatAction(action) {
  if (!action) return '—';
  return action
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function ApprovalCard({ item, onProcessed }) {
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState(null);
  const [fading, setFading] = useState(false);

  const handleAction = async (approved) => {
    setProcessing(true);
    setError(null);

    // Optimistic: start fading immediately
    setFading(true);

    const { data, error: apiError } = await postApprove(
      item.approval_id,
      approved
    );

    if (apiError || (data && data.status === 'error')) {
      // Restore on error
      setFading(false);
      setProcessing(false);
      setError(apiError || data?.detail || 'Failed — try again');
      return;
    }

    // Let fade animation complete, then remove
    setTimeout(() => {
      onProcessed(item.approval_id);
    }, 300);
  };

  const severityBadge = (severity) => {
    const s = (severity || '').toUpperCase();
    if (s === 'CRITICAL') return 'badge badge-red';
    if (s === 'HIGH') return 'badge badge-yellow';
    return 'badge badge-blue';
  };

  return (
    <div className={`approval-card ${fading ? 'fading' : ''}`}>
      <div className="approval-header">
        <span className="container-name">{item.target}</span>
        <span className={severityBadge(item.severity)}>
          {item.severity}
        </span>
        <span className="incident-time" style={{ marginLeft: 'auto' }}>
          {timeAgo(item.audit_timestamp)}
        </span>
      </div>
      <div className="approval-body">
        <div className="approval-field">
          <span className="approval-field-label">Action:</span>
          <span className="approval-field-value">
            {formatAction(item.action)}
          </span>
        </div>
        <div className="approval-field">
          <span className="approval-field-label">Confidence:</span>
          <span className="approval-field-value">
            {item.confidence != null
              ? `${Math.round(item.confidence * 100)}%`
              : '—'}
          </span>
        </div>
        <div className="approval-field">
          <span className="approval-field-label">Root Cause:</span>
          <span className="approval-field-value">
            {item.root_cause || '—'}
          </span>
        </div>
        <div className="approval-field">
          <span className="approval-field-label">Reasoning:</span>
          <span className="approval-field-value">
            {item.reasoning || '—'}
          </span>
        </div>
      </div>
      <div className="approval-footer">
        {processing ? (
          <span className="approval-processing">Processing…</span>
        ) : (
          <>
            <button
              className="btn-approve"
              disabled={processing}
              onClick={() => handleAction(true)}
            >
              Approve
            </button>
            <button
              className="btn-reject"
              disabled={processing}
              onClick={() => handleAction(false)}
            >
              Reject
            </button>
          </>
        )}
      </div>
      {error && <div className="approval-error">{error}</div>}
    </div>
  );
}

function ApprovalPanel({ approvals, onApprovalProcessed }) {
  if (!approvals || approvals.length === 0) {
    return <div className="approval-empty">No pending approvals</div>;
  }

  return (
    <div>
      {approvals.map((item) => (
        <ApprovalCard
          key={item.approval_id}
          item={item}
          onProcessed={onApprovalProcessed}
        />
      ))}
    </div>
  );
}

export default ApprovalPanel;
