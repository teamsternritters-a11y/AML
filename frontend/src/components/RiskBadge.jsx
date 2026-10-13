const LABELS = { ALLOW: 'ALLOW', OTP: 'OTP', HOLD: 'HOLD', BLOCK: 'BLOCK' }

export default function RiskBadge({ action }) {
  const label = LABELS[action] ?? action ?? '—'
  return <span className={`risk-badge ${label}`}>{label}</span>
}