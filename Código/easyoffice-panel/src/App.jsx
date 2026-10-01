import { Routes, Route } from 'react-router-dom'
import { AuthProvider } from './lib/AuthContext.jsx'
import LogIn from './pages/LogIn.jsx'
import Panel from './pages/Panel.jsx'

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<LogIn />} />
        <Route path="/panel" element={<Panel />} />
      </Routes>
    </AuthProvider>
  )
}
