-- =========================================================
-- CRM Easy Office — Modelo de datos v4: funciones, triggers y vistas
-- Son la ultima linea de defensa a nivel de base de datos, por si alguna vez
-- se escribe sin pasar por la app (un script, una migracion de datos, etc).
-- Se puede volver a ejecutar sobre una base existente: las funciones usan
-- CREATE OR REPLACE y cada trigger se elimina antes de crearse.
-- =========================================================


-- =========================================================
-- 1. NORMALIZACION DE RUT/RUN Y EMAIL
-- Igual que normalizar_rut / normalizar_email de app/utils.py. Un texto vacio
-- pasa a NULL, para que '' no cuente como "dato de contacto". Los UNIQUE de
-- run/rut/email dependen de esto: sin normalizar, '12.345.678-k' y
-- '12345678-K' serian dos personas distintas.
-- =========================================================
CREATE OR REPLACE FUNCTION fn_normalizar_rut(valor TEXT) RETURNS TEXT
LANGUAGE sql IMMUTABLE AS $$
    SELECT NULLIF(upper(replace(replace(trim(valor), '.', ''), ' ', '')), '')
$$;

CREATE OR REPLACE FUNCTION fn_normalizar_email(valor TEXT) RETURNS TEXT
LANGUAGE sql IMMUTABLE AS $$
    SELECT NULLIF(lower(trim(valor)), '')
$$;

CREATE OR REPLACE FUNCTION fn_usuario_normalizar() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.email := fn_normalizar_email(NEW.email);
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_usuario_normalizar ON usuario;
CREATE TRIGGER trg_usuario_normalizar
BEFORE INSERT OR UPDATE OF email ON usuario
FOR EACH ROW EXECUTE FUNCTION fn_usuario_normalizar();

CREATE OR REPLACE FUNCTION fn_cliente_normalizar() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.run   := fn_normalizar_rut(NEW.run);
    NEW.email := fn_normalizar_email(NEW.email);
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_cliente_normalizar ON cliente;
CREATE TRIGGER trg_cliente_normalizar
BEFORE INSERT OR UPDATE OF run, email ON cliente
FOR EACH ROW EXECUTE FUNCTION fn_cliente_normalizar();

CREATE OR REPLACE FUNCTION fn_solicitud_normalizar() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.run   := fn_normalizar_rut(NEW.run);
    NEW.email := fn_normalizar_email(NEW.email);
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_solicitud_normalizar ON solicitud_contacto;
CREATE TRIGGER trg_solicitud_normalizar
BEFORE INSERT OR UPDATE OF run, email ON solicitud_contacto
FOR EACH ROW EXECUTE FUNCTION fn_solicitud_normalizar();

CREATE OR REPLACE FUNCTION fn_empresa_normalizar() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.rut   := fn_normalizar_rut(NEW.rut);
    NEW.email := fn_normalizar_email(NEW.email);
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_empresa_normalizar ON empresa;
CREATE TRIGGER trg_empresa_normalizar
BEFORE INSERT OR UPDATE OF rut, email ON empresa
FOR EACH ROW EXECUTE FUNCTION fn_empresa_normalizar();

CREATE OR REPLACE FUNCTION fn_representante_normalizar() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.run := fn_normalizar_rut(NEW.run);
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_representante_normalizar ON representante_legal;
CREATE TRIGGER trg_representante_normalizar
BEFORE INSERT OR UPDATE OF run ON representante_legal
FOR EACH ROW EXECUTE FUNCTION fn_representante_normalizar();


-- =========================================================
-- 2. fecha_actualizacion AUTOMATICA
-- El DEFAULT solo aplica en el INSERT; sin este trigger la columna se quedaria
-- con la fecha de creacion.
-- =========================================================
CREATE OR REPLACE FUNCTION fn_set_fecha_actualizacion() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.fecha_actualizacion := now() AT TIME ZONE 'utc';
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_solicitud_fecha_actualizacion ON solicitud_contacto;
CREATE TRIGGER trg_solicitud_fecha_actualizacion
BEFORE UPDATE ON solicitud_contacto
FOR EACH ROW EXECUTE FUNCTION fn_set_fecha_actualizacion();

DROP TRIGGER IF EXISTS trg_empresa_fecha_actualizacion ON empresa;
CREATE TRIGGER trg_empresa_fecha_actualizacion
BEFORE UPDATE ON empresa
FOR EACH ROW EXECUTE FUNCTION fn_set_fecha_actualizacion();

DROP TRIGGER IF EXISTS trg_tramite_fecha_actualizacion ON tramite;
CREATE TRIGGER trg_tramite_fecha_actualizacion
BEFORE UPDATE ON tramite
FOR EACH ROW EXECUTE FUNCTION fn_set_fecha_actualizacion();


