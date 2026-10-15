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

-- Usuario de prueba para poder asignar/convertir solicitudes. password_hash
-- es un valor ficticio a propósito: esta cuenta NO puede iniciar sesión.
-- Para crear cuentas reales usar scripts/crear_user.py.
INSERT INTO usuario (id_usuario, id_rol, nombre, email, password_hash, activo) VALUES
    (1, 2, 'Agente de Prueba', 'agente.prueba@easyoffice.cl', 'CAMBIAR_CUANDO_EXISTA_AUTH', TRUE)
ON CONFLICT (id_usuario) DO NOTHING;

INSERT INTO servicio_contratado (id_servicio, nombre, descripcion, requiere_revision_humana, activo) VALUES
    (1, 'Contrato de servicio', 'Generación y firma de contrato de servicio con Easy Office.', FALSE, TRUE),
    (2, 'Autorización de domicilio tributario', 'Generación y firma de autorización de domicilio tributario.', FALSE, TRUE)
ON CONFLICT (id_servicio) DO NOTHING;

-- Sucursales (hoja INFORMACIONES del formulario de Easy Office).
-- Las iniciales LF y VL salen del formato de folio (LF-01-2026 / VL-01-2026). La de San Antonio (SA) es una suposicion nuestra, y su 
-- region no venia en la planilla: Easy Office debe confirmarlas.
INSERT INTO sucursal (iniciales, nombre, direccion, comuna, region, rol_propiedad) VALUES
    ('LF', 'La Florida', 'Vicuña Mackenna Poniente #7255, Oficina 707', 'La Florida', 'Metropolitana', '271-147'),
    ('VL', 'Valparaíso', 'Blanco N°1215, Oficina 405', 'Valparaíso', 'Valparaíso', '15-12'),
    ('SA', 'San Antonio', 'El Potrerillo N°8, Oficina C, Algarrobo', 'San Antonio', 'Valparaíso', '267-56')
ON CONFLICT (iniciales) DO NOTHING;

-- Servicios que vende Easy Office, con precio y ciclo de pago de referencia (hoja INFORMACIONES; Bodega sale de la planilla de muestra). 
-- El agente puede ajustar precio y ciclo en cada contrato.
INSERT INTO servicio_ofrecido (nombre, descripcion, precio_referencia, ciclo_pago_defecto) VALUES
    ('Creación de empresa', '*Constitución empresa en un día, hasta 3 socios  *Obtención de rut  *Domicilio tributario x 3 meses  * Inicio de actividad ante el SII  *Inscripción factura electrónica  * Gestión conjunta solicitud cuenta emprendedor BancoEstado', 49990, 'ÚNICO'),
    ('Domicilio tributario', '*Domicilio. Tributario, postal y comercial *Recepción de correspondencia fiscal *Escaneo de 1 página diaria de correspondencia fiscal no acumulable, sin costo *Uso 1 hora semanal de estación de trabajo *Inicio de actividades', 59990, 'ANUAL'),
    ('Web mail + dominio', '*Servicio web mail corporativo 1 GB + dominio x 1 año', 14990, 'ANUAL'),
    ('Contabilidad', NULL, NULL, NULL),
    ('Bodega', '*Bodega: 1 Cubo rack para pañol, con acceso Lun a Vie de 10 a 16 horas. Es prohibido almacenar todo tipo de sustancias químicas y/o biológicas; explosivos; residuos contaminantes; combustibles líquidos; gases tóxicos.', 71388, 'ANUAL')
ON CONFLICT (nombre) DO NOTHING;

-- Reinicia las secuencias para que los próximos INSERT con ID autogenerado
-- (SERIAL) no choquen con los IDs fijos insertados arriba.
SELECT setval('rol_id_rol_seq', (SELECT MAX(id_rol) FROM rol));
SELECT setval('usuario_id_usuario_seq', (SELECT MAX(id_usuario) FROM usuario));
SELECT setval('servicio_contratado_id_servicio_seq', (SELECT MAX(id_servicio) FROM servicio_contratado));