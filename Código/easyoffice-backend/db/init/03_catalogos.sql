-- =========================================================
-- CRM Easy Office — Catalogos fijos
-- Necesarios en TODO ambiente (tambien produccion): la app y los DEFAULT del
-- esquema dependen de estos codigos ('esperando_datos', 'ÚNICO', ...). Sin
-- ellos no se puede crear ningun tramite. Cambiar un codigo implica cambiar
-- tambien la app.
-- =========================================================

INSERT INTO estado_tramite (codigo, etiqueta, orden, es_final, documento_disponible, permite_regenerar) VALUES
    ('esperando_datos',  'Esperando datos del cliente', 1, FALSE, FALSE, TRUE),
    ('en_revision',      'En revisión',                 2, FALSE, FALSE, TRUE),
    ('procesando_firma', 'Procesando firma',            3, FALSE, FALSE, TRUE),
    ('firmado',          'Firmado',                     4, FALSE, TRUE,  FALSE),
    ('entregado',        'Entregado',                   5, TRUE,  TRUE,  FALSE),
    ('cancelado',        'Cancelado',                   6, TRUE,  FALSE, FALSE),
    -- El cliente rechazo el documento en la firma o vencio el plazo para firmar.
    -- No es final: se puede corregir y reenviar a firma.
    ('rechazado',        'Rechazado',                   7, FALSE, FALSE, TRUE)
ON CONFLICT (codigo) DO NOTHING;

-- Codigos iguales a CICLOS_PAGO de app/condiciones.py.
INSERT INTO ciclo_pago_defecto (codigo, nombre, meses, orden, activo) VALUES
    ('ÚNICO',      'Único',      NULL, 1, TRUE),
    ('ANUAL',      'Anual',      12,   2, TRUE),
    ('SEMESTRAL',  'Semestral',  6,    3, TRUE),
    ('TRIMESTRAL', 'Trimestral', 3,    4, TRUE),
    ('MENSUAL',    'Mensual',    1,    5, TRUE)
ON CONFLICT (codigo) DO NOTHING;
