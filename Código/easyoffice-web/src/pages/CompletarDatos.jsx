import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import Header from '../components/Header.jsx'
import Footer from '../components/Footer.jsx'
import { leerCodigo, borrarCodigo } from '../utils/codigoSesion.js'
import { guardarBorrador, leerBorrador, descartarBorrador } from '../utils/borrador.js'
import {
  atributosInput,
  camposPendientes,
  formatearParaResumen,
  normalizarEntrada,
  validarFormulario,
  valoresParaEnviar
} from '../utils/camposCliente.js'
import { enviarDatos, obtenerBorrador, obtenerFormulario } from '../lib/clienteApi.js'

// BORRADOR DE TEXTO LEGAL: lo redactó el equipo de desarrollo como base. Easy Office
// debe revisarlo (y su asesor legal, si corresponde) antes de pasar a producción.
const TEXTO_CONSENTIMIENTO =
  'Autorizo a Easy Office a tratar los datos personales y de mi empresa que ingreso en este ' +
  'formulario, solo para preparar, gestionar y entregar el trámite que contraté. Declaro que ' +
  'los datos son verídicos y que tengo derecho a entregarlos. Entiendo que Easy Office no los ' +
  'usará para otros fines y que solo los compartirá con quienes sean necesarios para realizar ' +
  'el servicio (por ejemplo, el proveedor de firma electrónica) o cuando la ley lo exija. ' +
  'Puedo pedir a Easy Office acceso, corrección o eliminación de mis datos cuando quiera.'

const TEXTO_NO_EDITAR =
  'Entiendo que, una vez enviados, no podré editar estos datos. Si hay un error, tendré que ' +
  'rehacer el proceso con Easy Office.'

const TEXTO_REVISE_BORRADOR = 'Revisé mi borrador y los datos son correctos.'

// ---------- estilos compartidos ----------
// Verde más oscuro que el corporativo para botones y enlaces: #15803d (green-700) sobre blanco
// cumple contraste AA; hover #166534 (green-800).
const FOCO = 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-700 focus-visible:ring-offset-2'
const CLASES_TARJETA = 'bg-white rounded-xl border border-gray-200 p-5 sm:p-6'
const CLASES_TARJETA_CENTRADA = 'mx-auto max-w-xl bg-white rounded-xl border border-gray-200 p-6 sm:p-8 text-center'
const CLASES_BOTON = `inline-flex min-h-[44px] items-center justify-center rounded-md bg-green-700 px-6 py-3 font-semibold text-white transition-colors hover:bg-green-800 disabled:cursor-not-allowed disabled:bg-gray-300 disabled:text-gray-600 ${FOCO}`
const CLASES_ENLACE = `inline-flex min-h-[44px] items-center rounded text-sm font-semibold text-green-700 hover:text-green-800 hover:underline ${FOCO}`
const CLASES_CASILLA = 'flex min-h-[44px] cursor-pointer items-start gap-3 py-2 text-sm text-gray-700'
const CLASES_INPUT_CASILLA = 'mt-0.5 h-5 w-5 shrink-0 cursor-pointer accent-green-700'
const CLASES_INPUT_RADIO = 'h-5 w-5 shrink-0 cursor-pointer accent-green-700'
// Alto del visor del borrador: 420 px en celular; en escritorio 880 px, o menos si la pantalla es baja.
const ALTO_VISOR = 'h-[420px] lg:h-[min(880px,calc(100vh-9rem))]'

// ---------- grupos del formulario ----------
// Dónde va cada campo y cuánto ocupa (1 o 2 columnas). Un campo que no esté aquí (por ejemplo,
// uno nuevo del servidor) igual se muestra: cae en "Otros datos", a ancho completo.
const GRUPOS = [
  { id: 'representante', titulo: 'Datos del representante legal' },
  { id: 'empresa', titulo: 'Datos de la empresa' },
  { id: 'otros', titulo: 'Otros datos' }
]