-- =========================================================
-- 3. historial_estado
-- =========================================================

-- 3.1 Sin estados repetidos seguidos -----------------------------------------
-- Evita ruido de auditoria por reintentos o bugs de la app. Bloquea la fila
-- del tramite para que dos inserciones simultaneas no pasen las dos el chequeo.
CREATE OR REPLACE FUNCTION fn_historial_no_duplicado() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_ultimo_estado VARCHAR(30);
BEGIN
    PERFORM 1 FROM tramite WHERE id = NEW.tramite_id FOR UPDATE;

    SELECT he.estado_tramite_codigo INTO v_ultimo_estado
    FROM historial_estado he
    WHERE he.tramite_id = NEW.tramite_id
    ORDER BY he.fecha DESC, he.id DESC
    LIMIT 1;

    IF v_ultimo_estado = NEW.estado_tramite_codigo THEN
        RAISE EXCEPTION 'No se puede repetir el mismo estado (%) dos veces seguidas para el tramite %',
            NEW.estado_tramite_codigo, NEW.tramite_id;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_historial_no_duplicado ON historial_estado;
CREATE TRIGGER trg_historial_no_duplicado
BEFORE INSERT ON historial_estado
FOR EACH ROW EXECUTE FUNCTION fn_historial_no_duplicado();

-- 3.2 Append-only ------------------------------------------------------------
-- TRUNCATE no dispara triggers de fila: para limpiar la tabla en desarrollo o
-- en tests se usa TRUNCATE, no DELETE.
CREATE OR REPLACE FUNCTION fn_historial_inmutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'historial_estado es append-only: no se permite %', TG_OP;
END;
$$;

DROP TRIGGER IF EXISTS trg_historial_inmutable ON historial_estado;
CREATE TRIGGER trg_historial_inmutable
BEFORE UPDATE OR DELETE ON historial_estado
FOR EACH ROW EXECUTE FUNCTION fn_historial_inmutable();

-- 3.3 tramite.estado_tramite_codigo = ultimo registro del historial ----------
-- Una sola fuente de verdad: la app inserta en el historial y el estado del
-- tramite se actualiza solo.
CREATE OR REPLACE FUNCTION fn_historial_sincronizar_tramite() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    UPDATE tramite
    SET estado_tramite_codigo = NEW.estado_tramite_codigo
    WHERE id = NEW.tramite_id
      AND estado_tramite_codigo IS DISTINCT FROM NEW.estado_tramite_codigo;
    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_historial_sincronizar_tramite ON historial_estado;
CREATE TRIGGER trg_historial_sincronizar_tramite
AFTER INSERT ON historial_estado
FOR EACH ROW EXECUTE FUNCTION fn_historial_sincronizar_tramite();


-- =========================================================
-- 4. sucursal: INICIALES FIJAS UNA VEZ USADAS EN UN FOLIO
-- Las iniciales forman el folio (LF-01-2026). Si cambian, el correlativo se
-- reinicia y los contratos ya emitidos quedan con otras iniciales.
-- =========================================================
CREATE OR REPLACE FUNCTION fn_sucursal_iniciales_fijas() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.iniciales IS DISTINCT FROM OLD.iniciales
       AND EXISTS (SELECT 1 FROM tramite
                   WHERE sucursal_id = OLD.id AND folio IS NOT NULL) THEN
        RAISE EXCEPTION 'La sucursal % ya tiene folios emitidos con las iniciales %; no se pueden cambiar',
            OLD.nombre, OLD.iniciales;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_sucursal_iniciales_fijas ON sucursal;
CREATE TRIGGER trg_sucursal_iniciales_fijas
BEFORE UPDATE OF iniciales ON sucursal
FOR EACH ROW EXECUTE FUNCTION fn_sucursal_iniciales_fijas();


-- =========================================================
-- 5. VISTAS
-- =========================================================

-- Versiones de plantilla: quien la subio, si esta activa y cuantos tramites
-- se generaron con cada una.
CREATE OR REPLACE VIEW v_plantilla_versiones AS
SELECT p.id                  AS plantilla_id,
       t.id                  AS tipo_tramite_id,
       t.nombre              AS tipo_tramite,
       p.version,
       p.activo,
       p.nombre_original,
       p.tamano_bytes,
       p.fecha_creacion,
       u.nombre              AS subida_por,
       COUNT(tr.id)          AS tramites_generados
FROM plantilla_documento p
JOIN tipo_tramite t   ON t.id = p.tipo_tramite_id
JOIN usuario u        ON u.id = p.usuario_id
LEFT JOIN tramite tr  ON tr.plantilla_documento_id = p.id
GROUP BY p.id, t.id, u.id;
