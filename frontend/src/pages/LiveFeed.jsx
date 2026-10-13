import React, { useState, useMemo } from 'react'
import useApi from '../hooks/useApi.js'
import { post } from '../api/client.js'
import MetricCard from '../components/MetricCard.jsx'
import RiskBadge from '../components/RiskBadge.jsx'
import LoadingState from '../components/LoadingState.jsx'
import InvestigationDrawer from '../components/InvestigationDrawer.jsx'

export default function LiveFeed() {
  const [actionFilter, setActionFilter] = useState('ALL')
  const [search, setSearch] = useState('')
  const [selectedTx, setSelectedTx] = useState(null)
  const [isSimulating, setIsSimulating] = useState(false)
  const [simMessage, setSimMessage] = useState(null)

  // Poll transactions every 3 seconds
  const params = useMemo(() => ({ limit: 100 }), [])
  const { data, loading, error, refetch } = useApi('/transactions', params, { pollInterval: 3000 })

  const transactions = data?.items || []
  const totalCount = data?.total_count ?? transactions.length

  // Counts for metric cards
  const stats = useMemo(() => {
    let allow = 0
    let otp = 0
    let hold = 0
    let block = 0
    transactions.forEach((tx) => {
      const a = (tx.action || '').toUpperCase()
      if (a === 'ALLOW') allow++
      else if (a === 'OTP') otp++
      else if (a === 'HOLD') hold++
      else if (a === 'BLOCK') block++
    })
    return { allow, otpHold: otp + hold, block }
  }, [transactions])

  // Filtered transactions
  const filteredList = useMemo(() => {
    return transactions.filter((tx) => {
      if (actionFilter !== 'ALL' && (tx.action || '').toUpperCase() !== actionFilter) {
        return false
      }
      if (search.trim()) {
        const q = search.trim().toLowerCase()
        const txId = (tx.transaction_id || '').toLowerCase()
        const sId = (tx.sender_id || '').toLowerCase()
        const rId = (tx.receiver_id || '').toLowerCase()
        const city = (tx.city || '').toLowerCase()
        if (!txId.includes(q) && !sId.includes(q) && !rId.includes(q) && !city.includes(q)) {
          return false
        }
      }
      return true
    })
  }, [transactions, actionFilter, search])

  // ── Multi-Tier Simulation Pools (ALLOW, OTP, HOLD, BLOCK) ─────
  const SIMULATION_POOLS = {
    // Low risk (< 30) → ALLOW (clean accounts, low amounts, known devices)
    allow: [
      { sender_id: 'ACC0001', receiver_id: 'ACC0002', device_id: 'DEV_ACC0001_0', city: 'Mumbai',    amount_range: [200, 800] },
      { sender_id: 'ACC0050', receiver_id: 'ACC0060', device_id: 'DEV_ACC0050_0', city: 'Chennai',   amount_range: [150, 600] },
      { sender_id: 'ACC0100', receiver_id: 'ACC0200', device_id: 'DEV_ACC0100_0', city: 'Hyderabad', amount_range: [100, 450] },
      { sender_id: 'ACC0030', receiver_id: 'ACC0040', device_id: 'DEV_ACC0030_0', city: 'Kolkata',   amount_range: [250, 900] },
    ],
    // Medium-low risk (30 - 60) → OTP (moderate amounts, unfamiliar city or new device)
    otp: [
      { sender_id: 'ACC0001', receiver_id: 'ACC1451', device_id: 'DEV_ACC0001_0', city: 'Unknown',   amount_range: [8000, 11000] },
      { sender_id: 'ACC0050', receiver_id: 'ACC0248', device_id: 'DEV_ACC0050_0', city: 'Unknown',   amount_range: [10000, 13000] },
      { sender_id: 'ACC0001', receiver_id: 'ACC0002', device_id: 'DEV_NEW_80',    city: 'Unknown',   amount_range: [2500, 3500] },
    ],
    // Elevated risk (60 - 85) → HOLD (higher amounts, suspicious devices, medium graph flags)
    hold: [
      { sender_id: 'ACC0248', receiver_id: 'ACC1936', device_id: 'DEV_SHARED_44', city: 'Chennai',   amount_range: [7000, 9500] },
      { sender_id: 'ACC1451', receiver_id: 'ACC1799', device_id: 'DEV_BURNER_11', city: 'Offshore',  amount_range: [42000, 48000] },
      { sender_id: 'ACC1563', receiver_id: 'ACC0004', device_id: 'DEV_RING_02',   city: 'Unknown',   amount_range: [42000, 46000] },
      { sender_id: 'ACC0248', receiver_id: 'ACC1155', device_id: 'DEV_NEW_99',    city: 'Unknown',   amount_range: [32000, 36000] },
      { sender_id: 'ACC0093', receiver_id: 'ACC0111', device_id: 'DEV_SHARED_77', city: 'Unknown',   amount_range: [28000, 32000] },
    ],
    // Critical risk (85 - 100) → BLOCK with varied scores (85.9, 92.0, 92.6, 98.2, 99.5)
    block: [
      { sender_id: 'ACC0445', receiver_id: 'ACC0294', device_id: 'DEV_RING_05',        city: 'Mumbai',   amount_range: [18000, 22000] }, // ~85.9
      { sender_id: 'ACC0184', receiver_id: 'ACC0178', device_id: 'DEV_BURNER_01',       city: 'Unknown',  amount_range: [32000, 38000] }, // ~92.0
      { sender_id: 'ACC0445', receiver_id: 'ACC0294', device_id: 'DEV_RING_05',        city: 'Unknown',  amount_range: [28000, 34000] }, // ~92.6
      { sender_id: 'ACC1050', receiver_id: 'ACC1796', device_id: 'DEV_BURNER_RING_77', city: 'Offshore', amount_range: [70000, 80000] }, // ~98.2
      { sender_id: 'ACC0445', receiver_id: 'ACC0294', device_id: 'DEV_RING_BURNER_01', city: 'Unknown',  amount_range: [88000, 98000] }, // ~99.5
    ],
  }

  const randBetween = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min

  // Quick simulation — randomly picks across ALLOW (45%), OTP (25%), HOLD (15%), BLOCK (15%)
  const handleSimulate = async () => {
    setIsSimulating(true)
    setSimMessage(null)
    try {
      const rand = Math.floor(Math.random() * 900000) + 100000
      const roll = Math.random()
      let tier = 'allow'
      if (roll < 0.45) tier = 'allow'
      else if (roll < 0.70) tier = 'otp'
      else if (roll < 0.85) tier = 'hold'
      else tier = 'block'

      const pool = SIMULATION_POOLS[tier]
      const preset = pool[Math.floor(Math.random() * pool.length)]
      const amount = randBetween(...preset.amount_range)

      const tag = tier[0].toUpperCase()
      const payload = {
        transaction_id: `TX_LIVE_${tag}${rand}`,
        sender_id:      preset.sender_id,
        receiver_id:    preset.receiver_id,
        amount,
        device_id:      preset.device_id,
        city:           preset.city,
        timestamp:      new Date().toISOString(),
      }

      const res = await post('/score', payload)
      setSimMessage(`${payload.transaction_id}: ${res.action} — score ${res.risk_score}`)
      await refetch()
      setTimeout(() => setSimMessage(null), 5000)
    } catch (err) {
      setSimMessage(`Error: ${err.message}`)
    } finally {
      setIsSimulating(false)
    }
  }

  const formatAmount = (amt) => {
    if (typeof amt !== 'number') return amt ?? '—'
    return `₹${amt.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  }

  const formatTime = (iso) => {
    if (!iso) return '—'
    try {
      const d = new Date(iso)
      if (isNaN(d.getTime())) return iso
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    } catch {
      return iso
    }
  }

  return (
    <div>
      {/* Top Header & Simulation Controls */}
      <div className="section-header">
        <div>
          <h2>Real-Time Transaction Stream</h2>
          <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
            Continuous ingestion with millisecond multi-signal composite scoring
          </span>
        </div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          {simMessage && (
            <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--primary-dark)', background: 'var(--bg-selected)', padding: '4px 10px', borderRadius: '8px' }}>
              {simMessage}
            </span>
          )}
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleSimulate}
            disabled={isSimulating}
            title="Inject a random transaction (mix of normal & anomalous)"
          >
            {isSimulating ? '⏳ Scoring…' : '⚡ Simulate Transaction'}
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={refetch}
            title="Refresh stream"
          >
            ↻
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="metric-grid">
        <MetricCard label="Total Streamed" value={totalCount} sub="Live in-memory buffer" />
        <MetricCard label="Allow Decided" value={stats.allow} sub="Low risk (Score < 30)" />
        <MetricCard label="OTP / Hold Review" value={stats.otpHold} sub="Step-up & delayed settlement" />
        <MetricCard label="Block / Cases" value={stats.block} sub="Auto-escalated for compliance" />
      </div>

      {/* Filter Bar */}
      <div className="filter-bar">
        <input
          type="text"
          placeholder="Filter by Transaction ID, Sender, Receiver, or City…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div className="pill-group">
          {['ALL', 'ALLOW', 'OTP', 'HOLD', 'BLOCK'].map((p) => (
            <button
              key={p}
              type="button"
              className={`pill ${actionFilter === p ? 'active' : ''}`}
              onClick={() => setActionFilter(p)}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {/* Main Table / State */}
      {loading && transactions.length === 0 ? (
        <LoadingState message="Connecting to transaction feed…" />
      ) : error ? (
        <div className="error-box">
          <strong>Feed Error:</strong> {error}
        </div>
      ) : filteredList.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: '48px 24px' }}>
          <h3 style={{ color: 'var(--text-heading)', marginBottom: '8px' }}>No Transactions Found</h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '13px', marginBottom: '16px' }}>
            {transactions.length === 0
              ? 'No live transactions have been streamed yet. Use "Test Anomalous Tx" or run the replay script in the backend.'
              : 'No transactions match the selected filters.'}
          </p>
          {transactions.length === 0 && (
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleSimulate}
            >
              Inject Demo Transaction
            </button>
          )}
        </div>
      ) : (
        <div className="card" style={{ padding: 0 }}>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Transaction ID</th>
                  <th>Sender</th>
                  <th>Receiver</th>
                  <th>Amount</th>
                  <th>Risk Score</th>
                  <th>Action</th>
                  <th>Primary Reason</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {filteredList.map((tx, idx) => {
                  const isSelected = selectedTx?.transaction_id === tx.transaction_id
                  const score = typeof tx.risk_score === 'number' ? tx.risk_score : 0
                  const topReason = tx.reasons && tx.reasons.length > 0 ? tx.reasons[0] : 'Normal activity'

                  return (
                    <tr
                      key={tx.transaction_id || idx}
                      className={isSelected ? 'selected' : ''}
                      onClick={() => setSelectedTx(tx)}
                    >
                      <td style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                        {formatTime(tx.timestamp)}
                      </td>
                      <td style={{ fontWeight: 700, color: 'var(--text-heading)' }}>
                        {tx.transaction_id}
                      </td>
                      <td>{tx.sender_id || '—'}</td>
                      <td>{tx.receiver_id || '—'}</td>
                      <td style={{ fontWeight: 600 }}>{formatAmount(tx.amount)}</td>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span style={{ fontWeight: 800, width: '32px' }}>{score}</span>
                          <div
                            style={{
                              flex: 1,
                              maxWidth: '60px',
                              height: '6px',
                              background: 'var(--bg-light)',
                              borderRadius: '3px',
                              overflow: 'hidden',
                            }}
                          >
                            <div
                              style={{
                                width: `${Math.min(score, 100)}%`,
                                height: '100%',
                                background:
                                  score >= 85
                                    ? 'var(--risk-high)'
                                    : score >= 60
                                    ? 'var(--risk-medium)'
                                    : 'var(--primary)',
                              }}
                            />
                          </div>
                        </div>
                      </td>
                      <td>
                        <RiskBadge action={tx.action} />
                      </td>
                      <td style={{ fontSize: '12px', color: 'var(--text-body)', maxWidth: '240px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {topReason}
                      </td>
                      <td>
                        <button
                          type="button"
                          className="btn btn-ghost"
                          style={{ padding: '3px 8px', fontSize: '11px' }}
                          onClick={(e) => {
                            e.stopPropagation()
                            setSelectedTx(tx)
                          }}
                        >
                          Inspect &rarr;
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Investigation Drawer */}
      {selectedTx && (
        <InvestigationDrawer
          transaction={selectedTx}
          onClose={() => setSelectedTx(null)}
        />
      )}
    </div>
  )
}