const UBICACION_CAMPOS = {
  representante_legal: { grupo: 'representante', orden: 1, ancho: 2 },
  rut_representante: { grupo: 'representante', orden: 2, ancho: 1 },
  celular: { grupo: 'representante', orden: 3, ancho: 1 },
  domicilio_representante: { grupo: 'representante', orden: 4, ancho: 2 },
  comuna_representante: { grupo: 'representante', orden: 5, ancho: 1 },
  region_representante: { grupo: 'representante', orden: 6, ancho: 1 },
  email: { grupo: 'representante', orden: 7, ancho: 2 },
  razon_social: { grupo: 'empresa', orden: 1, ancho: 1 },
  rut_empresa: { grupo: 'empresa', orden: 2, ancho: 1 },
  giro_principal: { grupo: 'empresa', orden: 3, ancho: 2 },
  fecha_escritura: { grupo: 'empresa', orden: 4, ancho: 1 },
  notaria: { grupo: 'empresa', orden: 5, ancho: 1 }
}

// Devuelve los grupos que tienen campos: [{ id, titulo, campos: [{ campo, ancho }] }].
function agruparCampos(campos) {
  const ubicados = campos.map((campo, i) => {
    const u = UBICACION_CAMPOS[campo.clave] ?? { grupo: 'otros', orden: 1000 + i, ancho: 2 }
    return { campo, ancho: u.ancho, grupo: u.grupo, orden: u.orden }
  })
  return GRUPOS.map((g) => ({
    ...g,
    campos: ubicados.filter((u) => u.grupo === g.id).sort((a, b) => a.orden - b.orden)
  })).filter((g) => g.campos.length > 0)
}

// El borrador trae datos del cliente: limpiarBorrador() lo deja vacío (sin páginas) al enviar,
// descartar o cambiar los datos, y al salir de la página el estado se desmonta.
const BORRADOR_INACTIVO = { estado: 'inactivo', total: 0, paginas: [], firma: null, mensaje: '' }

function subirAlInicio() {
  try {
    window.scrollTo({ top: 0 })
  } catch {
    // Entorno sin scroll.
  }
}

function formatearFecha(ms) {
  const f = new Date(ms)
  const dos = (n) => String(n).padStart(2, '0')
  return `${dos(f.getDate())}-${dos(f.getMonth() + 1)}-${f.getFullYear()}`
}

// ---------- piezas de la página ----------

