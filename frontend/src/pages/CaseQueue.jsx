import React, { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import useApi from '../hooks/useApi.js'
import { post } from '../api/client.js'
import RiskBadge from '../components/RiskBadge.jsx'
import LoadingState from '../components/LoadingState.jsx'

export default function CaseQueue() {
  const navigate = useNavigate()
  const [statusFilter, setStatusFilter] = useState('ALL') // 'ALL' | 'open' | 'closed'
  const [selectedCaseId, setSelectedCaseId] = useState(null)
  const [decisionNote, setDecisionNote] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [actionError, setActionError] = useState(null)
  const [successMessage, setSuccessMessage] = useState(null)

  const params = useMemo(() => {
    return statusFilter === 'ALL' ? { limit: 100 } : { status: statusFilter, limit: 100 }
  }, [statusFilter])

  const { data, loading, error, refetch } = useApi('/cases', params, { pollInterval: 4000 })
  const cases = data?.items || []

  // Ensure selected case is resolved
  const selectedCase = useMemo(() => {
    if (!selectedCaseId && cases.length > 0) return cases[0]
    return cases.find((c) => c.case_id === selectedCaseId) || cases[0] || null
  }, [cases, selectedCaseId])

  const handleDecision = async (decision) => {
    if (!selectedCase) return
    setIsSubmitting(true)
    setActionError(null)
    setSuccessMessage(null)
    try {
      await post(`/cases/${selectedCase.case_id}/decision`, {
        decision,
        note: decisionNote.trim() || `Adjudicated as ${decision} via Compliance Console`,
      })
      setDecisionNote('')
      setSuccessMessage('Decision recorded successfully')
      setTimeout(() => setSuccessMessage(null), 3000)
      await refetch()
    } catch (err) {
      setActionError(err.message)
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleInspectGraph = (accId) => {
    if (accId) {
      navigate(`/graph?account_id=${encodeURIComponent(accId)}`)
    }
  }

  return (
    <div>
      <div className="section-header">
        <div>
          <h2>AML &amp; Fraud Compliance Case Queue</h2>
          <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
            Investigation inbox for transactions flagged with BLOCK or high-risk topology
          </span>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={refetch}
            title="Refresh case list"
          >
            ↻ Refresh
          </button>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="filter-bar">
        <div className="pill-group">
          {[
            { id: 'ALL', label: `All Cases (${cases.length})` },
            { id: 'open', label: 'Open / Pending' },
            { id: 'closed', label: 'Closed / Adjudicated' },
          ].map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={`pill ${statusFilter === tab.id ? 'active' : ''}`}
              onClick={() => setStatusFilter(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {loading && cases.length === 0 ? (
        <LoadingState message="Fetching compliance cases…" />
      ) : error ? (
        <div className="error-box">
          <strong>Failed to load cases:</strong> {error}
        </div>
      ) : cases.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: '60px 24px' }}>
          <h3 style={{ marginBottom: '8px', color: 'var(--text-heading)' }}>No Cases in Queue</h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '13px', marginBottom: '16px' }}>
            {statusFilter === 'open'
              ? 'Zero open alerts pending compliance adjudication.'
              : 'No compliance cases have been created yet. Transactions evaluated with action=BLOCK are automatically queued here.'}
          </p>
        </div>
      ) : (
        <div className="cases-layout">
          {/* Left: Case List */}
          <div className="case-list">
            {cases.map((c) => {
              const isSelected = selectedCase?.case_id === c.case_id
              return (
                <div
                  key={c.case_id}
                  className={`case-item ${isSelected ? 'selected' : ''}`}
                  onClick={() => setSelectedCaseId(c.case_id)}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                    <strong style={{ fontSize: '13px', color: 'var(--text-heading)' }}>
                      {c.case_id}
                    </strong>
                    <span className={`status-chip ${c.status || 'open'}`}>
                      {c.status || 'open'}
                    </span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '12px' }}>
                    <span style={{ color: 'var(--text-muted)' }}>Sender: {c.sender_id}</span>
                    <RiskBadge action={c.action} />
                  </div>
                  <div style={{ marginTop: '4px', fontSize: '11px', color: 'var(--text-muted)' }}>
                    Risk Score: <strong>{c.risk_score}</strong>
                  </div>
                </div>
              )
            })}
          </div>

          {/* Right: Case Details & Adjudication */}
          {selectedCase ? (
            <div className="case-detail">
              {/* Header */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: '1px solid var(--border)', paddingBottom: '16px' }}>
                <div>
                  <h3 style={{ margin: 0, fontSize: '18px', color: 'var(--text-heading)' }}>
                    Case File: {selectedCase.case_id}
                  </h3>
                  <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                    Triggered by Transaction: <strong>{selectedCase.transaction_id}</strong>
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <RiskBadge action={selectedCase.action} />
                  <span className={`status-chip ${selectedCase.status}`}>
                    {selectedCase.status?.toUpperCase()}
                  </span>
                </div>
              </div>

              {/* Entity & Transaction Metadata */}
              <div>
                <h4 style={{ fontSize: '12px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '10px' }}>
                  Entity Information
                </h4>
                <div className="kv-row">
                  <span className="kv-label">Target Sender Account</span>
                  <span className="kv-value" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    {selectedCase.sender_id}
                    <button
                      type="button"
                      className="btn btn-ghost"
                      style={{ padding: '2px 8px', fontSize: '11px' }}
                      onClick={() => handleInspectGraph(selectedCase.sender_id)}
                    >
                      Inspect in Graph &rarr;
                    </button>
                  </span>
                </div>
                <div className="kv-row">
                  <span className="kv-label">Overall Risk Score</span>
                  <span className="kv-value" style={{ color: 'var(--risk-high)', fontSize: '16px' }}>
                    {selectedCase.risk_score} / 100
                  </span>
                </div>
                <div className="kv-row">
                  <span className="kv-label">Flagged At</span>
                  <span className="kv-value" style={{ fontSize: '12px' }}>
                    {selectedCase.created_at || '—'}
                  </span>
                </div>
              </div>

              {/* Suspicion Grounds */}
              <div>
                <h4 style={{ fontSize: '12px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '10px' }}>
                  Evidence &amp; Reason Codes
                </h4>
                {selectedCase.reasons && selectedCase.reasons.length > 0 ? (
                  <div>
                    {selectedCase.reasons.map((r, i) => (
                      <div key={i} className="reason-item">
                        <span className="reason-bullet">&#9679;</span>
                        <span style={{ fontSize: '13px' }}>{r}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                    Triggered high severity threshold during orchestration pipeline.
                  </p>
                )}
              </div>

              {/* Graph Signals */}
              <div>
                <h4 style={{ fontSize: '12px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '10px' }}>
                  Graph Anomaly Signals
                </h4>
                <div className="signal-row">
                  <span className={`signal-chip ${selectedCase.sender_graph_signals?.in_cycle ? 'active' : 'inactive'}`}>
                    {selectedCase.sender_graph_signals?.in_cycle ? 'Circular Transfer Detected' : 'No Loop'}
                  </span>
                  <span className={`signal-chip ${selectedCase.sender_graph_signals?.fan_in_flag ? 'active' : 'inactive'}`}>
                    {selectedCase.sender_graph_signals?.fan_in_flag ? 'High Fan-In Inflow' : 'Normal Fan-In'}
                  </span>
                  <span className={`signal-chip ${selectedCase.sender_graph_signals?.shared_device_flag ? 'active' : 'inactive'}`}>
                    {selectedCase.sender_graph_signals?.shared_device_flag ? 'Shared Device Ring' : 'No Device Sharing'}
                  </span>
                </div>
              </div>

              {/* Adjudication Panel */}
              {actionError && (
                <div className="error-box" style={{ fontSize: '12px' }}>
                  {actionError}
                </div>
              )}
              {successMessage && (
                <div style={{
                  display: 'flex', alignItems: 'center', gap: '8px',
                  background: '#DCFCE7', border: '1px solid #86EFAC',
                  borderRadius: '8px', padding: '10px 14px', fontSize: '13px',
                  fontWeight: 600, color: '#15803D', animation: 'fadeIn 0.2s ease',
                }}>
                  <span>✓</span> {successMessage}
                </div>
              )}

              {selectedCase.status === 'open' ? (
                <div className="decision-area">
                  <h4 style={{ fontSize: '13px', fontWeight: 800, color: 'var(--text-heading)' }}>
                    Compliance Officer Adjudication
                  </h4>
                  <textarea
                    rows={3}
                    placeholder="Enter case notes, investigator justification, or AML disposition rationale…"
                    value={decisionNote}
                    onChange={(e) => setDecisionNote(e.target.value)}
                  />
                  <div className="decision-btns">
                    <button
                      type="button"
                      className="btn btn-success"
                      onClick={() => handleDecision('approve')}
                      disabled={isSubmitting}
                    >
                      {isSubmitting ? 'Saving…' : '✓ Release & Approve Transaction'}
                    </button>
                    <button
                      type="button"
                      className="btn btn-danger"
                      onClick={() => handleDecision('reject')}
                      disabled={isSubmitting}
                    >
                      {isSubmitting ? 'Saving…' : '✕ Confirm Block & Escalate SAR'}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="decision-area" style={{ background: '#F8FAFC', border: '1px solid var(--border)' }}>
                  <h4 style={{ fontSize: '13px', fontWeight: 800, color: 'var(--text-heading)' }}>
                    Adjudication Outcome
                  </h4>
                  <div className="kv-row">
                    <span className="kv-label">Final Decision</span>
                    <strong style={{ color: selectedCase.reviewer_decision === 'approve' ? 'var(--risk-low)' : 'var(--risk-high)', textTransform: 'uppercase' }}>
                      {selectedCase.reviewer_decision}
                    </strong>
                  </div>
                  <div className="kv-row">
                    <span className="kv-label">Reviewer Notes</span>
                    <span className="kv-value">{selectedCase.reviewer_note || 'None recorded'}</span>
                  </div>
                  <div className="kv-row">
                    <span className="kv-label">Adjudicated At</span>
                    <span className="kv-value" style={{ fontSize: '12px' }}>
                      {selectedCase.reviewed_at || '—'}
                    </span>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="case-empty">
              Select a case from the list on the left to begin investigation.
            </div>
          )}
        </div>
      )}
    </div>
  )
}
