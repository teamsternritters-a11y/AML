import { useAuth } from '../context/AuthContext'
import LoginPage from '../pages/LoginPage'

/**
 * Wraps children with authentication protection.
 * - session === undefined → still loading (shows subtle spinner)
 * - session === null      → not authenticated → shows LoginPage
 * - session is set        → renders children (the dashboard)
 */
export default function AuthGuard({ children }) {
  const { session } = useAuth()

  // Still resolving session from Supabase — avoid flash of wrong content
  if (session === undefined) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100vh',
        width: '100vw',
        background: 'linear-gradient(135deg, #0A1628 0%, #0E2040 100%)',
      }}>
        <div style={{
          width: '36px',
          height: '36px',
          border: '3px solid rgba(41,152,244,0.2)',
          borderTopColor: '#2998F4',
          borderRadius: '50%',
          animation: 'spin 0.8s linear infinite',
        }} />
      </div>
    )
  }

  if (!session) return <LoginPage />

  return children
}
