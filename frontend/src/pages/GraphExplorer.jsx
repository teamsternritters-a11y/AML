import React, { useState, useEffect, useRef, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import ForceGraph2D from 'react-force-graph-2d'
import { get } from '../api/client.js'
import LoadingState from '../components/LoadingState.jsx'

const SAMPLE_ACCOUNTS = ['ACC0996', 'ACC1193', 'ACC0001', 'ACC0042', 'ACC0500']

export default function GraphExplorer() {
  const [searchParams, setSearchParams] = useSearchParams()
  const initialAccount = searchParams.get('account_id') || 'ACC0996'

  const [accountId, setAccountId] = useState(initialAccount)
  const [hops, setHops] = useState(2)
  const [maxNodes, setMaxNodes] = useState(100)

  const [graphData, setGraphData] = useState(null)
  const [accountRisk, setAccountRisk] = useState(null)
  const [selectedNode, setSelectedNode] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [viewMode, setViewMode] = useState('canvas') // 'canvas' | 'table'

  const containerRef = useRef(null)
  const fgRef = useRef(null)
  const [dims, setDims] = useState({ width: 600, height: 500 })

  // Measure container dimensions
  useEffect(() => {
    const updateSize = () => {
      if (containerRef.current) {
        const { clientWidth, clientHeight } = containerRef.current
        setDims({
          width: clientWidth || 600,
          height: clientHeight || 500,
        })
      }
    }
    updateSize()
    window.addEventListener('resize', updateSize)
    return () => window.removeEventListener('resize', updateSize)
  }, [])

  // Fetch graph data
  const fetchGraph = async (targetId) => {
    if (!targetId || !targetId.trim()) return
    setLoading(true)
    setError(null)
    setSelectedNode(null)
    try {
      const res = await get('/graph', {
        account_id: targetId.trim(),
        hops,
        max_nodes: maxNodes,
      })

      setAccountRisk(res.account)

      const nodes = (res.neighborhood?.nodes || []).map((n) => ({
        id: n.id,
        graph_risk: n.graph_risk ?? 0.0,
        in_degree: n.in_degree ?? 0,
        out_degree: n.out_degree ?? 0,
      }))

      const links = (res.neighborhood?.edges || []).map((e) => ({
        source: e.source,
        target: e.target,
        amounts: e.amounts || [],
        transaction_ids: e.transaction_ids || [],
      }))

      setGraphData({ nodes, links, truncated: res.neighborhood?.truncated })
      setSearchParams({ account_id: targetId.trim() })
    } catch (err) {
      setError(err.message)
      setGraphData(null)
      setAccountRisk(null)
    } finally {
      setLoading(false)
    }
  }

  // Load on mount and when query params change
  useEffect(() => {
    const q = searchParams.get('account_id') || initialAccount
    setAccountId(q)
    fetchGraph(q)
  }, [searchParams.get('account_id')])

  const handleSubmit = (e) => {
    e.preventDefault()
    fetchGraph(accountId)
  }

  const handleSelectSample = (acc) => {
    setAccountId(acc)
    fetchGraph(acc)
  }

  // Node color mapping
  const getNodeColor = (node) => {
    if (node.id === accountId) return '#2563EB' // Royal Blue for search focal
    const r = node.graph_risk || 0
    if (r >= 0.5) return '#EF4444' // Red
    if (r >= 0.2) return '#F59E0B' // Amber
    return '#10B981' // Green
  }

  return (
    <div>
      {/* Header & Controls */}
      <div className="section-header">
        <div>
          <h2>Graph Network &amp; Mule Ring Explorer</h2>
          <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
            Directed multi-hop transaction topology, circular loops, and fan-in mule detection
          </span>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            type="button"
            className={`btn ${viewMode === 'canvas' ? 'btn-primary' : 'btn-ghost'}`}
            onClick={() => setViewMode('canvas')}
          >
            Force Graph
          </button>
          <button
            type="button"
            className={`btn ${viewMode === 'table' ? 'btn-primary' : 'btn-ghost'}`}
            onClick={() => setViewMode('table')}
          >
            Tabular View
          </button>
        </div>
      </div>

      {/* Query Bar */}
      <form onSubmit={handleSubmit} className="graph-controls">
        <input
          type="text"
          placeholder="Enter Account ID (e.g. ACC0996)…"
          value={accountId}
          onChange={(e) => setAccountId(e.target.value)}
        />
        <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '4px' }}>
          Hops:
          <select value={hops} onChange={(e) => setHops(Number(e.target.value))}>
            <option value={1}>1 Hop</option>
            <option value={2}>2 Hops</option>
            <option value={3}>3 Hops</option>
          </select>
        </label>
        <button type="submit" className="btn btn-primary" disabled={loading}>
          {loading ? 'Searching…' : 'Inspect Network'}
        </button>
      </form>

      {/* Sample Quick-Picks */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px', flexWrap: 'wrap' }}>
        <span style={{ fontSize: '12px', fontWeight: 700, color: 'var(--text-muted)' }}>Try Sample Accounts:</span>
        {SAMPLE_ACCOUNTS.map((acc) => (
          <button
            key={acc}
            type="button"
            className="pill"
            style={{ fontSize: '11px', padding: '3px 10px' }}
            onClick={() => handleSelectSample(acc)}
          >
            {acc}
          </button>
        ))}
      </div>

      {error && (
        <div className="error-box" style={{ marginBottom: '16px' }}>
          <strong>Graph Query Error:</strong> {error}
        </div>
      )}

      {/* Main Layout: Canvas + Inspector */}
      <div className="graph-page">
        {/* Left: Force Graph Canvas */}
        <div className="graph-canvas-wrap" ref={containerRef}>
          {loading ? (
            <div style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center',
              justifyContent: 'center', height: '100%', gap: '16px', color: 'var(--text-muted)',
            }}>
              <div style={{
                width: '40px', height: '40px', border: '4px solid var(--bg-light)',
                borderTopColor: 'var(--primary)', borderRadius: '50%',
                animation: 'spin 0.8s linear infinite',
              }} />
              <span style={{ fontSize: '14px', fontWeight: 600 }}>Loading graph data…</span>
              <span style={{ fontSize: '12px' }}>Traversing {hops}-hop neighborhood for <strong>{accountId}</strong></span>
            </div>
          ) : !graphData || graphData.nodes.length === 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)', gap: '10px' }}>
              <span style={{ fontSize: '32px' }}>🕸</span>
              <span>No graph data loaded. Search an account or select one above.</span>
            </div>
          ) : viewMode === 'canvas' ? (
            <>
              {graphData.truncated && (
                <div className="graph-fallback-banner">
                  Neighborhood was capped at {maxNodes} nodes to preserve interactive rendering.
                </div>
              )}
              <ForceGraph2D
                ref={fgRef}
                width={dims.width}
                height={dims.height}
                graphData={graphData}
                nodeId="id"
                nodeLabel={(node) =>
                  `${node.id}\nGraph Risk: ${(node.graph_risk * 100).toFixed(1)}%\nDegree: ${(node.in_degree || 0) + (node.out_degree || 0)}`
                }
                nodeColor={getNodeColor}
                nodeRelSize={6}
                nodeVal={(node) => (node.id === accountId ? 14 : 7)}
                nodeCanvasObject={(node, ctx, globalScale) => {
                  const label = node.id
                  const fontSize = 11 / globalScale
                  const isFocal = node.id === accountId
                  const isSelected = selectedNode?.id === node.id

                  ctx.beginPath()
                  ctx.arc(node.x, node.y, isFocal ? 7 : 5, 0, 2 * Math.PI, false)
                  ctx.fillStyle = getNodeColor(node)
                  ctx.fill()

                  if (isFocal || isSelected) {
                    ctx.strokeStyle = '#1E3A8A'
                    ctx.lineWidth = 2 / globalScale
                    ctx.stroke()
                  }

                  // Label
                  ctx.font = `${isFocal ? 'bold ' : ''}${fontSize}px sans-serif`
                  ctx.textAlign = 'center'
                  ctx.textBaseline = 'top'
                  ctx.fillStyle = isFocal ? '#1E3A8A' : '#476B9A'
                  ctx.fillText(label, node.x, node.y + (isFocal ? 9 : 7))
                }}
                linkDirectionalArrowLength={4}
                linkDirectionalArrowRelPos={1}
                linkColor={() => '#CBD5E1'}
                linkWidth={(link) => {
                  const totalAmt = (link.amounts || []).reduce((a, b) => a + b, 0)
                  return Math.min(Math.max(1, totalAmt / 5000), 5)
                }}
                onNodeClick={(node) => {
                  setSelectedNode(node)
                }}
                cooldownTicks={100}
                onEngineStop={() => {
                  if (fgRef.current) fgRef.current.zoomToFit(400, 20)
                }}
              />
              <div
                style={{
                  position: 'absolute',
                  bottom: '12px',
                  left: '12px',
                  background: 'rgba(255,255,255,0.92)',
                  padding: '8px 12px',
                  borderRadius: '8px',
                  border: '1px solid var(--border)',
                  fontSize: '11px',
                  display: 'flex',
                  gap: '12px',
                  alignItems: 'center',
                }}
              >
                <span><strong>Legend:</strong></span>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                  <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#2563EB' }} /> Focus Account
                </span>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                  <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#EF4444' }} /> High Risk (&ge;50%)
                </span>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                  <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#F59E0B' }} /> Med Risk (&ge;20%)
                </span>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                  <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#10B981' }} /> Normal
                </span>
              </div>
            </>
          ) : (
            /* Table Fallback View */
            <div style={{ padding: '16px', overflowY: 'auto', height: '100%' }}>
              <h3 style={{ fontSize: '14px', marginBottom: '8px' }}>Neighborhood Nodes ({graphData.nodes.length})</h3>
              <table style={{ marginBottom: '20px' }}>
                <thead>
                  <tr>
                    <th>Account ID</th>
                    <th>Graph Risk</th>
                    <th>In-Degree</th>
                    <th>Out-Degree</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {graphData.nodes.map((n) => (
                    <tr key={n.id} onClick={() => setSelectedNode(n)}>
                      <td style={{ fontWeight: 700 }}>{n.id}</td>
                      <td>{(n.graph_risk * 100).toFixed(1)}%</td>
                      <td>{n.in_degree ?? '—'}</td>
                      <td>{n.out_degree ?? '—'}</td>
                      <td>
                        <button
                          type="button"
                          className="btn btn-ghost"
                          style={{ padding: '2px 8px', fontSize: '11px' }}
                          onClick={() => handleSelectSample(n.id)}
                        >
                          Focus &rarr;
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <h3 style={{ fontSize: '14px', marginBottom: '8px' }}>Directed Transfers ({graphData.links.length})</h3>
              <table>
                <thead>
                  <tr>
                    <th>Source</th>
                    <th>Target</th>
                    <th>Transfers Count</th>
                    <th>Total Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {graphData.links.map((l, idx) => {
                    const total = (l.amounts || []).reduce((a, b) => a + b, 0)
                    return (
                      <tr key={idx}>
                        <td>{typeof l.source === 'object' ? l.source.id : l.source}</td>
                        <td>{typeof l.target === 'object' ? l.target.id : l.target}</td>
                        <td>{(l.amounts || []).length}</td>
                        <td>₹{total.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Right: Inspector Pane */}
        <div className="graph-inspector">
          {/* Focal Account Risk Summary */}
          {accountRisk && (
            <div className="card">
              <h3 style={{ fontSize: '14px', marginBottom: '10px', color: 'var(--text-heading)' }}>
                Focal Account: {accountRisk.account_id}
              </h3>
              <div className="kv-row">
                <span className="kv-label">Graph Risk Score</span>
                <span className="kv-value" style={{ color: accountRisk.graph_risk >= 0.5 ? 'var(--risk-high)' : 'var(--text-heading)' }}>
                  {(accountRisk.graph_risk * 100).toFixed(1)}%
                </span>
              </div>
              <div className="kv-row">
                <span className="kv-label">In-Degree (Senders)</span>
                <span className="kv-value">{accountRisk.in_degree}</span>
              </div>
              <div className="kv-row">
                <span className="kv-label">Out-Degree (Receivers)</span>
                <span className="kv-value">{accountRisk.out_degree}</span>
              </div>
              <div className="kv-row">
                <span className="kv-label">Total Degree</span>
                <span className="kv-value">{accountRisk.total_degree}</span>
              </div>

              <div style={{ marginTop: '12px' }}>
                <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                  Network Typology Flags
                </span>
                <div className="signal-row" style={{ marginTop: '6px' }}>
                  <span className={`signal-chip ${accountRisk.in_cycle ? 'active' : 'inactive'}`}>
                    {accountRisk.in_cycle ? 'Circular Flow' : 'No Loop'}
                  </span>
                  <span className={`signal-chip ${accountRisk.fan_in_flag ? 'active' : 'inactive'}`}>
                    {accountRisk.fan_in_flag ? 'Fan-In Mule' : 'Normal In-Flow'}
                  </span>
                  <span className={`signal-chip ${accountRisk.shared_device_flag ? 'active' : 'inactive'}`}>
                    {accountRisk.shared_device_flag ? 'Shared Device' : 'Clean Device'}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Node Selected in Graph */}
          {selectedNode && (
            <div className="card" style={{ borderColor: 'var(--primary)' }}>
              <h4 style={{ fontSize: '13px', marginBottom: '8px', color: 'var(--primary-dark)' }}>
                Selected Peer Node
              </h4>
              <div className="kv-row">
                <span className="kv-label">Account ID</span>
                <span className="kv-value">{selectedNode.id}</span>
              </div>
              <div className="kv-row">
                <span className="kv-label">Graph Risk Score</span>
                <span className="kv-value" style={{
                  fontWeight: 800,
                  fontSize: '16px',
                  color: selectedNode.graph_risk >= 0.5
                    ? 'var(--risk-high)'
                    : selectedNode.graph_risk >= 0.2
                    ? '#B45309'
                    : 'var(--risk-low)',
                }}>
                  {(selectedNode.graph_risk * 100).toFixed(1)}%
                  <span style={{ fontSize: '11px', fontWeight: 400, color: 'var(--text-muted)', marginLeft: '6px' }}>
                    {selectedNode.graph_risk >= 0.5 ? '— High Risk' : selectedNode.graph_risk >= 0.2 ? '— Medium Risk' : '— Normal'}
                  </span>
                </span>
              </div>
              <button
                type="button"
                className="btn btn-primary"
                style={{ width: '100%', marginTop: '10px', fontSize: '12px', justifyContent: 'center' }}
                onClick={() => handleSelectSample(selectedNode.id)}
              >
                Center Graph on {selectedNode.id} &rarr;
              </button>
            </div>
          )}

          {/* Topology Stats */}
          {graphData && (
            <div className="card">
              <h4 style={{ fontSize: '12px', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '8px' }}>
                Subgraph Statistics
              </h4>
              <div className="kv-row">
                <span className="kv-label">Total Accounts</span>
                <span className="kv-value">{graphData.nodes.length}</span>
              </div>
              <div className="kv-row">
                <span className="kv-label">Directed Channels</span>
                <span className="kv-value">{graphData.links.length}</span>
              </div>
              <div className="kv-row">
                <span className="kv-label">Search Depth</span>
                <span className="kv-value">{hops} hops</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
