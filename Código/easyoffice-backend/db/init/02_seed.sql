-- =========================================================
-- Datos semilla mínimos para poder probar el módulo de
-- "formulario de contacto -> solicitud -> trámite".
-- Los IDs de servicio_contratado coinciden con los que ya
-- usa el frontend público (easyoffice-web/src/pages/IniciarTramite.jsx).
-- =========================================================

INSERT INTO rol (id_rol, nombre, descripcion) VALUES
    (1, 'administrador', 'Acceso total al panel interno'),
    (2, 'agente', 'Gestiona solicitudes de contacto y trámites asignados')
ON CONFLICT (id_rol) DO NOTHING;

-- Usuario de prueba para poder asignar/convertir solicitudes mientras no
-- existe el módulo de autenticación (Épica A). password_hash es un valor
-- ficticio, NO usar en producción.
INSERT INTO usuario (id_usuario, id_rol, nombre, email, password_hash, activo) VALUES
    (1, 2, 'Agente de Prueba', 'agente.prueba@easyoffice.cl', 'CAMBIAR_CUANDO_EXISTA_AUTH', TRUE)
ON CONFLICT (id_usuario) DO NOTHING;

INSERT INTO servicio_contratado (id_servicio, nombre, descripcion, requiere_revision_humana, activo) VALUES
    (1, 'Contrato de servicio', 'Generación y firma de contrato de servicio con Easy Office.', FALSE, TRUE),
    (2, 'Autorización de domicilio tributario', 'Generación y firma de autorización de domicilio tributario.', FALSE, TRUE)
ON CONFLICT (id_servicio) DO NOTHING;

-- Reinicia las secuencias para que los próximos INSERT con ID autogenerado
-- (SERIAL) no choquen con los IDs fijos insertados arriba.
SELECT setval('rol_id_rol_seq', (SELECT MAX(id_rol) FROM rol));
SELECT setval('usuario_id_usuario_seq', (SELECT MAX(id_usuario) FROM usuario));
SELECT setval('servicio_contratado_id_servicio_seq', (SELECT MAX(id_servicio) FROM servicio_contratado));