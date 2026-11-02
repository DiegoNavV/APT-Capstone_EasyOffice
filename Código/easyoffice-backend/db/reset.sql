-- =========================================================
-- CRM Easy Office — Reinicio COMPLETO de la base de datos
-- BORRA TODAS LAS TABLAS Y SUS DATOS. Usar solo en desarrollo.
--
-- No vive en db/init/ a proposito: asi nunca se ejecuta por accidente junto
-- con el esquema. Despues de correrlo, volver a ejecutar en orden los archivos
-- de db/init/ (01 a 05). En Docker es mas simple: docker compose down -v.
-- =========================================================

-- CASCADE elimina tambien FK, triggers y vistas que dependen de las tablas.
DROP TABLE IF EXISTS
    historial_estado,
    datos_empresa_tramite,
    tramite,
    solicitud_contacto,
    plantilla_documento,
    refresh_token,
    usuario,
    rol,
    cliente,
    empresa,
    representante_legal,
    sucursal,
    servicio_ofrecido,
    ciclo_pago_defecto,
    estado_tramite,
    tipo_tramite
CASCADE;

DROP FUNCTION IF EXISTS
    fn_normalizar_rut(TEXT),
    fn_normalizar_email(TEXT),
    fn_usuario_normalizar(),
    fn_cliente_normalizar(),
    fn_solicitud_normalizar(),
    fn_empresa_normalizar(),
    fn_representante_normalizar(),
    fn_set_fecha_actualizacion(),
    fn_historial_no_duplicado(),
    fn_historial_inmutable(),
    fn_historial_sincronizar_tramite(),
    fn_sucursal_iniciales_fijas();
