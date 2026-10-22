-- Migracion 005: limpieza de indices (Nivel 1 del pulido del esquema) -- sin
-- cambios de comportamiento para la aplicacion. Para bases YA creadas. Corre
-- dentro de una transaccion y se puede ejecutar mas de una vez sin problema.

BEGIN;

-- tramite.codigo_seguimiento ya es UNIQUE arriba en 01_schema.sql, lo que crea
-- su propio indice. Este indice explicito duplicaba exactamente lo mismo.
DROP INDEX IF EXISTS idx_tramite_codigo_seguimiento;

-- usuario.id_cliente: columna reservada para cuando un cliente pudiera tener
-- cuenta propia. Nunca se uso -- no esta mapeada en app/models.py y no aparece
-- en ningun router/crud/test. Se elimina para no dejar una FK muerta.
ALTER TABLE usuario DROP COLUMN IF EXISTS id_cliente;

-- Postgres no indexa automaticamente las columnas FK (a diferencia de MySQL).
-- Estas 5 si se filtran o se unen hoy en el codigo (app/crud.py, app/plantillas.py,
-- app/documentos.py) -- sin indice, cada consulta hace un seq scan, y cada
-- UPDATE/DELETE en la tabla padre escanea toda la tabla hija para revisar la FK.
CREATE INDEX IF NOT EXISTS idx_tramite_id_cliente ON tramite(id_cliente);
CREATE INDEX IF NOT EXISTS idx_tramite_id_servicio ON tramite(id_servicio);
CREATE INDEX IF NOT EXISTS idx_tramite_id_usuario_responsable ON tramite(id_usuario_responsable);
CREATE INDEX IF NOT EXISTS idx_tramite_id_empresa ON tramite(id_empresa);
CREATE INDEX IF NOT EXISTS idx_plantilla_documento_id_servicio ON plantilla_documento(id_servicio);

COMMIT;
