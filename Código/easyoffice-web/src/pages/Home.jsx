import { useState } from 'react'
import Header from '../components/Header.jsx'
import Hero from '../components/Hero.jsx'
import AboutStats from '../components/AboutStats.jsx'
import Servicios from '../components/Servicios.jsx'
import Footer from '../components/Footer.jsx'
import IniciarTramiteModal from '../components/IniciarTramiteModal.jsx'

export default function Home() {
  const [modalAbierto, setModalAbierto] = useState(false)

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
