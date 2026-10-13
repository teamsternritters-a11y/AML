import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext.jsx'
import AuthGuard from './components/AuthGuard.jsx'
import App from './App.jsx'
import './styles/global.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <AuthGuard>
          <App />
        </AuthGuard>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
)