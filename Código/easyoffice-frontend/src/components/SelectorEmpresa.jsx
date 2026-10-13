import { useEffect, useState } from 'react'
import { ApiError } from '../lib/api.js'
import { buscarEmpresas, obtenerEmpresasSugeridas } from '../lib/solicitudesApi.js'

// Paso opcional al convertir una solicitud: el agente decide si el trámite queda vinculado a una empresa que ya existe. Nunca se 
// preselecciona nada ni lo decide el cliente: por defecto va "Sin empresa por ahora". Solo muestra id, RUT y razón social; los datos 
// detallados de la empresa no viajan hasta aquí.

const MIN_CARACTERES = 2
const ESPERA_BUSQUEDA_MS = 350

// "76123456-0" -> "76.123.456-0" (solo para mostrar; se guarda sin puntos).
function formatearRut(rut) {
  const m = /^(\d{1,8})-([\dkK])$/.exec(rut || '')
  if (!m) return rut || ''
  return `${m[1].replace(/\B(?=(\d{3})+(?!\d))/g, '.')}-${m[2].toUpperCase()}`
}

export function textoEmpresa(empresa) {
  return `${empresa.razon_social} (${formatearRut(empresa.rut_empresa)})`
}

function Opcion({ name, checked, onChange, disabled, children }) {
  return (
    <label className={`flex items-start gap-2.5 px-3 py-2 rounded-[10px] border cursor-pointer ${checked ? 'border-brand-primary bg-brand-tint' : 'border-line hover:border-ink-muted'}`}>
      <input
        type="radio"
        name={name}
        checked={checked}
        onChange={onChange}
        disabled={disabled}
        className="mt-1 accent-brand-primary"
      />
      <span className="text-sm text-ink-primary break-words">{children}</span>
    </label>
  )
}

export default function SelectorEmpresa({
  idSolicitud,
  accessToken,
  seleccionada,
  onSeleccionar,
  onSesionVencida,
  deshabilitado = false
}) {
  const [sugeridas, setSugeridas] = useState([])
  const [cargandoSugeridas, setCargandoSugeridas] = useState(true)
  const [errorSugeridas, setErrorSugeridas] = useState('')

  const [texto, setTexto] = useState('')
  const [resultados, setResultados] = useState([])
  const [buscando, setBuscando] = useState(false)
  const [errorBusqueda, setErrorBusqueda] = useState('')

  const consulta = texto.trim()
  const consultaValida = consulta.length >= MIN_CARACTERES

  // Un fallo aquí nunca bloquea la conversión: el agente puede seguir sin empresa.
  function manejarError(e, fijarMensaje) {
    if (e instanceof ApiError && e.status === 401) {
      onSesionVencida?.()
      return
    }
    fijarMensaje(e instanceof ApiError ? e.message : 'No se pudo conectar con el servidor.')
  }

  useEffect(() => {
    let cancelado = false
    setCargandoSugeridas(true)
    setErrorSugeridas('')
    obtenerEmpresasSugeridas({ accessToken, idSolicitud })
      .then((datos) => {
        if (!cancelado) setSugeridas(datos)
      })
      .catch((e) => {
        if (!cancelado) manejarError(e, setErrorSugeridas)
      })
      .finally(() => {
        if (!cancelado) setCargandoSugeridas(false)
      })
    return () => {
      cancelado = true
    }
    // Se piden una sola vez al abrir el paso; el token se renueva solo.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idSolicitud])

  useEffect(() => {
    setErrorBusqueda('')
    if (!consultaValida) {
      setResultados([])
      setBuscando(false)
      return undefined
    }
    let cancelado = false
    setBuscando(true)
    // Pequeña espera para no consultar en cada tecla.
    const temporizador = setTimeout(() => {
      buscarEmpresas({ accessToken, texto: consulta })
        .then((datos) => {
          if (!cancelado) setResultados(datos)
        })
        .catch((e) => {
          if (!cancelado) manejarError(e, setErrorBusqueda)
        })
        .finally(() => {
          if (!cancelado) setBuscando(false)
        })
    }, ESPERA_BUSQUEDA_MS)
    return () => {
      cancelado = true
      clearTimeout(temporizador)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [consulta])

  // Lista visible: la empresa ya elegida siempre queda a la vista (aunque deje de aparecer al cambiar la búsqueda), luego 
  // las sugeridas y luego los resultados.
  const visibles = []
  const vistas = new Set()
  function agregar(empresa) {
    if (!empresa || vistas.has(empresa.id_empresa)) return
    vistas.add(empresa.id_empresa)
    visibles.push(empresa)
  }
  agregar(seleccionada)
  sugeridas.forEach(agregar)
  if (consultaValida) resultados.forEach(agregar)

  const sinResultados = consultaValida && !buscando && !errorBusqueda && resultados.length === 0

  return (
    <fieldset className="mt-4" disabled={deshabilitado}>
      <legend className="text-sm font-semibold text-ink-primary">Empresa (opcional)</legend>
      <p className="mt-1 text-xs text-ink-muted">
        Si el cliente ya tiene una empresa registrada, vincúlala para reutilizar sus datos. Si no
        estás seguro, déjalo sin empresa.
      </p>

      <div className="mt-3 space-y-2">
        <Opcion
          name={`empresa-${idSolicitud}`}
          checked={!seleccionada}
          onChange={() => onSeleccionar(null)}
        >
          Sin empresa por ahora
        </Opcion>

        {cargandoSugeridas && <p className="text-xs text-ink-muted">Buscando empresas del solicitante…</p>}
        {errorSugeridas && (
          <p className="text-xs text-ink-muted">
            No se pudieron cargar las sugerencias ({errorSugeridas}). Puedes buscar la empresa o
            continuar sin ella.
          </p>
        )}

        {visibles.map((empresa) => {
          const esSugerida = sugeridas.some((s) => s.id_empresa === empresa.id_empresa)
          return (
            <Opcion
              key={empresa.id_empresa}
              name={`empresa-${idSolicitud}`}
              checked={seleccionada?.id_empresa === empresa.id_empresa}
              onChange={() => onSeleccionar(empresa)}
            >
              {textoEmpresa(empresa)}
              {esSugerida && <span className="ml-2 text-xs text-ink-muted">· Ya registrada con este solicitante</span>}
            </Opcion>
          )
        })}
      </div>

      <div className="mt-3">
        <label htmlFor={`buscar-empresa-${idSolicitud}`} className="text-xs text-ink-muted">
          Buscar otra empresa por razón social o RUT
        </label>
        <input
          id={`buscar-empresa-${idSolicitud}`}
          type="search"
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          maxLength={100}
          placeholder="Ej: Comercial Prueba o 76.123.456-0"
          className="mt-1 w-full text-sm text-ink-primary bg-surface border border-line-strong rounded-[10px] px-3 py-2 focus:outline-none focus:border-brand-primary"
        />
        <div role="status" aria-live="polite" className="mt-1 text-xs text-ink-muted">
          {consulta.length > 0 && !consultaValida && `Escribe al menos ${MIN_CARACTERES} caracteres.`}
          {buscando && 'Buscando…'}
          {sinResultados && 'No se encontraron empresas con ese texto.'}
        </div>
        {errorBusqueda && (
          <p role="alert" className="text-xs text-red-600">
            {errorBusqueda}
          </p>
        )}
      </div>
    </fieldset>
  )
}