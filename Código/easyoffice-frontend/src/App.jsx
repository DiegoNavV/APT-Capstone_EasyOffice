import { Routes, Route } from 'react-router-dom'
import { AuthProvider } from './lib/AuthContext.jsx'

import LogIn from './pages/LogIn.jsx'
import Solicitudes from './pages/Solicitudes.jsx'
import Tramites from './pages/Tramites.jsx'

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<LogIn />} />
        <Route path="/panel/tramites" element={<Tramites />} />
        <Route path="/panel/solicitudes" element={<Solicitudes />} />
      </Routes>
    </AuthProvider>
  )
}