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
    // refresh token (ver app/api/v1/endpoints/auth.py en easyoffice-api).
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
  return solicitar('/api/v1/auth/login', { body: JSON.stringify({ email, password }) })
}

export function verificarDosFactores({ ticket, codigo }) {
  return solicitar('/api/v1/auth/2fa/verify', { body: JSON.stringify({ ticket, codigo }) })
}

export function obtenerUsuarioActual(accessToken) {
  return solicitar('/api/v1/auth/me', {
    method: 'GET',
    headers: { Authorization: `Bearer ${accessToken}` }
  })
}

export function cerrarSesionApi() {
  // Revoca el refresh token en el servidor (ver /auth/logout). Si no se
  // llama, la cookie httpOnly sigue siendo válida aunque el frontend "olvide"
  // el access token.
  return solicitar('/api/v1/auth/logout')
}
