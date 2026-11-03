-- 001_integracion_firma.sql
--
-- Prepara la base para integrar la API de firma (Ley 19.799).
--
-- Que cambia:
--   1. Nuevo estado de tramite 'rechazado': el cliente rechazo el documento
--      en la firma o vencio el plazo para firmar. No es final: se puede
--      corregir y reenviar a firma.
--   2. Nueva columna tramite.documento_firma_id: id (UUID en texto) del
--      documento en la API de firma. Se llena al enviarlo a firmar y sirve
--      para reconocer los avisos (webhook) que llegan despues.
--
-- Los mismos cambios estan en db/init/01_schema.sql y 03_catalogos.sql,
-- para que una base nueva quede igual que una migrada.
--
-- Se puede ejecutar mas de una vez sin error.

BEGIN;

-- 1. Estado 'rechazado' (orden 7, despues de 'cancelado').
INSERT INTO estado_tramite (codigo, etiqueta, orden, es_final, documento_disponible, permite_regenerar)
VALUES ('rechazado', 'Rechazado', 7, FALSE, FALSE, TRUE)
ON CONFLICT (codigo) DO NOTHING;

-- 2. Columna con el id del documento en la API de firma.
ALTER TABLE tramite ADD COLUMN IF NOT EXISTS documento_firma_id VARCHAR (36);

-- Un documento de la API de firma pertenece a un solo tramite.
-- (ADD CONSTRAINT no tiene IF NOT EXISTS, por eso se revisa antes.)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_tramite_documento_firma'
    ) THEN
        ALTER TABLE tramite
            ADD CONSTRAINT uq_tramite_documento_firma UNIQUE (documento_firma_id);
    END IF;
END $$;

COMMIT;