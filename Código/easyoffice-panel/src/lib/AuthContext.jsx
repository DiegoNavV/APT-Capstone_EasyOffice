import { createContext, useContext, useState } from 'react'
import { cerrarSesionApi } from './api.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  // El access token vive SOLO en memoria (nunca localStorage/sessionStorage):
  // si quedara en storage persistente, un XSS podría leerlo directo. Al
  // recargar la página se pierde la sesión en memoria; retomarla con el
  // refresh token (cookie httpOnly) queda pendiente para cuando se arme el
  // resto del panel.
  const [accessToken, setAccessToken] = useState(null)
  const [usuario, setUsuario] = useState(null)

  function iniciarSesion(accessToken, usuario) {
    setAccessToken(accessToken)
    setUsuario(usuario)
  }

  async function cerrarSesion() {
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
    <AuthContext.Provider value={{ accessToken, usuario, iniciarSesion, cerrarSesion }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth debe usarse dentro de <AuthProvider>')
  return ctx
}
