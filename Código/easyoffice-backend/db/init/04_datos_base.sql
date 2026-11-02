-- =========================================================
-- CRM Easy Office — Datos base del negocio
-- Datos reales de Easy Office (hoja INFORMACIONES de su planilla) que se
-- pueden ajustar sin tocar la estructura. Van en todo ambiente.
-- =========================================================

INSERT INTO rol (id, nombre, descripcion) VALUES
    (1, 'administrador', 'Acceso total al panel interno'),
    (2, 'agente', 'Gestiona solicitudes de contacto y trámites asignados')
ON CONFLICT (id) DO NOTHING;

-- Los IDs coinciden con los que ya usa el frontend público
-- (easyoffice-web/src/pages/IniciarTramite.jsx).
INSERT INTO tipo_tramite (id, nombre, descripcion, revision_humana, activo) VALUES
    (1, 'Contrato de servicio', 'Generación y firma de contrato de servicio con Easy Office.', FALSE, TRUE),
    (2, 'Autorización de domicilio tributario', 'Generación y firma de autorización de domicilio tributario.', FALSE, TRUE)
ON CONFLICT (id) DO NOTHING;

-- Las iniciales LF y VL salen del formato de folio (LF-01-2026 / VL-01-2026).
-- La de San Antonio (SA) es una suposicion nuestra, y su region no venia en la
-- planilla: Easy Office debe confirmarlas. Ojo: la direccion de SA esta en
-- Algarrobo, pero la comuna dice San Antonio; confirmar antes de usarla en un
-- contrato real.
INSERT INTO sucursal (iniciales, nombre, direccion, comuna, region, rol_propiedad) VALUES
    ('LF', 'La Florida', 'Vicuña Mackenna Poniente #7255, Oficina 707', 'La Florida', 'Metropolitana', '271-147'),
    ('VL', 'Valparaíso', 'Blanco N°1215, Oficina 405', 'Valparaíso', 'Valparaíso', '15-12'),
    ('SA', 'San Antonio', 'El Potrerillo N°8, Oficina C, Algarrobo', 'San Antonio', 'Valparaíso', '267-56')
ON CONFLICT (iniciales) DO NOTHING;

-- Bodega sale de la planilla de muestra. Contabilidad se cotiza caso a caso:
-- sin precio ni ciclo de referencia. El agente puede ajustar precio y ciclo en
-- cada contrato.
INSERT INTO servicio_ofrecido (nombre, descripcion, precio_referencia, ciclo_pago_defecto_codigo) VALUES
    ('Creación de empresa', '*Constitución empresa en un día, hasta 3 socios  *Obtención de rut  *Domicilio tributario x 3 meses  * Inicio de actividad ante el SII  *Inscripción factura electrónica  * Gestión conjunta solicitud cuenta emprendedor BancoEstado', 49990, 'ÚNICO'),
    ('Domicilio tributario', '*Domicilio. Tributario, postal y comercial *Recepción de correspondencia fiscal *Escaneo de 1 página diaria de correspondencia fiscal no acumulable, sin costo *Uso 1 hora semanal de estación de trabajo *Inicio de actividades', 59990, 'ANUAL'),
    ('Web mail + dominio', '*Servicio web mail corporativo 1 GB + dominio x 1 año', 14990, 'ANUAL'),
    ('Contabilidad', NULL, NULL, NULL),
    ('Bodega', '*Bodega: 1 Cubo rack para pañol, con acceso Lun a Vie de 10 a 16 horas. Es prohibido almacenar todo tipo de sustancias químicas y/o biológicas; explosivos; residuos contaminantes; combustibles líquidos; gases tóxicos.', 71388, 'ANUAL')
ON CONFLICT (nombre) DO NOTHING;

-- Reinicia las secuencias para que los proximos INSERT con ID autogenerado
-- (SERIAL) no choquen con los IDs fijos insertados arriba.
SELECT setval('rol_id_seq', (SELECT MAX(id) FROM rol));
SELECT setval('tipo_tramite_id_seq', (SELECT MAX(id) FROM tipo_tramite));
