-- Migracion 002: los datos de la empresa se guardan una sola vez y se reutilizan entre tramites (tabla empresa). datos_empresa_tramite 
-- queda olo como registro del envio unico de cada tramite.
-- Para bases YA creadas. Corre dentro de una transaccion: si algo falla, no se aplica nada.

BEGIN;

-- Seguridad: si la tabla ya tiene filas con datos, no se borra nada.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'datos_empresa_tramite' AND column_name = 'razon_social'
    ) AND EXISTS (SELECT 1 FROM datos_empresa_tramite) THEN
        RAISE EXCEPTION 'datos_empresa_tramite tiene filas: migrar sus datos a empresa antes de continuar';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS empresa (
    id_empresa          SERIAL PRIMARY KEY,
    rut_empresa         VARCHAR(15) NOT NULL UNIQUE,
    razon_social        VARCHAR(200) NOT NULL,
    datos               JSONB NOT NULL DEFAULT '{}'::jsonb,
    fecha_creacion      TIMESTAMP NOT NULL DEFAULT now(),
    fecha_actualizacion TIMESTAMP NOT NULL DEFAULT now()
);

ALTER TABLE tramite ADD COLUMN IF NOT EXISTS id_empresa INTEGER REFERENCES empresa(id_empresa);
CREATE INDEX IF NOT EXISTS idx_tramite_id_empresa ON tramite(id_empresa);

ALTER TABLE datos_empresa_tramite
    DROP COLUMN IF EXISTS razon_social,
    DROP COLUMN IF EXISTS rut_empresa,
    DROP COLUMN IF EXISTS datos;

COMMIT;