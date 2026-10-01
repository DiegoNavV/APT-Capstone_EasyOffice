import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

export default function IniciarTramiteModal({ open, onClose }) {
  const [codigo, setCodigo] = useState('')
  const navigate = useNavigate()

  if (!open) return null

  function irASeguimiento(e) {
    e.preventDefault()
    if (codigo.trim().length !== 8) return
    onClose()
    navigate(`/seguimiento?codigo=${codigo.trim().toUpperCase()}`)
  }

  function irAContratar() {
    onClose()
    navigate('/iniciar-tramite')
  }

  return (
    <div
      className="fixed inset-0 z-[100] bg-black/50 flex items-center justify-center px-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-xl max-w-md w-full p-6 sm:p-8"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between">
          <h2 className="text-xl font-bold text-ink">Ingresa tu código de trámite</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-xl leading-none"
            aria-label="Cerrar"
          >
            ×
          </button>
        </div>

        <p className="mt-2 text-sm text-gray-600">
          Si ya iniciaste un trámite, ingresa aquí tu código de 8 caracteres para continuar y
          descargar tu documento.
        </p>

        <form onSubmit={irASeguimiento} className="mt-4">
          <input
            type="text"
            maxLength={8}
            value={codigo}
            onChange={(e) => setCodigo(e.target.value.toUpperCase())}
            placeholder="Ej: A1B2C3D4"
            className="w-full border border-gray-300 rounded-md px-3 py-2.5 text-sm tracking-widest text-center font-semibold focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary"
          />
          <button
            type="submit"
            disabled={codigo.length !== 8}
            className="mt-3 w-full bg-primary hover:bg-primary-dark disabled:bg-gray-300 disabled:cursor-not-allowed text-white font-semibold py-3 rounded-md transition-colors"
          >
            Continuar
          </button>
        </form>

        <p className="mt-5 text-center text-sm text-gray-600">
          ¿No tienes tu código?{' '}
          <button
            type="button"
            onClick={irAContratar}
            className="text-primary font-semibold hover:underline"
          >
            Contrata aquí
          </button>
        </p>
      </div>
    </div>
  )
}
