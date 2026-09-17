import React from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';

function CustomTooltip({ active, payload }) {
  if (!active || !payload || !payload.length) return null;
  const data = payload[0].payload;
  return (
    <div
      style={{
        background: 'var(--bg-tertiary)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-sm)',
        padding: '8px 12px',
        fontSize: '12px',
        fontFamily: 'var(--font-mono)',
      }}
    >
      <div style={{ color: 'var(--text-primary)' }}>
        Avg MTTR: {Math.round(data.avg_mttr_seconds)}s
      </div>
      <div style={{ color: 'var(--text-secondary)', marginTop: '2px' }}>
        {data.count} incident{data.count === 1 ? '' : 's'}
      </div>
    </div>
  );
}

function formatDate(dateStr) {
  if (!dateStr) return '';
  const parts = dateStr.split('-');
  if (parts.length < 3) return dateStr;
  const months = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
  ];
  const monthIdx = parseInt(parts[1], 10) - 1;
  return `${months[monthIdx] || parts[1]} ${parseInt(parts[2], 10)}`;
}

function MTTRChart({ metrics }) {
  if (!metrics) return null;

  const chartData = (metrics.mttr_by_day || []).map((d) => ({
    ...d,
    label: formatDate(d.date),
  }));

  return (
    <div>
      <div className="mttr-chart-wrapper">
        {chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
              <CartesianGrid
                stroke="var(--border)"
                strokeDasharray=""
                vertical={false}
              />
              <XAxis
                dataKey="label"
                tick={{
                  fill: 'var(--text-secondary)',
                  fontSize: 11,
                  fontFamily: 'var(--font-mono)',
                }}
                axisLine={{ stroke: 'var(--border)' }}
                tickLine={false}
              />
              <YAxis
                tickFormatter={(v) => `${Math.round(v)}s`}
                tick={{
                  fill: 'var(--text-secondary)',
                  fontSize: 11,
                  fontFamily: 'var(--font-mono)',
                }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip content={<CustomTooltip />} />
              <Line
                type="monotone"
                dataKey="avg_mttr_seconds"
                stroke="var(--green)"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, fill: 'var(--green)' }}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div
            className="approval-empty"
            style={{ padding: '48px 0' }}
          >
            No MTTR data yet — incidents will appear here
          </div>
        )}
      </div>

      <div className="stat-boxes">
        <div className="stat-box">
          <div className="stat-number">{metrics.total_incidents ?? 0}</div>
          <div className="stat-label">Total Incidents</div>
        </div>
        <div className="stat-box">
          <div className="stat-number">{metrics.auto_remediated ?? 0}</div>
          <div className="stat-label">Auto-Remediated</div>
        </div>
        <div className="stat-box">
          <div className="stat-number">
            {metrics.avg_mttr_seconds
              ? `${Math.round(metrics.avg_mttr_seconds)}s`
              : '—'}
          </div>
          <div className="stat-label">Avg MTTR</div>
        </div>
      </div>
    </div>
  );
}

export default MTTRChart;
