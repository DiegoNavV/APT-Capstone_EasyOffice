import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { validarCodigoSeguimiento } from '../utils/validaciones.js'

export default function IniciarTramiteModal({ open, onClose }) {
  const [codigo, setCodigo] = useState('')
  const [tocado, setTocado] = useState(false)
  const navigate = useNavigate()

  if (!open) return null

  const codigoValido = validarCodigoSeguimiento(codigo)

  function onCambiarCodigo(valor) {
    // Solo letras y números, hasta 8 caracteres - igual a como se genera el código real.
    const limpio = valor.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 8)
    setCodigo(limpio)
  }

  function irASeguimiento(e) {
    e.preventDefault()
    setTocado(true)
    if (!codigoValido) return
    onClose()
    navigate(`/seguimiento?codigo=${codigo}`)
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
            onChange={(e) => onCambiarCodigo(e.target.value)}
            onBlur={() => setTocado(true)}
            placeholder="Ej: A1B2C3D4"
            className={`w-full border rounded-md px-3 py-2.5 text-sm tracking-widest text-center font-semibold focus:outline-none focus:ring-2 focus:border-primary ${
              tocado && !codigoValido ? 'border-red-400 focus:ring-red-200' : 'border-gray-300 focus:ring-primary/40'
            }`}
          />
          {tocado && !codigoValido && (
            <p className="mt-1 text-xs text-red-600">
              El código debe tener 8 caracteres (letras y números).
            </p>
          )}
          <button
            type="submit"
            disabled={!codigoValido}
            className="mt-3 w-full bg-primary hover:bg-primary-dark disabled:bg-gray-300 disabled:cursor-not-allowed text-white font-semibold py-3 rounded-md transition-colors"
          >
            Continuar
          </button>
        </form>

        <p className="mt-5 text-center text-sm text-gray-600">
          ¿No tienes tu código? Para obtenerlo primero debes contratar el servicio y coordinar
          el pago con Easy Office.
          <br />
          <button
            type="button"
            onClick={irAContratar}
            className="mt-1 text-primary font-semibold hover:underline"
          >
            Contrata aquí
          </button>
        </p>
      </div>
    </div>
  )
}