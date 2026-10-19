-- Migracion 004: plantillas de documentos con versiones (trazabilidad).
-- Para bases YA creadas. Corre dentro de una transaccion y se puede ejecutar mas de una vez sin problema.
-- Cada archivo subido es una version nueva de un servicio; las anteriores no se borran.
-- Solo puede haber UNA version activa por servicio.

BEGIN;

ALTER TABLE plantilla_documento ADD COLUMN IF NOT EXISTS nombre_original  VARCHAR(255);
ALTER TABLE plantilla_documento ADD COLUMN IF NOT EXISTS hash_sha256      VARCHAR(64);
ALTER TABLE plantilla_documento ADD COLUMN IF NOT EXISTS tamano_bytes     INTEGER;
ALTER TABLE plantilla_documento ADD COLUMN IF NOT EXISTS marcas           JSONB;
ALTER TABLE plantilla_documento ADD COLUMN IF NOT EXISTS id_usuario_subio INTEGER REFERENCES usuario(id_usuario);

CREATE UNIQUE INDEX IF NOT EXISTS uq_plantilla_servicio_version
    ON plantilla_documento(id_servicio, version);
CREATE UNIQUE INDEX IF NOT EXISTS uq_plantilla_activa_por_servicio
    ON plantilla_documento(id_servicio) WHERE activa;

COMMIT;