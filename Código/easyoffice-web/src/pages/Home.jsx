import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import Header from '../components/Header.jsx'
import Hero from '../components/Hero.jsx'
import AboutStats from '../components/AboutStats.jsx'
import Servicios from '../components/Servicios.jsx'
import Footer from '../components/Footer.jsx'
import IniciarTramiteModal from '../components/IniciarTramiteModal.jsx'

export default function Home() {
  const [modalAbierto, setModalAbierto] = useState(false)
  const { hash } = useLocation()

  // Si se llega desde otra página con una sección (por ejemplo /#contabilidad), baja hasta ella.
  useEffect(() => {
    if (!hash) return
    const el = document.getElementById(decodeURIComponent(hash.slice(1)))
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [hash])

  return (
    <div className="min-h-screen flex flex-col">
      <Header onIniciarTramite={() => setModalAbierto(true)} />
      <main className="flex-1">
        <Hero onIniciarTramite={() => setModalAbierto(true)} />
        <AboutStats />
        <Servicios onIniciarTramite={() => setModalAbierto(true)} />
      </main>
      <Footer />

      <IniciarTramiteModal open={modalAbierto} onClose={() => setModalAbierto(false)} />
    </div>
  )
}