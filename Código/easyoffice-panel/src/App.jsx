import { Routes, Route } from 'react-router-dom'
import { AuthProvider } from './lib/AuthContext.jsx'
import Login from './pages/Login.jsx'
import Panel from './pages/Panel.jsx'

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<Login />} />
        <Route path="/panel" element={<Panel />} />
      </Routes>
    </AuthProvider>
  )
}
