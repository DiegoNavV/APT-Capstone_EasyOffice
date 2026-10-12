import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from './api.js'
import { obtenerNovedades } from './solicitudesApi.js'

// Aviso de solicitudes nuevas por consulta periódica (polling). Todo el mecanismo vive en este archivo: si algún día se cambia a SSE u 
// otro medio, solo se reemplaza este hook y la pantalla de Solicitudes no se entera.
//
// Cómo funciona:
//  - Al abrir la vista pide el "punto de partida": el id más alto que existe.
//    Solicitudes.jsx espera a `listo` antes de cargar la lista, así ninguna
//    solicitud queda entre el punto de partida y la lista.
//  - Cada 30 s pregunta cuántas solicitudes hay con id mayor al punto de
//    partida (consulta liviana: solo números, ver GET .../novedades).
//  - No consulta mientras la pestaña esté oculta; al volver a verla consulta
//    de inmediato.
//  - Errores de red: se ignoran en silencio y se reintenta en el siguiente
//    ciclo. 401 (sesión vencida): se llama a onSesionVencida.

export const INTERVALO_NOVEDADES_MS = 30_000

export function useNovedadesSolicitudes({ accessToken, onSesionVencida, intervaloMs = INTERVALO_NOVEDADES_MS }) {
  const [nuevas, setNuevas] = useState(0)
  const [listo, setListo] = useState(false)

  // id más alto al abrir o refrescar la lista; null = todavía no se pudo obtener.
  const baseRef = useRef(null)
  // Sube en cada reinicio: una respuesta que llega de una época anterior se descarta.
  const epocaRef = useRef(0)
  const montadoRef = useRef(true)
  const enCursoRef = useRef(false)
  // Siempre el último valor, sin reiniciar el temporizador cuando el access
  // token se renueva (cada ~85 min).
  const tokenRef = useRef(accessToken)
  const vencidaRef = useRef(onSesionVencida)
  useEffect(() => {
    tokenRef.current = accessToken
    vencidaRef.current = onSesionVencida
  })

  useEffect(() => {
    montadoRef.current = true
    return () => {
      montadoRef.current = false
    }
  }, [])

  const haySesion = Boolean(accessToken)

  // Una consulta: sin punto de partida lo establece; con él cuenta las nuevas.
  const consultar = useCallback(async () => {
    const epoca = epocaRef.current
    const desdeId = baseRef.current
    try {
      const datos = await obtenerNovedades({ accessToken: tokenRef.current, desdeId })
      if (!montadoRef.current || epoca !== epocaRef.current) return
      if (desdeId === null) {
        baseRef.current = datos.ultimo_id
        setNuevas(0)
      } else {
        setNuevas(datos.nuevas)
      }
    } catch (e) {
      if (!montadoRef.current || epoca !== epocaRef.current) return
      if (e instanceof ApiError && e.status === 401) vencidaRef.current?.()
      // Cualquier otro error: se reintenta en el siguiente ciclo.
    }
  }, [])

  // Punto de partida inicial.
  useEffect(() => {
    if (!haySesion) return
    let cancelado = false
    consultar().finally(() => {
      if (!cancelado) setListo(true)
    })
    return () => {
      cancelado = true
    }
  }, [haySesion, consultar])

  // Consulta periódica.
  useEffect(() => {
    if (!haySesion || !listo) return

    async function sondear() {
      if (document.hidden || enCursoRef.current) return
      enCursoRef.current = true
      try {
        await consultar()
      } finally {
        enCursoRef.current = false
      }
    }

    function alCambiarVisibilidad() {
      if (!document.hidden) sondear()
    }

    const id = setInterval(sondear, intervaloMs)
    document.addEventListener('visibilitychange', alCambiarVisibilidad)
    return () => {
      clearInterval(id)
      document.removeEventListener('visibilitychange', alCambiarVisibilidad)
    }
  }, [haySesion, listo, intervaloMs, consultar])

  // Se llama justo antes de recargar la lista: borra el aviso y toma un punto
  // de partida nuevo. Nunca lanza error; si la consulta falla, el siguiente
  // ciclo vuelve a intentarlo.
  const reiniciar = useCallback(async () => {
    epocaRef.current += 1
    baseRef.current = null
    setNuevas(0)
    await consultar()
  }, [consultar])

  return { nuevas, listo, reiniciar }
}