import { useMemo, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../lib/AuthContext.jsx'
import Sidebar from '../components/Sidebar.jsx'
import StatusChip from '../components/StatusChip.jsx'
import UserMenu from '../components/UserMenu.jsx'

// Vista "panel principal" (mockup Figma, pantalla "2 · Listado de trámites").
// Todavía no existe un endpoint de listado de trámites en el backend (solo
// GET /api/tramites/codigo/{codigo} para el seguimiento público), así que esta
// pantalla usa los mismos datos de ejemplo del mockup. El filtro por
// documento y la búsqueda sí funcionan (son puramente del lado del cliente);
// "+ Nuevo trámite", "Estado"/"Agente" y las filas todavía no hacen nada
// porque esas funcionalidades no están construidas.

const KPIS = [
  { etiqueta: 'En borrador', valor: 3, nota: 'Pendientes de completar' },
  { etiqueta: 'Enviados a firma', valor: 5, nota: 'Esperando al cliente' },
  { etiqueta: 'Firmados (hoy)', valor: 8, nota: '+2 vs. ayer' },
  { etiqueta: 'Rechazados', valor: 1, nota: 'Requiere reintento' }
]

const DOCUMENTOS = ['Contrato de servicios', 'Autorización de domicilio']

const TRAMITES_EJEMPLO = [
  { id: 1, cliente: 'Constructora Vega Ltda.', rut: '76.912.345-6', documento: 'Contrato de servicios', agente: 'D. Navarrete', actualizado: 'Hoy · 10:24', estado: 'firmado' },
  { id: 2, cliente: 'María Ríos Tapia', rut: '15.234.876-2', documento: 'Autorización de domicilio', agente: 'A. Fernández', actualizado: 'Hoy · 09:10', estado: 'enviado' },
  { id: 3, cliente: 'Tostaduría del Sur SpA', rut: '77.456.001-K', documento: 'Contrato de servicios', agente: 'D. Hernández', actualizado: 'Ayer · 17:45', estado: 'entregado' },
  { id: 4, cliente: 'Innova Design SpA', rut: '78.101.220-3', documento: 'Autorización de domicilio', agente: 'D. Navarrete', actualizado: 'Ayer · 16:02', estado: 'borrador' },
  { id: 5, cliente: 'Juan Pérez Soto', rut: '13.098.554-1', documento: 'Contrato de servicios', agente: 'A. Fernández', actualizado: '12 sep · 11:30', estado: 'rechazado' },
  { id: 6, cliente: 'Comercial Andes Ltda.', rut: '76.550.900-8', documento: 'Autorización de domicilio', agente: 'D. Hernández', actualizado: '12 sep · 09:05', estado: 'enviado' }
]

// Filas que todavía no hacen nada al hacer clic (no existe vista de detalle construida).
function detenerClic(e) {
  e.preventDefault()
}

export default function Tramites() {
  const { usuario, verificando } = useAuth()
  const [documento, setDocumento] = useState('')
  const [busqueda, setBusqueda] = useState('')

  const filas = useMemo(() => {
    const texto = busqueda.trim().toLowerCase()
    return TRAMITES_EJEMPLO.filter((t) => {
      if (documento && t.documento !== documento) return false
      if (texto && !t.cliente.toLowerCase().includes(texto) && !t.rut.toLowerCase().includes(texto)) return false
      return true
    })
  }, [documento, busqueda])

  if (verificando) return null
  if (!usuario) return <Navigate to="/" replace />

  return (
    <div className="bg-canvas flex h-screen items-start">
      <Sidebar activo="tramites" />

      <div className="flex flex-1 flex-col h-full min-w-0">
        <header className="bg-surface border-b border-line flex items-center justify-between px-7 py-3.5 shrink-0">
          <h1 className="text-lg font-semibold text-ink-primary">Trámites</h1>
          <div className="flex items-center gap-3">
            <input
              type="text"
              value={busqueda}
              onChange={(e) => setBusqueda(e.target.value)}
              placeholder="Buscar cliente o RUT…"
              className="bg-subtle text-sm text-ink-primary placeholder:text-ink-muted rounded-md pl-3 pr-4 py-2.5 w-64 focus:outline-none focus:ring-2 focus:ring-brand-primary"
            />
            {/* Todavía no está construido el flujo de creación de trámites. */}
            <button
              type="button"
              onClick={detenerClic}
              className="bg-brand-primary hover:bg-brand-dark text-white text-sm font-semibold px-6 py-3 rounded-[10px] transition-colors"
            >
              + Nuevo trámite
            </button>
            <UserMenu />
          </div>
        </header>

        <main className="flex-1 overflow-y-auto px-7 py-6">
          <div className="flex gap-4">
            {KPIS.map((kpi) => (
              <div key={kpi.etiqueta} className="bg-surface border border-line rounded-[10px] flex-1 px-5 py-[18px]">
                <p className="text-[13px] font-medium text-ink-secondary">{kpi.etiqueta}</p>
                <p className="text-[26px] font-bold text-ink-primary leading-[32px]">{kpi.valor}</p>
                <p className="text-xs text-ink-muted">{kpi.nota}</p>
              </div>
            ))}
          </div>

          <div className="bg-surface border border-line rounded-[10px] mt-5 overflow-hidden">
            <div className="border-b border-line flex items-center gap-2.5 px-4 py-3.5">
              <div className="flex gap-1.5">
                <button
                  type="button"
                  onClick={() => setDocumento('')}
                  className={`text-[13px] font-medium px-3 py-[7px] rounded-md border transition-colors ${
                    documento === '' ? 'bg-brand-tint border-brand-primary text-brand-dark' : 'bg-surface border-line-strong text-ink-secondary hover:border-ink-muted'
                  }`}
                >
                  Todos
                </button>
                {DOCUMENTOS.map((doc) => (
                  <button
                    key={doc}
                    type="button"
                    onClick={() => setDocumento(doc)}
                    className={`text-[13px] font-medium px-3 py-[7px] rounded-md border transition-colors ${
                      documento === doc ? 'bg-brand-tint border-brand-primary text-brand-dark' : 'bg-surface border-line-strong text-ink-secondary hover:border-ink-muted'
                    }`}
                  >
                    {doc}
                  </button>
                ))}
              </div>
              <div className="flex-1" />
              {/* Mockup del mockup: todavía no abren un menú real. */}
              <button type="button" onClick={detenerClic} className="text-[13px] font-medium px-3 py-[7px] rounded-md border border-line-strong text-ink-secondary">
                Estado&nbsp;&nbsp;▾
              </button>
              <button type="button" onClick={detenerClic} className="text-[13px] font-medium px-3 py-[7px] rounded-md border border-line-strong text-ink-secondary">
                Agente&nbsp;&nbsp;▾
              </button>
            </div>

            <div className="bg-subtle border-b border-line flex items-center px-4 py-[11px] text-[11px] font-semibold tracking-wide text-ink-muted">
              <span className="flex-1">CLIENTE</span>
              <span className="w-[230px]">DOCUMENTO</span>
              <span className="w-[170px]">AGENTE</span>
              <span className="w-[150px]">ACTUALIZADO</span>
              <span className="w-[150px]">ESTADO</span>
            </div>

            {filas.length === 0 ? (
              <p className="text-sm text-ink-secondary text-center py-10">Ningún trámite coincide con el filtro.</p>
            ) : (
              filas.map((t) => (
                // No hay vista de detalle construida todavía: la fila no navega a ningún lado.
                <a key={t.id} href="#" onClick={detenerClic} className="border-b border-line last:border-b-0 cursor-pointer flex items-center px-4 py-[13px] hover:bg-canvas transition-colors">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-ink-primary">{t.cliente}</p>
                    <p className="text-xs text-ink-muted">RUT {t.rut}</p>
                  </div>
                  <span className="w-[230px] text-[13px] text-ink-secondary">{t.documento}</span>
                  <span className="w-[170px] text-[13px] text-ink-secondary">{t.agente}</span>
                  <span className="w-[150px] text-[13px] text-ink-secondary">{t.actualizado}</span>
                  <span className="w-[150px]">
                    <StatusChip variant={t.estado} />
                  </span>
                </a>
              ))
            )}
          </div>
        </main>
      </div>
    </div>
  )
}
