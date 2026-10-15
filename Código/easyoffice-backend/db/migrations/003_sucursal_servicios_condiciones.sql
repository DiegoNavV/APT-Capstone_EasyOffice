-- Migracion 003: sucursales, catalogo de servicios que vende Easy Office, y folio / condiciones del contrato en el tramite.
-- Para bases YA creadas. Corre dentro de una transaccion y se puede ejecutar mas de una vez sin problema.

BEGIN;

CREATE TABLE IF NOT EXISTS sucursal (
    id_sucursal    SERIAL PRIMARY KEY,
    iniciales      VARCHAR(5) NOT NULL UNIQUE,
    nombre         VARCHAR(100) NOT NULL,
    direccion      VARCHAR(200) NOT NULL,
    comuna         VARCHAR(100) NOT NULL,
    region         VARCHAR(100) NOT NULL,
    rol_propiedad  VARCHAR(30),
    activa         BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS servicio_ofrecido (
    id_servicio_ofrecido SERIAL PRIMARY KEY,
    nombre               VARCHAR(150) NOT NULL UNIQUE,
    descripcion          TEXT,
    precio_referencia    INTEGER CHECK (precio_referencia IS NULL OR precio_referencia >= 0),
    ciclo_pago_defecto   VARCHAR(20),
    activo               BOOLEAN NOT NULL DEFAULT TRUE
);

ALTER TABLE tramite ADD COLUMN IF NOT EXISTS id_sucursal INTEGER REFERENCES sucursal(id_sucursal);
ALTER TABLE tramite ADD COLUMN IF NOT EXISTS folio VARCHAR(20);
ALTER TABLE tramite ADD COLUMN IF NOT EXISTS condiciones JSONB;

CREATE UNIQUE INDEX IF NOT EXISTS uq_tramite_folio ON tramite(folio);
CREATE INDEX IF NOT EXISTS idx_tramite_id_sucursal ON tramite(id_sucursal);

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

COMMIT;