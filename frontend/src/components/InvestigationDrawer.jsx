import React from 'react'
import { useNavigate } from 'react-router-dom'
import RiskBadge from './RiskBadge.jsx'

export default function InvestigationDrawer({ transaction, onClose }) {
  const navigate = useNavigate()

  if (!transaction) return null

  const {
    transaction_id = '—',
    sender_id = '—',
    receiver_id = '—',
    amount = 0,
    device_id = '—',
    city = '—',
    timestamp = '—',
    risk_score = 0,
    action = 'ALLOW',
    model_risk = 0,
    graph_risk = 0,
    rules_risk = 0,
    reasons = [],
    rules_triggered = [],
    sender_graph_signals = {},
    receiver_graph_signals = {},
    case_id,
  } = transaction

  const formattedAmount = typeof amount === 'number'
    ? `₹${amount.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    : amount

  const getScoreColor = (s) => {
    if (s >= 85) return 'var(--risk-high)'
    if (s >= 60) return 'var(--risk-medium)'
    if (s >= 30) return 'var(--primary)'
    return 'var(--risk-low)'
  }

  const handleInspect = (accountId) => {
    if (accountId && accountId !== '—') {
      navigate(`/graph?account_id=${encodeURIComponent(accountId)}`)
      if (onClose) onClose()
    }
  }

  const handleViewCase = () => {
    navigate('/cases')
    if (onClose) onClose()
  }

  return (
    <>
      <div className="drawer-overlay" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true">
        <button className="drawer-close" onClick={onClose} aria-label="Close drawer">
          &times;
        </button>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingRight: '28px' }}>
          <div>
            <h3 style={{ margin: 0 }}>Transaction Analysis</h3>
            <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{transaction_id}</span>
          </div>
          <RiskBadge action={action} />
        </div>

        {/* Section 1: Overview & Parties */}
        <div className="drawer-section">
          <h4>Transaction Details</h4>
          <div className="kv-row">
            <span className="kv-label">Amount</span>
            <span className="kv-value" style={{ fontSize: '15px', color: 'var(--text-heading)' }}>
              {formattedAmount}
            </span>
          </div>
          <div className="kv-row">
            <span className="kv-label">Sender Account</span>
            <span className="kv-value" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span>{sender_id}</span>
              {sender_id !== '—' && (
                <button
                  type="button"
                  className="btn btn-ghost"
                  style={{ padding: '2px 6px', fontSize: '11px' }}
                  onClick={() => handleInspect(sender_id)}
                  title="Inspect sender in Graph Explorer"
                >
                  Graph ↗
                </button>
              )}
            </span>
          </div>
          <div className="kv-row">
            <span className="kv-label">Receiver Account</span>
            <span className="kv-value" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span>{receiver_id}</span>
              {receiver_id !== '—' && (
                <button
                  type="button"
                  className="btn btn-ghost"
                  style={{ padding: '2px 6px', fontSize: '11px' }}
                  onClick={() => handleInspect(receiver_id)}
                  title="Inspect receiver in Graph Explorer"
                >
                  Graph ↗
                </button>
              )}
            </span>
          </div>
          <div className="kv-row">
            <span className="kv-label">Device ID</span>
            <span className="kv-value">{device_id}</span>
          </div>
          <div className="kv-row">
            <span className="kv-label">Location</span>
            <span className="kv-value">{city}</span>
          </div>
          <div className="kv-row">
            <span className="kv-label">Timestamp</span>
            <span className="kv-value" style={{ fontSize: '12px' }}>{timestamp}</span>
          </div>
          {case_id && (
            <div className="kv-row" style={{ marginTop: '6px' }}>
              <span className="kv-label">Case File</span>
              <button
                type="button"
                className="btn btn-primary"
                style={{ padding: '3px 8px', fontSize: '11px' }}
                onClick={handleViewCase}
              >
                {case_id} &rarr;
              </button>
            </div>
          )}
        </div>

        {/* Section 2: Score Breakdown */}
        <div className="drawer-section">
          <h4>Risk Score Breakdown</h4>
          <div style={{ marginBottom: '12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '4px' }}>
              <span style={{ fontSize: '13px', fontWeight: 700, color: 'var(--text-heading)' }}>
                Composite Risk
              </span>
              <span style={{ fontSize: '20px', fontWeight: 800, color: getScoreColor(risk_score) }}>
                {risk_score} <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)' }}>/ 100</span>
              </span>
            </div>
            <div className="score-bar-track" style={{ height: '10px' }}>
              <div
                className="score-bar-fill"
                style={{
                  width: `${Math.min(Math.max(risk_score, 0), 100)}%`,
                  background: getScoreColor(risk_score),
                }}
              />
            </div>
          </div>

          <div className="score-bar-wrap">
            <span className="score-bar-label">ML Model (50%)</span>
            <div className="score-bar-track">
              <div
                className="score-bar-fill"
                style={{ width: `${Math.min(Math.round(model_risk * 100), 100)}%` }}
              />
            </div>
            <span style={{ fontSize: '12px', fontWeight: 600, width: '42px', textAlign: 'right' }}>
              {(model_risk * 100).toFixed(1)}%
            </span>
          </div>

          <div className="score-bar-wrap">
            <span className="score-bar-label">Graph (30%)</span>
            <div className="score-bar-track">
              <div
                className="score-bar-fill"
                style={{ width: `${Math.min(Math.round(graph_risk * 100), 100)}%` }}
              />
            </div>
            <span style={{ fontSize: '12px', fontWeight: 600, width: '42px', textAlign: 'right' }}>
              {(graph_risk * 100).toFixed(1)}%
            </span>
          </div>

          <div className="score-bar-wrap">
            <span className="score-bar-label">Rules (20%)</span>
            <div className="score-bar-track">
              <div
                className="score-bar-fill"
                style={{ width: `${Math.min(Math.round(rules_risk * 100), 100)}%` }}
              />
            </div>
            <span style={{ fontSize: '12px', fontWeight: 600, width: '42px', textAlign: 'right' }}>
              {(rules_risk * 100).toFixed(1)}%
            </span>
          </div>
        </div>

        {/* Section 3: Explainability Reasons */}
        <div className="drawer-section">
          <h4>SHAP &amp; Rule Explanations</h4>
          {reasons && reasons.length > 0 ? (
            <div>
              {reasons.map((r, i) => (
                <div key={i} className="reason-item">
                  <span className="reason-bullet">&#9679;</span>
                  <span>{r}</span>
                </div>
              ))}
            </div>
          ) : (
            <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
              No critical risk signals flagged for this transaction.
            </p>
          )}

          {rules_triggered && rules_triggered.length > 0 && (
            <div style={{ marginTop: '10px' }}>
              <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                Triggered Rule Conditions:
              </span>
              <div className="signal-row" style={{ marginTop: '4px' }}>
                {rules_triggered.map((rule, idx) => (
                  <span key={idx} className="signal-chip active" style={{ fontSize: '11px' }}>
                    {rule}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Section 4: Graph Signals */}
        <div className="drawer-section">
          <h4>Network Graph Signals</h4>
          <div style={{ marginBottom: '10px' }}>
            <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-heading)' }}>Sender Network:</span>
            <div className="signal-row">
              <span className={`signal-chip ${sender_graph_signals.in_cycle ? 'active' : 'inactive'}`}>
                {sender_graph_signals.in_cycle ? 'Circular Flow Detected' : 'No Cycle'}
              </span>
              <span className={`signal-chip ${sender_graph_signals.fan_in_flag ? 'active' : 'inactive'}`}>
                {sender_graph_signals.fan_in_flag ? 'High Fan-In Mule' : 'Normal Fan-In'}
              </span>
              <span className={`signal-chip ${sender_graph_signals.shared_device_flag ? 'active' : 'inactive'}`}>
                {sender_graph_signals.shared_device_flag ? 'Shared Device Ring' : 'Single Device'}
              </span>
            </div>
          </div>

          <div>
            <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-heading)' }}>Receiver Network:</span>
            <div className="signal-row">
              <span className={`signal-chip ${receiver_graph_signals.in_cycle ? 'active' : 'inactive'}`}>
                {receiver_graph_signals.in_cycle ? 'Circular Flow Detected' : 'No Cycle'}
              </span>
              <span className={`signal-chip ${receiver_graph_signals.fan_in_flag ? 'active' : 'inactive'}`}>
                {receiver_graph_signals.fan_in_flag ? 'High Fan-In Mule' : 'Normal Fan-In'}
              </span>
              <span className={`signal-chip ${receiver_graph_signals.shared_device_flag ? 'active' : 'inactive'}`}>
                {receiver_graph_signals.shared_device_flag ? 'Shared Device Ring' : 'Single Device'}
              </span>
            </div>
          </div>
        </div>

        {/* Section 5: Actions */}
        <div className="drawer-section" style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <button
            type="button"
            className="btn btn-primary"
            style={{ width: '100%', justifyContent: 'center' }}
            onClick={() => handleInspect(sender_id)}
          >
            Explore Sender Network Graph &rarr;
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            style={{ width: '100%', justifyContent: 'center' }}
            onClick={onClose}
          >
            Close Details
          </button>
        </div>
      </aside>
    </>
  )
}
