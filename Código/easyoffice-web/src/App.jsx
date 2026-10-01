import { Routes, Route } from 'react-router-dom'
import Home from './pages/Home.jsx'
import IniciarTramite from './pages/IniciarTramite.jsx'
import SeguimientoTramite from './pages/SeguimientoTramite.jsx'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/iniciar-tramite" element={<IniciarTramite />} />
      <Route path="/seguimiento" element={<SeguimientoTramite />} />
    </Routes>
  )
}
