-- =========================================================
-- CRM Easy Office — Datos SOLO para desarrollo
-- No cargar en produccion: excluir este archivo al montar db/init/.
-- =========================================================

-- Usuario de prueba para poder asignar/convertir solicitudes. hash_pswd es un
-- valor ficticio a proposito: esta cuenta NO puede iniciar sesion.
-- Para crear cuentas reales usar scripts/crear_user.py.
INSERT INTO usuario (id, rol_id, nombre, email, hash_pswd, activo) VALUES
    (1, 2, 'Agente de Prueba', 'agente.prueba@easyoffice.cl', 'CAMBIAR_CUANDO_EXISTA_AUTH', TRUE)
ON CONFLICT (id) DO NOTHING;

-- Reinicia la secuencia para que el proximo usuario autogenerado no choque con el id fijo.
SELECT setval('usuario_id_seq', (SELECT MAX(id) FROM usuario));
