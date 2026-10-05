import { createContext, useContext, useEffect, useRef, useState } from 'react'
import { cerrarSesionApi, obtenerUsuarioActual, refrescarToken } from './api.js'

const AuthContext = createContext(null)

// Cuánto antes de que expire el access token se pide uno nuevo. Con el
// default de 90 min del backend esto refresca a los 85 min; de sobra para
// que nunca llegue a expirar mientras la pestaña está abierta.
const MARGEN_MINUTOS = 5

export function AuthProvider({ children }) {
  // El access token vive SOLO en memoria (nunca localStorage/sessionStorage):
  // si quedara en storage persistente, un XSS podría leerlo directo. Lo que
  // sobrevive a un F5 o a cerrar la pestaña es el refresh token (cookie
  // httpOnly, invisible para JS) - con eso se recupera la sesión al montar.
  const [accessToken, setAccessToken] = useState(null)
  const [usuario, setUsuario] = useState(null)
  // true mientras se intenta recuperar la sesión al cargar la página. Las
  // pantallas que dependen de `usuario` deben esperar a que esto sea false
  // antes de decidir si redirigir al login (ver Panel.jsx y LogIn.jsx).
  const [verificando, setVerificando] = useState(true)

  // Timer del refresco proactivo (setTimeout), para poder cancelarlo en un
  // logout o antes de programar uno nuevo.
  const timerRef = useRef(null)

  function cancelarRefrescoProgramado() {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }

  function programarRefresco(expiresInMinutes) {
    cancelarRefrescoProgramado()
    const esperaMs = Math.max(expiresInMinutes - MARGEN_MINUTOS, 1) * 60 * 1000
    timerRef.current = setTimeout(refrescar, esperaMs)
  }

  // Pide un access token nuevo con el refresh token de la cookie (rota la
  // cookie en el servidor, ver /api/auth/refresh). Se usa tanto al cargar la
  // página como, de ahí en más, automáticamente antes de cada expiración.
  async function refrescar() {
    try {
      const { access_token, expires_in_minutes } = await refrescarToken()
      setAccessToken(access_token)
      programarRefresco(expires_in_minutes)
      return access_token
    } catch {
      // Sin sesión real (nunca inició sesión, o el refresh token venció o fue
      // revocado): se limpia todo, igual que un logout.
      cancelarRefrescoProgramado()
      setAccessToken(null)
      setUsuario(null)
      return null
    }
  }

  // Al montar la app: intenta recuperar la sesión con el refresh token antes
  // de mostrar nada que dependa de `usuario`.
  useEffect(() => {
    let cancelado = false

    async function recuperarSesion() {
      const token = await refrescar()
      if (token && !cancelado) {
        try {
          const datosUsuario = await obtenerUsuarioActual(token)
          if (!cancelado) setUsuario(datosUsuario)
        } catch {
          if (!cancelado) {
            cancelarRefrescoProgramado()
            setAccessToken(null)
            setUsuario(null)
          }
        }
      }
      if (!cancelado) setVerificando(false)
    }

    recuperarSesion()
    return () => {
      cancelado = true
      cancelarRefrescoProgramado()
    }
    // Se ejecuta una sola vez, al montar.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function iniciarSesion(accessToken, usuario, expiresInMinutes) {
    setAccessToken(accessToken)
    setUsuario(usuario)
    programarRefresco(expiresInMinutes)
  }

  async function cerrarSesion() {
    cancelarRefrescoProgramado()
    setAccessToken(null)
    setUsuario(null)
    try {
      await cerrarSesionApi()
    } catch {
      // Igual se limpia la sesión local aunque falle la llamada (ej. sin
      // conexión); el refresh token vence solo en REFRESH_TOKEN_EXPIRE_DAYS.
    }
  }

  return (
    <AuthContext.Provider value={{ accessToken, usuario, verificando, iniciarSesion, cerrarSesion }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth debe usarse dentro de <AuthProvider>')
  return ctx
}
