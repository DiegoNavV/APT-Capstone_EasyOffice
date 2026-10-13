-- Migracion 001: datos de empresa que entrega el cliente con su codigo.
-- Para bases YA creadas. Se puede ejecutar mas de una vez sin problema.

CREATE TABLE IF NOT EXISTS datos_empresa_tramite (
    id_datos                     SERIAL PRIMARY KEY,
    id_tramite                   INTEGER NOT NULL UNIQUE REFERENCES tramite(id_tramite),
    razon_social                 VARCHAR(200) NOT NULL,
    rut_empresa                  VARCHAR(15) NOT NULL,
    datos                        JSONB NOT NULL DEFAULT '{}'::jsonb,
    solicitante_es_representante BOOLEAN NOT NULL,
    consentimiento_aceptado      BOOLEAN NOT NULL CHECK (consentimiento_aceptado),
    fecha_envio                  TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_datos_empresa_rut ON datos_empresa_tramite(rut_empresa);