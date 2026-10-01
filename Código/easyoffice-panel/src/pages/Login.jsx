import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Logo from '../components/Logo.jsx'
import TextField from '../components/TextField.jsx'
import Button from '../components/Button.jsx'
import { ApiError, login, obtenerUsuarioActual, verificarDosFactores } from '../lib/api.js'
import { useAuth } from '../lib/AuthContext.jsx'

export default function Login() {
  const navigate = useNavigate()
  const { iniciarSesion } = useAuth()

  const [paso, setPaso] = useState('credenciales') // 'credenciales' | 'dos_factores'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [codigo, setCodigo] = useState('')
  const [ticket, setTicket] = useState(null)
  const [cargando, setCargando] = useState(false)
  const [error, setError] = useState(null)

  async function completarSesion(accessToken) {
    const usuario = await obtenerUsuarioActual(accessToken)
    iniciarSesion(accessToken, usuario)
    navigate('/panel')
  }

  async function handleSubmitCredenciales(e) {
    e.preventDefault()
    setCargando(true)
    setError(null)
    try {
      const respuesta = await login({ email, password })
      if (respuesta.requiere_2fa) {
        setTicket(respuesta.ticket)
        setPaso('dos_factores')
      } else {
        await completarSesion(respuesta.access_token)
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No pudimos conectar con el servidor.')
    } finally {
      setCargando(false)
    }
  }

  async function handleSubmitCodigo(e) {
    e.preventDefault()
    setCargando(true)
    setError(null)
    try {
      const respuesta = await verificarDosFactores({ ticket, codigo })
      await completarSesion(respuesta.access_token)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No pudimos conectar con el servidor.')
    } finally {
      setCargando(false)
    }
  }

  return (
    <div className="bg-canvas min-h-screen flex flex-col items-center justify-center gap-4 px-4">
      <div className="bg-surface border border-line rounded-2xl shadow-[0px_10px_30px_0px_rgba(26,41,66,0.1)] flex flex-col gap-5 items-start p-10 w-full max-w-[440px]">
        <Logo />

        {paso === 'credenciales' ? (
          <>
            <div className="flex flex-col gap-1">
              <h1 className="text-[22px] font-semibold text-ink-primary leading-tight">Inicia sesión</h1>
              <p className="text-sm text-ink-secondary">CRM de gestión documental de Easy Office</p>
            </div>

            <form onSubmit={handleSubmitCredenciales} className="flex flex-col gap-5 w-full">
              <TextField
                id="email"
                label="Correo electrónico"
                type="email"
                autoComplete="username"
                placeholder="agente@easyoffice.cl"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
              <TextField
                id="password"
                label="Contraseña"
                type="password"
                autoComplete="current-password"
                placeholder="••••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />

              <span
                className="text-[13px] font-medium text-ink-link text-right w-full cursor-not-allowed select-none"
                title="Recuperación de contraseña: aún no implementada"
              >
                ¿Olvidaste tu contraseña?
              </span>

              {error && <p className="text-sm text-red-600">{error}</p>}

              <Button loading={cargando}>Ingresar</Button>

              <p className="text-xs text-ink-muted text-center w-full">
                Acceso para perfiles Agente y Administrador
              </p>
            </form>
          </>
        ) : (
          <>
            <div className="flex flex-col gap-1">
              <h1 className="text-[22px] font-semibold text-ink-primary leading-tight">Verificación en dos pasos</h1>
              <p className="text-sm text-ink-secondary">
                Ingresa el código de 6 dígitos de tu app autenticadora.
              </p>
            </div>

            <form onSubmit={handleSubmitCodigo} className="flex flex-col gap-5 w-full">
              <TextField
                id="codigo"
                label="Código de verificación"
                inputMode="numeric"
                pattern="\d{6}"
                maxLength={6}
                placeholder="000000"
                value={codigo}
                onChange={(e) => setCodigo(e.target.value.replace(/\D/g, '').slice(0, 6))}
                autoFocus
                required
              />

              {error && <p className="text-sm text-red-600">{error}</p>}

              <Button loading={cargando} disabled={codigo.length !== 6}>
                Verificar
              </Button>

              <button
                type="button"
                onClick={() => {
                  setPaso('credenciales')
                  setCodigo('')
                  setError(null)
                }}
                className="text-xs text-ink-muted text-center w-full hover:text-ink-secondary"
              >
                Volver
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  )
}
