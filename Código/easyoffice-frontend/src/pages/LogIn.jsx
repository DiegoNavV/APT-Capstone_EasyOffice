import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Logo from '../components/Logo.jsx'
import TextField from '../components/TextField.jsx'
import Button from '../components/Button.jsx'
import { ApiError, login, obtenerUsuarioActual } from '../lib/api.js'
import { useAuth } from '../lib/AuthContext.jsx'

// Pantalla de inicio de sesión (ruta "/").
// El usuario ingresa correo + contraseña; si son correctos se guarda la sesión
// y se navega a /panel.

export default function LogIn() {
  const navigate = useNavigate()
  const { iniciarSesion, usuario, verificando } = useAuth()

  // Lo que el usuario escribe en cada campo.
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  // Estado de la petición en curso: desactiva el botón y muestra errores.
  const [cargando, setCargando] = useState(false)
  const [error, setError] = useState(null)

  // Si el refresh token de la cookie (ver AuthContext.jsx) ya recuperó una
  // sesión al cargar la página, no tiene sentido mostrarle el login a alguien
  // que ya está autenticado.
  useEffect(() => {
    if (!verificando && usuario) navigate('/panel', { replace: true })
  }, [verificando, usuario, navigate])

  // Se ejecuta al enviar el formulario.
  async function handleSubmit(e) {
    e.preventDefault() // evita que el navegador recargue la página
    setCargando(true)
    setError(null)

    try {
      // 1. Valida las credenciales y obtiene el token de acceso.
      const { access_token, expires_in_minutes } = await login({ email, password })

      // 2. Con el token pide los datos del usuario (/auth/me).
      const usuario = await obtenerUsuarioActual(access_token)

      // 3. Guarda la sesión en el AuthContext (programa el refresco
      //    automático antes de que expire) y entra al panel.
      iniciarSesion(access_token, usuario, expires_in_minutes)
      navigate('/panel')

    } catch (err) {
      // ApiError = el servidor respondió con un error (ej. "Credenciales inválidas").
      // Cualquier otro error = no hubo respuesta (servidor caído, sin red, etc.).
      setError(err instanceof ApiError ? err.message : 'No pudimos conectar con el servidor.')

    } finally {
      setCargando(false)

    }
  }

  // Mientras se intenta recuperar una sesión previa (refresh token de la
  // cookie) no se muestra el formulario, para no hacerlo parpadear justo
  // antes de redirigir a /panel.
  if (verificando) return null

  return (
    <div className="bg-canvas min-h-screen flex flex-col items-center justify-center gap-4 px-4">
      <div className="bg-surface border border-line rounded-2xl shadow-[0px_10px_30px_0px_rgba(26,41,66,0.1)] flex flex-col gap-5 items-start p-10 w-full max-w-[440px]">
        <Logo />

        <div className="flex flex-col gap-1">
          <h1 className="text-[22px] font-semibold text-ink-primary leading-tight">Inicia sesión</h1>
          <p className="text-sm text-ink-secondary">CRM de gestión documental de Easy Office</p>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-5 w-full">
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

          <Button loading={cargando} textoCargando="Ingresando…">
            Ingresar
          </Button>

          <p className="text-xs text-ink-muted text-center w-full">
            Acceso para personas Autorizadas
          </p>
        </form>
      </div>
    </div>
  )
}
