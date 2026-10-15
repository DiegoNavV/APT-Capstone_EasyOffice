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
import { enviarDatos, obtenerFormulario } from '../lib/clienteApi.js'

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

const CLASES_TARJETA = 'bg-white rounded-xl border border-gray-200 p-6 sm:p-8'

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
  const erroresCliente = useMemo(() => validarFormulario(campos, valores), [campos, valores])
  const hayAlgoEscrito = Object.values(valores).some((v) => v.trim() !== '')

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
  }

  async function enviar() {
    if (enviandoRef.current) return
    if (esRepresentante === null || !consentimiento || !aceptaNoEditar) return
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

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      <Header />

      <main className="flex-1 py-12">
        <div className="max-w-xl mx-auto px-4 sm:px-6">
          <h1 className="text-2xl sm:text-3xl font-bold text-ink text-center">Completar mis datos</h1>

          {fase === 'cargando' && (
            <p className="mt-8 text-center text-gray-600">Cargando tu formulario...</p>
          )}

          {fase === 'error' && (
            <div className={`mt-8 ${CLASES_TARJETA} text-center`}>
              <p role="alert" className="text-sm text-red-600">{mensajeCarga}</p>
              <Link to="/seguimiento" className="mt-4 inline-block text-sm font-semibold text-primary hover:text-primary-dark">
                Volver a consultar mi trámite
              </Link>
            </div>
          )}

          {fase === 'no_disponible' && (
            <div className={`mt-8 ${CLASES_TARJETA} text-center`}>
              <p className="font-semibold text-ink">
                {formulario.datos_enviados ? 'Ya recibimos tus datos' : 'Este formulario no está disponible'}
              </p>
              <p className="mt-2 text-sm text-gray-600">
                {formulario.datos_enviados
                  ? 'No necesitas hacer nada más aquí. Puedes seguir el avance de tu trámite en la página de seguimiento.'
                  : 'Por ahora no hay datos que debas completar para este trámite. Revisa el estado en la página de seguimiento.'}
              </p>
              <Link to="/seguimiento" className="mt-4 inline-block text-sm font-semibold text-primary hover:text-primary-dark">
                Ver el estado de mi trámite
              </Link>
            </div>
          )}

          {fase === 'form' && (
            <>
              <p className="mt-2 text-gray-600 text-center">
                {formulario.nombre_servicio} · Código {formulario.codigo_seguimiento}
              </p>

              {avisoServidor && (
                <div role="alert" className="mt-6 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
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
                <div className="mt-6 rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-800">
                  Recuperamos lo que habías escrito el {formatearFecha(borradorDe)}. Revísalo antes de continuar.
                </div>
              )}

              {registrados.length > 0 && (
                <div className={`mt-6 ${CLASES_TARJETA}`}>
                  <h2 className="font-semibold text-ink">Datos que ya tenemos registrados</h2>
                  <p className="mt-1 text-sm text-gray-600">
                    Por seguridad se muestran parcialmente y no puedes modificarlos aquí.
                  </p>
                  <dl className="mt-4 space-y-3">
                    {registrados.map((c) => (
                      <div key={c.clave}>
                        <dt className="text-sm font-medium text-gray-700">{c.etiqueta}</dt>
                        <dd className="mt-1 rounded-md bg-gray-100 px-3 py-2 text-sm text-gray-700">
                          {c.valor_enmascarado}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </div>
              )}

              <form onSubmit={irARevision} noValidate className={`mt-6 ${CLASES_TARJETA} space-y-4`}>
                <h2 className="font-semibold text-ink">Datos que debes completar</h2>
                                {pendientes.length > 0 && (
                  <p className="text-sm text-gray-600">
                    Lo que escribes se guarda solo en este navegador mientras avanzas. No se envía a Easy Office
                    hasta que confirmes al final.
                  </p>
                )}

                {pendientes.length === 0 && (
                  <p className="text-sm text-gray-600">No necesitas ingresar más datos. Continúa para confirmar.</p>
                )}

                {pendientes.map((c) => {
                  const error = errorDe(c.clave)
                  const attrs = atributosInput(c.tipo)
                  const id = `campo-${c.clave}`
                  return (
                    <div key={c.clave}>
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
                        className={`mt-1 w-full border rounded-md px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:border-primary ${
                          error ? 'border-red-400 focus:ring-red-200' : 'border-gray-300 focus:ring-primary/40'
                        }`}
                      />
                      <div id={`${id}-ayuda`}>
                        {c.ayuda && !error && <p className="mt-1 text-xs text-gray-500">{c.ayuda}</p>}
                        {error && (
                          <p role="alert" className="mt-1 text-xs text-red-600">
                            {error}
                          </p>
                        )}
                      </div>
                    </div>
                  )
                })}

                <button
                  type="submit"
                  className="w-full bg-primary hover:bg-primary-dark text-white font-semibold py-3 rounded-md transition-colors"
                >
                  Revisar mis datos
                </button>

                {hayAlgoEscrito && (
                  <div className="text-center text-sm">
                    {!confirmandoDescarte ? (
                      <button
                        type="button"
                        onClick={() => setConfirmandoDescarte(true)}
                        className="text-gray-500 underline hover:text-gray-700"
                      >
                        Descartar borrador
                      </button>
                    ) : (
                      <span className="text-gray-700">
                        ¿Borrar todo lo que escribiste?{' '}
                        <button type="button" onClick={descartar} className="font-semibold text-red-600 underline">
                          Sí, borrar
                        </button>{' '}
                        <button
                          type="button"
                          onClick={() => setConfirmandoDescarte(false)}
                          className="text-gray-500 underline"
                        >
                          Cancelar
                        </button>
                      </span>
                    )}
                  </div>
                )}
              </form>
            </>
          )}

          {fase === 'revision' && (
            <>
              <p className="mt-2 text-gray-600 text-center">
                Revisa con calma. Después de enviar no podrás editar estos datos.
              </p>

              <div className={`mt-6 ${CLASES_TARJETA}`}>
                <h2 className="font-semibold text-ink">Tus datos</h2>
                {pendientes.length === 0 ? (
                  <p className="mt-2 text-sm text-gray-600">No hay datos nuevos para enviar.</p>
                ) : (
                  <dl className="mt-4 space-y-3">
                    {pendientes.map((c) => (
                      <div key={c.clave}>
                        <dt className="text-sm text-gray-500">{c.etiqueta}</dt>
                        <dd className="font-medium text-ink break-words">
                          {formatearParaResumen(c, valores[c.clave])}
                        </dd>
                      </div>
                    ))}
                  </dl>
                )}
                <button
                  type="button"
                  onClick={() => {
                    setFase('form')
                    subirAlInicio()
                  }}
                  className="mt-4 text-sm font-semibold text-primary hover:text-primary-dark"
                >
                  Volver a editar
                </button>
              </div>

              <div className={`mt-6 ${CLASES_TARJETA} space-y-5`}>
                <fieldset>
                  <legend className="text-sm font-medium text-gray-700">
                    ¿Eres el representante legal de la empresa?
                  </legend>
                  <div className="mt-2 flex gap-6">
                    <label className="flex items-center gap-2 text-sm text-gray-700">
                      <input
                        type="radio"
                        name="representante"
                        checked={esRepresentante === true}
                        onChange={() => setEsRepresentante(true)}
                      />
                      Sí
                    </label>
                    <label className="flex items-center gap-2 text-sm text-gray-700">
                      <input
                        type="radio"
                        name="representante"
                        checked={esRepresentante === false}
                        onChange={() => setEsRepresentante(false)}
                      />
                      No
                    </label>
                  </div>
                </fieldset>

                <div>
                  <p className="text-sm font-medium text-gray-700">Tratamiento de tus datos</p>
                  <p className="mt-1 rounded-md bg-gray-50 border border-gray-200 p-3 text-xs text-gray-600">
                    {TEXTO_CONSENTIMIENTO}
                  </p>
                  <label className="mt-2 flex items-start gap-2 text-sm text-gray-700">
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={consentimiento}
                      onChange={(e) => setConsentimiento(e.target.checked)}
                    />
                    Leí y acepto el tratamiento de mis datos.
                  </label>
                </div>

                <label className="flex items-start gap-2 text-sm text-gray-700">
                  <input
                    type="checkbox"
                    className="mt-1"
                    checked={aceptaNoEditar}
                    onChange={(e) => setAceptaNoEditar(e.target.checked)}
                  />
                  {TEXTO_NO_EDITAR}
                </label>

                {errorEnvio && (
                  <div role="alert" className="text-sm text-red-600">
                    <p>{errorEnvio.mensaje}</p>
                    {errorEnvio.estado === 409 && (
                      <Link to="/seguimiento" className="mt-1 inline-block font-semibold text-primary hover:text-primary-dark">
                        Ver el estado de mi trámite
                      </Link>
                    )}
                  </div>
                )}

                <button
                  type="button"
                  onClick={enviar}
                  disabled={enviando || esRepresentante === null || !consentimiento || !aceptaNoEditar}
                  className="w-full bg-primary hover:bg-primary-dark disabled:bg-gray-300 disabled:cursor-not-allowed text-white font-semibold py-3 rounded-md transition-colors"
                >
                  {enviando ? 'Enviando...' : 'Enviar mis datos'}
                </button>
              </div>
            </>
          )}

          {fase === 'enviado' && (
            <div className={`mt-8 ${CLASES_TARJETA} text-center`}>
              <p className="text-lg font-semibold text-ink">¡Recibimos tus datos!</p>
              <p className="mt-2 text-sm text-gray-600">
                {resultado?.estado_actual === 'en_revision'
                  ? 'Easy Office revisará tu información antes de continuar con tu trámite.'
                  : 'Ya estamos trabajando en tu trámite.'}{' '}
                Puedes seguir el avance con tu código de seguimiento.
              </p>
              <Link
                to="/seguimiento"
                className="mt-6 inline-block bg-primary hover:bg-primary-dark text-white font-semibold px-6 py-3 rounded-md transition-colors"
              >
                Ver el estado de mi trámite
              </Link>
            </div>
          )}
        </div>
      </main>

      <Footer />
    </div>
  )
}