function Pasos({ actual }) {
  const pasos = [
    { numero: 1, texto: 'Tus datos' },
    { numero: 2, texto: 'Revisar y enviar' }
  ]
  return (
    <ol aria-label="Pasos del proceso" className="flex flex-wrap items-center gap-2 text-sm">
      {pasos.map((p, i) => {
        const hecho = p.numero < actual
        const activo = p.numero === actual
        return (
          <li key={p.numero} className="flex items-center gap-2" aria-current={activo ? 'step' : undefined}>
            {i > 0 && (
              <span aria-hidden="true" className="text-gray-400">
                →
              </span>
            )}
            <span
              aria-hidden="true"
              className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold ${
                hecho || activo ? 'bg-green-700 text-white' : 'bg-gray-200 text-gray-700'
              }`}
            >
              {hecho ? '✓' : p.numero}
            </span>
            <span className={activo ? 'font-semibold text-ink' : 'text-gray-600'}>
              <span className="sr-only">Paso {p.numero}: </span>
              {p.texto}
              {hecho && <span className="sr-only"> (completado)</span>}
            </span>
          </li>
        )
      })}
    </ol>
  )
}

function EncabezadoPagina({ titulo, subtitulo, nota, paso }) {
  return (
    <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div>
        <h1 className="text-2xl font-bold text-ink sm:text-3xl">{titulo}</h1>
        {subtitulo && <p className="mt-1 text-gray-600">{subtitulo}</p>}
        {nota && <p className="mt-1 text-sm text-gray-600">{nota}</p>}
      </div>
      {paso && <Pasos actual={paso} />}
    </div>
  )
}

export default function CompletarDatos() {
  const navigate = useNavigate()
  const [codigo] = useState(() => leerCodigo())

  const [fase, setFase] = useState('cargando') // cargando | error | no_disponible | form | revision | enviado
  const [mensajeCarga, setMensajeCarga] = useState('')
  const [formulario, setFormulario] = useState(null)

  const [valores, setValores] = useState({})
  const [tocados, setTocados] = useState({})
  const [erroresServidor, setErroresServidor] = useState({})
  const [avisoServidor, setAvisoServidor] = useState('')
  const [borradorDe, setBorradorDe] = useState(null)
  const [confirmandoDescarte, setConfirmandoDescarte] = useState(false)

  const [esRepresentante, setEsRepresentante] = useState(null)
  const [consentimiento, setConsentimiento] = useState(false)
  const [aceptaNoEditar, setAceptaNoEditar] = useState(false)
  // Borrador del documento: inactivo | cargando | listo | error | no_disponible.
  // `firma` identifica con qué datos se armó, para saber si sigue vigente.
  const [borrador, setBorrador] = useState(BORRADOR_INACTIVO)
  const [revisoBorrador, setRevisoBorrador] = useState(false)
  const peticionBorradorRef = useRef(0)
  const [enviando, setEnviando] = useState(false)
  const [errorEnvio, setErrorEnvio] = useState(null) // { mensaje, estado }
  const [resultado, setResultado] = useState(null)
  const enviandoRef = useRef(false)

  useEffect(() => {
    if (!codigo) {
      navigate('/seguimiento', { replace: true })
      return undefined
    }
    let activo = true
    obtenerFormulario(codigo)
      .then((f) => {
        if (!activo) return
        setFormulario(f)
        if (!f.formulario_disponible) {
          setFase('no_disponible')
          return
        }
        const borrador = leerBorrador(codigo)
        if (borrador) {
          const restaurados = {}
          for (const c of camposPendientes(f.campos)) {
            const v = borrador.valores[c.clave]
            if (typeof v === 'string' && v.trim() !== '') restaurados[c.clave] = v.slice(0, c.max_largo)
          }
          if (Object.keys(restaurados).length > 0) {
            setValores(restaurados)
            setBorradorDe(borrador.guardado)
          }
        }
        setFase('form')
      })
      .catch((e) => {
        if (!activo) return
        if (e.estado === 404) borrarCodigo()
        setMensajeCarga(e.message)
        setFase('error')
      })
    return () => {
      activo = false
    }
  }, [codigo, navigate])

  const campos = formulario?.campos ?? []
  const registrados = campos.filter((c) => c.registrado)
  const pendientes = useMemo(() => camposPendientes(campos), [campos])
  const gruposPendientes = useMemo(() => agruparCampos(pendientes), [pendientes])
  const erroresCliente = useMemo(() => validarFormulario(campos, valores), [campos, valores])
  const hayAlgoEscrito = Object.values(valores).some((v) => v.trim() !== '')
  const firmaActual = useMemo(() => JSON.stringify(valoresParaEnviar(campos, valores)), [campos, valores])

  // Para enviar hay que haber visto el borrador con los datos actuales y marcarlo como
  // revisado. Única excepción: si el servidor dice que no puede mostrarlo (no depende del cliente).
  const borradorVigente = borrador.firma === firmaActual
  const borradorOk =
    borradorVigente && (borrador.estado === 'no_disponible' || (borrador.estado === 'listo' && revisoBorrador))
  const puedeEnviar = !enviando && esRepresentante !== null && consentimiento && aceptaNoEditar && borradorOk

  function limpiarBorrador() {
    peticionBorradorRef.current += 1
    setBorrador(BORRADOR_INACTIVO)
    setRevisoBorrador(false)
  }

  // Pide el borrador con los datos actuales. Si ya hay uno vigente (o en camino) con los
  // mismos datos no vuelve a pedirlo, para no gastar el límite de intentos del cliente.
  async function cargarBorrador(forzar = false) {
    if (!forzar && borrador.firma === firmaActual && (borrador.estado === 'listo' || borrador.estado === 'cargando')) {
      return
    }
    const turno = peticionBorradorRef.current + 1
    peticionBorradorRef.current = turno
    setRevisoBorrador(false)
    setBorrador({ estado: 'cargando', total: 0, paginas: [], firma: firmaActual, mensaje: '' })
    try {
      const { total, paginas } = await obtenerBorrador(codigo, valoresParaEnviar(campos, valores))
      if (turno !== peticionBorradorRef.current) return
      setBorrador({ estado: 'listo', total, paginas, firma: firmaActual, mensaje: '' })
    } catch (e) {
      if (turno !== peticionBorradorRef.current) return
      if (e.errores) {
        // El servidor rechazó algún campo: se vuelve al formulario, igual que al enviar.
        setBorrador(BORRADOR_INACTIVO)
        setErroresServidor(e.errores)
        setAvisoServidor(e.message)
        setFase('form')
        subirAlInicio()
        return
      }
      setBorrador({
        estado: e.estado === 409 ? 'no_disponible' : 'error',
        total: 0,
        paginas: [],
        firma: firmaActual,
        mensaje: e.message
      })
    }
  }

  function errorDe(clave) {
    return erroresServidor[clave] ?? (tocados[clave] ? erroresCliente[clave] : null)
  }

  function cambiar(campo, texto) {
    const nuevos = { ...valores, [campo.clave]: normalizarEntrada(campo, texto) }
    setValores(nuevos)
    guardarBorrador(codigo, nuevos)
    if (erroresServidor[campo.clave]) {
      setErroresServidor((previos) => {
        const resto = { ...previos }
        delete resto[campo.clave]
        return resto
      })
    }
  }

  function descartar() {
    descartarBorrador()
    limpiarBorrador()
    setValores({})
    setTocados({})
    setErroresServidor({})
    setAvisoServidor('')
    setBorradorDe(null)
    setConfirmandoDescarte(false)
  }

  function irARevision(e) {
    e.preventDefault()
    setTocados(Object.fromEntries(pendientes.map((c) => [c.clave, true])))
    if (Object.keys(erroresCliente).length > 0) return
    setAvisoServidor('')
    setErrorEnvio(null)
    setFase('revision')
    subirAlInicio()
    cargarBorrador()
  }

  async function enviar() {
    if (enviandoRef.current) return
    if (!puedeEnviar) return
    enviandoRef.current = true
    setEnviando(true)
    setErrorEnvio(null)
    try {
      const respuesta = await enviarDatos(codigo, {
        campos: valoresParaEnviar(campos, valores),
        solicitante_es_representante: esRepresentante,
        consentimiento_aceptado: consentimiento,
        acepta_no_editar: aceptaNoEditar
      })
      descartarBorrador()
      limpiarBorrador()
      setValores({})
      setResultado(respuesta)
      setFase('enviado')
      subirAlInicio()
    } catch (e) {
      if (e.errores) {
        setErroresServidor(e.errores)
        setAvisoServidor(e.message)
        setFase('form')
        subirAlInicio()
      } else {
        setErrorEnvio({ mensaje: e.message, estado: e.estado })
      }
    } finally {
      enviandoRef.current = false
      setEnviando(false)
    }
  }

  const clavesVisibles = new Set(pendientes.map((c) => c.clave))
  const erroresSinCampo = Object.entries(erroresServidor).filter(([k]) => !clavesVisibles.has(k))
  const subtitulo = formulario ? `${formulario.nombre_servicio} · Código ${formulario.codigo_seguimiento}` : null

  return (
    <div className="min-h-screen flex flex-col bg-[#f6f7f8]">
      <Header />

      <main className="flex-1">
        <div
          className={`mx-auto w-full px-4 pt-6 lg:px-10 lg:pt-10 ${
            fase === 'revision' ? 'max-w-[1440px] pb-24 lg:pb-10' : 'max-w-[1280px] pb-10'
          }`}
        >
          {fase === 'cargando' && (
            <>
              <EncabezadoPagina titulo="Completar mis datos" />
              <div role="status" className={`mt-8 ${CLASES_TARJETA_CENTRADA}`}>
                <p className="text-gray-600">Cargando tu formulario...</p>
              </div>
            </>
          )}

          {fase === 'error' && (
            <>
              <EncabezadoPagina titulo="Completar mis datos" />
              <div className={`mt-8 ${CLASES_TARJETA_CENTRADA}`}>
                <p role="alert" className="text-sm text-red-700">
                  {mensajeCarga}
                </p>
                <Link to="/seguimiento" className={`mt-4 ${CLASES_ENLACE}`}>
                  Volver a consultar mi trámite
                </Link>
              </div>
            </>
          )}

          {fase === 'no_disponible' && (
            <>
              <EncabezadoPagina titulo="Completar mis datos" subtitulo={subtitulo} />
              <div className={`mt-8 ${CLASES_TARJETA_CENTRADA}`}>
                <p className="font-semibold text-ink">
                  {formulario.datos_enviados ? 'Ya recibimos tus datos' : 'Este formulario no está disponible'}
                </p>
                <p className="mt-2 text-sm text-gray-600">
                  {formulario.datos_enviados
                    ? 'No necesitas hacer nada más aquí. Puedes seguir el avance de tu trámite en la página de seguimiento.'
                    : 'Por ahora no hay datos que debas completar para este trámite. Revisa el estado en la página de seguimiento.'}
                </p>
                <Link to="/seguimiento" className={`mt-4 ${CLASES_ENLACE}`}>
                  Ver el estado de mi trámite
                </Link>
              </div>
            </>
          )}

          {fase === 'form' && (
            <>
              <EncabezadoPagina titulo="Completar mis datos" subtitulo={subtitulo} paso={1} />

              {avisoServidor && (
                <div role="alert" className="mt-6 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
                  <p>{avisoServidor}</p>
                  {erroresSinCampo.length > 0 && (
                    <ul className="mt-2 list-disc pl-5">
                      {erroresSinCampo.map(([clave, msg]) => (
                        <li key={clave}>{msg}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              {borradorDe && (
                <div className="mt-6 rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-800">
                  Recuperamos lo que habías escrito el {formatearFecha(borradorDe)}. Revísalo antes de continuar.
                </div>
              )}

              <div className="mt-6 flex flex-col gap-6 lg:flex-row lg:items-start">
                <aside className="w-full space-y-4 lg:sticky lg:top-28 lg:w-[340px] lg:shrink-0">
                  {registrados.length > 0 && (
                    <section aria-labelledby="titulo-registrados" className={CLASES_TARJETA}>
                      <h2 id="titulo-registrados" className="font-semibold text-ink">
                        Datos que ya tenemos registrados
                      </h2>
                      <p className="mt-1 text-sm text-gray-600">
                        Por seguridad se muestran parcialmente y no puedes modificarlos aquí.
                      </p>
                      <dl className="mt-4 space-y-3">
                        {registrados.map((c) => (
                          <div key={c.clave}>
                            <dt className="text-sm font-medium text-gray-700">{c.etiqueta}</dt>
                            <dd className="mt-1 rounded-md bg-gray-100 px-3 py-2 text-sm text-gray-700 break-words">
                              {c.valor_enmascarado}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    </section>
                  )}

                  {pendientes.length > 0 && (
                    <div className="rounded-xl border border-green-200 bg-green-50 p-4 text-sm text-green-900">
                      Lo que escribes se guarda solo en este navegador mientras avanzas. No se envía a Easy Office
                      hasta que confirmes al final.
                    </div>
                  )}
                </aside>

                <form
                  onSubmit={irARevision}
                  noValidate
                  aria-labelledby="titulo-completar"
                  className={`min-w-0 flex-1 ${CLASES_TARJETA}`}
                >
                  <h2 id="titulo-completar" className="font-semibold text-ink">
                    Datos que debes completar
                  </h2>

                  {pendientes.length === 0 && (
                    <p className="mt-2 text-sm text-gray-600">No necesitas ingresar más datos. Continúa para confirmar.</p>
                  )}

                  {gruposPendientes.map((g, i) => (
                    <section
                      key={g.id}
                      aria-labelledby={`grupo-${g.id}`}
                      className={i === 0 ? 'mt-5' : 'mt-6 border-t border-gray-200 pt-6'}
                    >
                      <h3 id={`grupo-${g.id}`} className="text-sm font-semibold text-gray-800">
                        {g.titulo}
                      </h3>
                      <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
                        {g.campos.map(({ campo: c, ancho }) => {
                          const error = errorDe(c.clave)
                          const attrs = atributosInput(c.tipo)
                          const id = `campo-${c.clave}`
                          return (
                            <div key={c.clave} className={ancho === 2 ? 'sm:col-span-2' : ''}>
                              <label htmlFor={id} className="text-sm font-medium text-gray-700">
                                {c.etiqueta}
                              </label>
                              <input
                                id={id}
                                {...attrs}
                                value={valores[c.clave] ?? ''}
                                maxLength={c.tipo === 'fecha' ? undefined : c.max_largo}
                                onChange={(e) => cambiar(c, e.target.value)}
                                onBlur={() => setTocados((t) => ({ ...t, [c.clave]: true }))}
                                aria-invalid={error ? 'true' : 'false'}
                                aria-describedby={`${id}-ayuda`}
                                className={`mt-1 min-h-[44px] w-full rounded-md border bg-white px-3 py-2.5 text-sm focus:outline-none focus:ring-2 ${
                                  error
                                    ? 'border-red-500 focus:border-red-600 focus:ring-red-200'
                                    : 'border-gray-300 focus:border-green-700 focus:ring-green-700/30'
                                }`}
                              />
                              <div id={`${id}-ayuda`}>
                                {c.ayuda && !error && <p className="mt-1 text-xs text-gray-600">{c.ayuda}</p>}
                                {error && (
                                  <p role="alert" className="mt-1 text-xs text-red-700">
                                    {error}
                                  </p>
                                )}
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    </section>
                  ))}

                  <div className="mt-8 flex flex-col-reverse gap-3 border-t border-gray-200 pt-6 sm:flex-row sm:items-center sm:justify-between">
                    <div className="text-sm">
                      {hayAlgoEscrito &&
                        (!confirmandoDescarte ? (
                          <button
                            type="button"
                            onClick={() => setConfirmandoDescarte(true)}
                            className={`min-h-[44px] rounded text-gray-600 underline hover:text-gray-800 ${FOCO}`}
                          >
                            Descartar borrador
                          </button>
                        ) : (
                          <span className="flex flex-wrap items-center gap-x-3 text-gray-700">
                            ¿Borrar todo lo que escribiste?
                            <button
                              type="button"
                              onClick={descartar}
                              className={`min-h-[44px] rounded font-semibold text-red-700 underline ${FOCO}`}
                            >
                              Sí, borrar
                            </button>
                            <button
                              type="button"
                              onClick={() => setConfirmandoDescarte(false)}
                              className={`min-h-[44px] rounded text-gray-600 underline ${FOCO}`}
                            >
                              Cancelar
                            </button>
                          </span>
                        ))}
                    </div>
                    <button type="submit" className={`w-full sm:w-auto ${CLASES_BOTON}`}>
                      Revisar mis datos
                    </button>
                  </div>
                </form>
              </div>
            </>
          )}

          {fase === 'revision' && (
            <>
              <EncabezadoPagina
                titulo="Revisa tu documento"
                subtitulo={subtitulo}
                nota="Después de enviar no podrás editar estos datos."
                paso={2}
              />

              <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[400px_minmax(0,1fr)] lg:items-start">
                {/* En celular este contenedor "desaparece" (contents) y sus tarjetas se ordenan con
                    order-*: datos, borrador, confirmaciones, barra de envío. En escritorio es la
                    columna izquierda, fija y con su propio scroll si no cabe. */}
                <div className="contents lg:sticky lg:top-28 lg:block lg:max-h-[calc(100vh-8rem)] lg:space-y-6 lg:overflow-y-auto">
                  <section aria-labelledby="titulo-tus-datos" className={`order-1 ${CLASES_TARJETA}`}>
                    <div className="flex items-center justify-between gap-3">
                      <h2 id="titulo-tus-datos" className="font-semibold text-ink">
                        Tus datos
                      </h2>
                      <button
                        type="button"
                        onClick={() => {
                          setFase('form')
                          subirAlInicio()
                        }}
                        className={CLASES_ENLACE}
                      >
                        Volver a editar
                      </button>
                    </div>
                    {pendientes.length === 0 ? (
                      <p className="mt-2 text-sm text-gray-600">No hay datos nuevos para enviar.</p>
                    ) : (
                      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3">
                        {gruposPendientes
                          .flatMap((g) => g.campos)
                          .map(({ campo: c, ancho }) => (
                            <div key={c.clave} className={`min-w-0 ${ancho === 2 ? 'col-span-2' : ''}`}>
                              <dt className="text-xs text-gray-600">{c.etiqueta}</dt>
                              <dd className="text-sm font-medium text-ink break-words">
                                {formatearParaResumen(c, valores[c.clave])}
                              </dd>
                            </div>
                          ))}
                      </dl>
                    )}
                  </section>

                  <section aria-labelledby="titulo-confirmar" className={`order-3 ${CLASES_TARJETA}`}>
                    <h2 id="titulo-confirmar" className="font-semibold text-ink">
                      Antes de enviar
                    </h2>

                    <fieldset className="mt-3">
                      <legend className="text-sm font-medium text-gray-700">
                        ¿Eres el representante legal de la empresa?
                      </legend>
                      <div className="mt-1 flex gap-6">
                        <label className={`${CLASES_CASILLA} items-center`}>
                          <input
                            type="radio"
                            name="representante"
                            className={CLASES_INPUT_RADIO}
                            checked={esRepresentante === true}
                            onChange={() => setEsRepresentante(true)}
                          />
                          Sí
                        </label>
                        <label className={`${CLASES_CASILLA} items-center`}>
                          <input
                            type="radio"
                            name="representante"
                            className={CLASES_INPUT_RADIO}
                            checked={esRepresentante === false}
                            onChange={() => setEsRepresentante(false)}
                          />
                          No
                        </label>
                      </div>
                    </fieldset>

                    {borrador.estado === 'listo' && (
                      <label className={`mt-2 ${CLASES_CASILLA}`}>
                        <input
                          type="checkbox"
                          className={CLASES_INPUT_CASILLA}
                          checked={revisoBorrador}
                          onChange={(e) => setRevisoBorrador(e.target.checked)}
                        />
                        {TEXTO_REVISE_BORRADOR}
                      </label>
                    )}

                    <div className="mt-2">
                      <label className={CLASES_CASILLA}>
                        <input
                          type="checkbox"
                          className={CLASES_INPUT_CASILLA}
                          checked={consentimiento}
                          onChange={(e) => setConsentimiento(e.target.checked)}
                          aria-describedby="texto-consentimiento"
                        />
                        Leí y acepto el tratamiento de mis datos.
                      </label>
                      <details className="ml-8">
                        <summary
                          className={`inline-flex min-h-[44px] cursor-pointer items-center rounded text-sm font-semibold text-green-700 hover:text-green-800 ${FOCO}`}
                        >
                          Ver texto
                        </summary>
                        <p
                          id="texto-consentimiento"
                          className="mt-1 rounded-md border border-gray-200 bg-gray-50 p-3 text-xs text-gray-700"
                        >
                          {TEXTO_CONSENTIMIENTO}
                        </p>
                      </details>
                    </div>

                    <label className={`mt-2 ${CLASES_CASILLA}`}>
                      <input
                        type="checkbox"
                        className={CLASES_INPUT_CASILLA}
                        checked={aceptaNoEditar}
                        onChange={(e) => setAceptaNoEditar(e.target.checked)}
                      />
                      {TEXTO_NO_EDITAR}
                    </label>

                    {errorEnvio && (
                      <div role="alert" className="mt-3 text-sm text-red-700">
                        <p>{errorEnvio.mensaje}</p>
                        {errorEnvio.estado === 409 && (
                          <Link to="/seguimiento" className={CLASES_ENLACE}>
                            Ver el estado de mi trámite
                          </Link>
                        )}
                      </div>
                    )}

                    {!borradorOk && (
                      <p className="mt-3 text-sm text-gray-600">
                        Para enviar, primero revisa el borrador de tu documento y marca que lo revisaste.
                      </p>
                    )}
                  </section>

                  {/* Celular: barra pegada abajo. Escritorio: botón a ancho completo bajo las confirmaciones. */}
                  <div className="order-4 sticky bottom-0 z-10 -mx-4 border-t border-gray-200 bg-white px-4 py-3 lg:static lg:mx-0 lg:border-0 lg:bg-transparent lg:p-0">
                    <button
                      type="button"
                      onClick={enviar}
                      disabled={!puedeEnviar}
                      className={`min-h-[48px] w-full ${CLASES_BOTON}`}
                    >
                      {enviando ? 'Enviando...' : 'Enviar mis datos'}
                    </button>
                  </div>
                </div>

                <section
                  aria-labelledby="titulo-borrador"
                  className={`order-2 min-w-0 lg:col-start-2 lg:row-start-1 ${CLASES_TARJETA}`}
                >
                  <h2 id="titulo-borrador" className="font-semibold text-ink">
                    Borrador de tu documento
                  </h2>
                  <p className="mt-1 text-sm text-gray-600">
                    Así quedaría tu documento con los datos que ingresaste. Los datos que ya teníamos registrados se
                    muestran parcialmente. Es un borrador: todavía no es tu documento final ni está firmado.
                  </p>

                  {borrador.estado === 'cargando' && (
                    <div role="status" aria-busy="true" className="mt-4">
                      <div className={`${ALTO_VISOR} animate-pulse rounded-lg bg-gray-200`} />
                      <p className="mt-3 text-sm text-gray-600">Preparando tu borrador... puede tardar unos segundos.</p>
                    </div>
                  )}

                  {borrador.estado === 'listo' && (
                    <div className="mt-4">
                      <div className="flex items-center justify-between gap-4">
                        <p className="text-sm text-gray-700">Páginas: {borrador.total}</p>
                        <button type="button" onClick={() => cargarBorrador(true)} className={CLASES_ENLACE}>
                          Volver a cargar
                        </button>
                      </div>
                      <div
                        role="region"
                        aria-label="Páginas del borrador"
                        tabIndex={0}
                        className={`mt-2 ${ALTO_VISOR} overflow-y-auto rounded-lg bg-gray-200 p-3 sm:p-6 ${FOCO}`}
                      >
                        <div className="mx-auto flex max-w-[820px] flex-col gap-4 sm:gap-6">
                          {borrador.paginas.map((p) => (
                            <img
                              key={p.numero}
                              src={p.imagen}
                              alt={`Página ${p.numero} del borrador`}
                              draggable={false}
                              onContextMenu={(e) => e.preventDefault()}
                              className="block h-auto w-full select-none bg-white shadow-md"
                            />
                          ))}
                        </div>
                      </div>
                    </div>
                  )}

                  {borrador.estado === 'error' && (
                    <div role="alert" className="mt-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
                      <p>{borrador.mensaje}</p>
                      <button type="button" onClick={() => cargarBorrador(true)} className={`mt-1 ${CLASES_ENLACE}`}>
                        Reintentar
                      </button>
                    </div>
                  )}

                  {borrador.estado === 'no_disponible' && (
                    <div className="mt-4 rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-800">
                      {borrador.mensaje}
                    </div>
                  )}
                </section>
              </div>
            </>
          )}

          {fase === 'enviado' && (
            <>
              <EncabezadoPagina titulo="Completar mis datos" subtitulo={subtitulo} />
              <div className={`mt-8 ${CLASES_TARJETA_CENTRADA}`}>
                <p className="text-lg font-semibold text-ink">¡Recibimos tus datos!</p>
                <p className="mt-2 text-sm text-gray-600">
                  {resultado?.estado_actual === 'en_revision'
                    ? 'Easy Office revisará tu información antes de continuar con tu trámite.'
                    : 'Ya estamos trabajando en tu trámite.'}{' '}
                  Puedes seguir el avance con tu código de seguimiento.
                </p>
                <Link to="/seguimiento" className={`mt-6 ${CLASES_BOTON}`}>
                  Ver el estado de mi trámite
                </Link>
              </div>
            </>
          )}
        </div>
      </main>

      <Footer />
    </div>
  )
}
