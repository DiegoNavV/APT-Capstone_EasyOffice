export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

async function solicitar(path, options = {}) {
  const res = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    // Obligatorio para que el navegador mande/reciba la cookie httpOnly del
    // refresh token (ver app/routers/auth.py en easyoffice-backend).
    credentials: 'include',
    ...options
  })

  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw new ApiError(data.detail || 'Ocurrió un error inesperado', res.status)
  }
  return data
}

export function login({ email, password }) {
  return solicitar('/api/auth/login', { body: JSON.stringify({ email, password }) })
}

export function obtenerUsuarioActual(accessToken) {
  return solicitar('/api/auth/me', {
    method: 'GET',
    headers: { Authorization: `Bearer ${accessToken}` }
  })
}

export function cerrarSesionApi() {
  // Revoca el refresh token en el servidor (ver /auth/logout). Si no se
  // llama, la cookie httpOnly sigue siendo válida aunque el frontend "olvide"
  // el access token.
  return solicitar('/api/auth/logout')
}

export function refrescarToken() {
  // No manda body: el refresh token viaja en la cookie httpOnly (credentials:
  // 'include' en `solicitar`), el navegador la agrega solo. 401 si no hay
  // cookie, está vencida o fue revocada (ver AuthContext.jsx).
  return solicitar('/api/auth/refresh')
}
